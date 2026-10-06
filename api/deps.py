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
    return Ctx(claims, get_cliente(claims.get("cliente_cod")))


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
def df_cliente(c: Ctx) -> pd.DataFrame:
    """Variantes publicadas con `precio`, `precio_lista`, `pct_desc` de la lista del cliente.
    Admin sin cliente → lista 1 (igual que `cliente_efectivo` del Streamlit)."""
    return catalog.con_precio(catalog.variantes_publicadas(), c.lista)


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
