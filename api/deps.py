"""Dependencias comunes: usuario actual (cookie JWT), cliente efectivo, catálogo
con precios del cliente y serialización JSON de DataFrames/Firestore."""
from __future__ import annotations

import datetime as dt
import math
import threading
import time
from typing import Any

import pandas as pd
from fastapi import Depends, HTTPException, Request

import auth
import catalog
import config
import reposicion

COOKIE = config.COOKIE_NAME

# Cache de dim_cliente por código (BQ): TTL 10 min, process-wide.
_cli_cache: dict[int, tuple[dict | None, float]] = {}
_cli_lock = threading.Lock()
_CLI_TTL = 600


def get_cliente(cliente_cod: int | None) -> dict | None:
    if cliente_cod is None:
        return None
    with _cli_lock:
        hit = _cli_cache.get(int(cliente_cod))
        if hit and time.time() - hit[1] < _CLI_TTL:
            return hit[0]
    cli = catalog.get_cliente(int(cliente_cod))
    with _cli_lock:
        _cli_cache[int(cliente_cod)] = (cli, time.time())
    return cli


def invalidar_cliente(cliente_cod: int | None) -> None:
    if cliente_cod is not None:
        with _cli_lock:
            _cli_cache.pop(int(cliente_cod), None)


# Cache del doc `usuarios/{email}` (Firestore): TTL 60 s. El JWT dura 24 h, pero desactivar un usuario,
# cambiarle el rol/cliente o resetearle la password tiene que pegar en ~1 min, no al día siguiente.
_usr_cache: dict[str, tuple[dict | None, float]] = {}
_USR_TTL = 60


def get_usuario(email: str) -> dict | None:
    email = (email or "").strip().lower()
    with _cli_lock:
        hit = _usr_cache.get(email)
        if hit and time.time() - hit[1] < _USR_TTL:
            return hit[0]
    u = auth.get_usuario(email)
    with _cli_lock:
        _usr_cache[email] = (u, time.time())
    return u


def invalidar_usuario(email: str | None) -> None:
    if email:
        with _cli_lock:
            _usr_cache.pop(email.strip().lower(), None)


def invalidar_todo() -> None:
    with _cli_lock:
        _cli_cache.clear()
        _usr_cache.clear()


class Ctx:
    """Contexto de la request: claims del JWT + cliente efectivo."""

    def __init__(self, claims: dict, cliente: dict | None):
        self.email: str = claims["sub"]
        self.rol: str = claims.get("rol", "cliente")
        self.cliente_cod: int | None = claims.get("cliente_cod")
        self.nombre: str = claims.get("nombre") or ""
        self.cliente = cliente

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def puede_pedir(self) -> bool:
        return bool(self.cliente)

    @property
    def lista(self) -> int:
        return int((self.cliente or {}).get("lista_precios") or 1)

    @property
    def descuento(self) -> float:
        return float((self.cliente or {}).get("descuento") or 0)

    @property
    def es_franquicia(self) -> bool:
        return self.cliente_cod is not None and reposicion.pv_de_cliente(self.cliente_cod) is not None

    def usuario_dict(self) -> dict:
        return {"email": self.email, "rol": self.rol, "cliente_cod": self.cliente_cod,
                "nombre_display": self.nombre}

    def publico(self) -> dict:
        cli = self.cliente or {}
        return {
            "user": {"email": self.email, "rol": self.rol, "nombre": self.nombre,
                     "cliente_cod": self.cliente_cod},
            "cliente": {
                "cliente_cod": cli.get("cliente_cod"), "nombre": cli.get("nombre_display") or cli.get("nombre"),
                "lista_precios": self.lista, "descuento": self.descuento, "cuit": cli.get("cuit"),
                "contacto_nombre": cli.get("contacto_nombre", ""), "contacto_email": cli.get("contacto_email", ""),
                "contacto_telefono": cli.get("contacto_telefono", ""),
                "localidad": cli.get("localidad"), "provincia": cli.get("provincia_desc"),
            } if cli else None,
            "puede_pedir": self.puede_pedir,
            "es_admin": self.es_admin,
            "es_franquicia": self.es_franquicia,
        }


def _token(request: Request) -> str | None:
    tok = request.cookies.get(COOKIE)
    if tok:
        return tok
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def ctx_opcional(request: Request) -> Ctx | None:
    claims = auth.verify_jwt(_token(request))
    if not claims:
        return None
    u = get_usuario(claims.get("sub"))
    if not u or not u.get("activo", True):
        return None                       # usuario borrado o desactivado por el admin
    pwd_ts = u.get("password_updated_at")
    if pwd_ts is not None and claims.get("iat") and hasattr(pwd_ts, "timestamp") \
            and float(claims["iat"]) < pwd_ts.timestamp() - 1:
        return None                       # la password cambió después de emitir este token
    # rol / cliente_cod / nombre: siempre los del doc (los claims pueden tener 24 h de antigüedad)
    vivo = {**claims, "rol": u.get("rol", "cliente"),
            "cliente_cod": int(u["cliente_cod"]) if u.get("cliente_cod") is not None else None,
            "nombre": u.get("nombre_display") or claims.get("nombre") or ""}
    return Ctx(vivo, get_cliente(vivo["cliente_cod"]))


def ctx_requerido(request: Request) -> Ctx:
    c = ctx_opcional(request)
    if c is None:
        raise HTTPException(401, "No autenticado")
    return c


def ctx_cliente(c: Ctx = Depends(ctx_requerido)) -> Ctx:
    if not c.puede_pedir:
        raise HTTPException(403, "Tu usuario no tiene un cliente asociado para hacer pedidos")
    return c


def ctx_admin(c: Ctx = Depends(ctx_requerido)) -> Ctx:
    if not c.es_admin:
        raise HTTPException(403, "Solo administradores")
    return c


# ---------------------------------------------------------------------------
# Catálogo con precios del cliente
# ---------------------------------------------------------------------------
_df_cache: dict[int, tuple[pd.DataFrame, float, object, object]] = {}   # lista → (df, ts catálogo, overrides, config)
_df_lock = threading.Lock()


def df_cliente(c: Ctx) -> pd.DataFrame:
    """Variantes publicadas con `precio`, `precio_lista`, `pct_desc` de la lista del cliente.
    Admin sin cliente → lista 1 (igual que `cliente_efectivo` del Streamlit).
    Memoizado por lista mientras no cambien el catálogo BQ, los overrides ni la config
    (antes se recalculaba `aplicar_overrides` + `con_precio` —copias completas— en CADA request).
    El DataFrame devuelto es compartido: los callers filtran/copian, nunca lo mutan."""
    import overrides
    lista = c.lista
    ov = overrides.get_catalogo_overrides()
    cfg = overrides.get_config()
    with _df_lock:
        hit = _df_cache.get(lista)
        if hit and hit[1] == catalog._cache.ts and hit[2] is ov and hit[3] is cfg:
            return hit[0]
    base = catalog.variantes_publicadas()
    ts = catalog._cache.ts
    df = catalog.con_precio(base, lista)
    with _df_lock:
        _df_cache[lista] = (df, ts, ov, cfg)
    return df


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------
def jsonable(o: Any) -> Any:
    """NaN → None, numpy → python, datetime → ISO, DataFrame → records."""
    if o is None:
        return None
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, (str, bool, int)):
        return o
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return [jsonable(r) for r in o.to_dict("records")]
    if isinstance(o, pd.Series):
        return jsonable(o.to_dict())
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if hasattr(o, "item"):          # numpy scalar
        try:
            return jsonable(o.item())
        except Exception:  # noqa: BLE001
            pass
    if pd.isna(o) if not isinstance(o, (list, dict)) else False:
        return None
    return str(o)
