"""Capa administrable (Firestore) que pisa el catálogo readonly de BigQuery.

Ver SPECS.md §2-§6. Reglas:
- Override inexistente o null → vale lo de Aleph/BQ.
- `publicado`: None=auto (visible con stock), False=oculto siempre, True=visible (con stock).
- `precios[lista]` pisa articulosol.precio{N} solo para esa lista.
- Todo write guarda updated_at/updated_by y invalida el cache (TTL 60s).
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import pandas as pd

import config
import db

log = logging.getLogger(__name__)

TTL_SEG = 60

_lock = threading.Lock()
_cache: dict[str, tuple[object, float]] = {}


def _cached(name: str, loader):
    with _lock:
        hit = _cache.get(name)
        if hit and time.time() - hit[1] < TTL_SEG:
            return hit[0]
    data = loader()
    with _lock:
        _cache[name] = (data, time.time())
    return data


def invalidar(name: str | None = None) -> None:
    with _lock:
        if name:
            _cache.pop(name, None)
        else:
            _cache.clear()


def _audit(campos: dict, por: str) -> dict:
    return {**campos, "updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def get_catalogo_overrides() -> dict[str, dict]:
    """{producto_cod: doc} de toda la colección (chica: solo productos tocados)."""
    def load():
        return {d.id: (d.to_dict() or {}) for d in db.catalogo_overrides_col().stream()}
    return _cached("catalogo", load)


def set_catalogo_override(producto_cod: str, campos: dict, por: str) -> None:
    """Merge de campos {publicado, destacado, nombre, descripcion, precios}."""
    permitidos = {"publicado", "destacado", "nombre", "descripcion", "precios"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if "precios" in campos and campos["precios"]:
        campos["precios"] = {str(k): float(v) for k, v in campos["precios"].items() if v and float(v) > 0}
    db.catalogo_overrides_col().document(str(producto_cod)).set(_audit(campos, por), merge=True)
    invalidar("catalogo")
    log.info("Override catálogo %s por %s: %s", producto_cod, por, campos)


def aplicar_overrides(df: pd.DataFrame, incluir_ocultos: bool = False) -> pd.DataFrame:
    """Pisa nombre/descripcion/precios, agrega `destacado` y `publicado`, y
    filtra los ocultos (salvo incluir_ocultos=True, para la vista admin)."""
    out = df.copy()
    out["destacado"] = False
    out["publicado"] = None
    ov = get_catalogo_overrides()
    if ov:
        idx = out["producto_cod"]
        pub = idx.map(lambda p: ov.get(p, {}).get("publicado"))
        out["publicado"] = pub
        out["destacado"] = idx.map(lambda p: bool(ov.get(p, {}).get("destacado"))).astype(bool)
        nombres = {p: o["nombre"] for p, o in ov.items() if o.get("nombre")}
        descrs = {p: o["descripcion"] for p, o in ov.items() if o.get("descripcion")}
        if nombres:
            out["producto_nombre"] = idx.map(nombres).fillna(out["producto_nombre"])
        if descrs and "descripcion" in out:
            out["descripcion"] = idx.map(descrs).fillna(out["descripcion"])
        for p, o in ov.items():
            for lista, precio in (o.get("precios") or {}).items():
                col = f"precio{int(lista)}"
                if col in out.columns:
                    out.loc[out["producto_cod"] == p, col] = float(precio)
        if not incluir_ocultos:
            out = out[out["publicado"].map(lambda v: v is not False)]
    return out


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
def get_clientes_overrides() -> dict[int, dict]:
    def load():
        return {int(d.id): (d.to_dict() or {}) for d in db.clientes_overrides_col().stream()}
    return _cached("clientes", load)


def set_cliente_override(cliente_cod: int, campos: dict, por: str) -> None:
    permitidos = {"descuento_pct", "lista_precios", "notas"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    db.clientes_overrides_col().document(str(int(cliente_cod))).set(_audit(campos, por), merge=True)
    invalidar("clientes")
    log.info("Override cliente %s por %s: %s", cliente_cod, por, campos)


def aplicar_override_cliente(cliente: dict) -> dict:
    """Merge del override sobre el dict de dim_cliente. Agrega *_origen."""
    out = dict(cliente)
    out["descuento_origen"] = "Aleph"
    out["lista_origen"] = "Aleph"
    o = get_clientes_overrides().get(int(cliente["cliente_cod"]), {})
    if o.get("descuento_pct") is not None:
        out["descuento"] = float(o["descuento_pct"])
        out["descuento_origen"] = "Override"
    if o.get("lista_precios"):
        out["lista_precios"] = int(o["lista_precios"])
        out["lista_origen"] = "Override"
    if o.get("notas"):
        out["notas"] = o["notas"]
    return out


# ---------------------------------------------------------------------------
# Config global
# ---------------------------------------------------------------------------
DEFAULTS_CONFIG = {
    "pedidos_email_to": None,          # None → env config.PEDIDOS_EMAIL_TO
    "banner_texto": "",
    "aplicar_descvta": False,
    "minimo_pedido_unidades": None,
}


def get_config() -> dict:
    def load():
        snap = db.config_ref().get()
        return snap.to_dict() or {}
    doc = _cached("config", load)
    out = dict(DEFAULTS_CONFIG)
    out.update({k: v for k, v in doc.items() if k in DEFAULTS_CONFIG and v is not None})
    return out


def set_config(campos: dict, por: str) -> None:
    campos = {k: v for k, v in campos.items() if k in DEFAULTS_CONFIG}
    db.config_ref().set(_audit(campos, por), merge=True)
    invalidar("config")
    log.info("Config global por %s: %s", por, campos)


def pedidos_email_to() -> list[str]:
    v = get_config().get("pedidos_email_to")
    if v:
        return [e.strip() for e in str(v).split(",") if e.strip()]
    return config.PEDIDOS_EMAIL_TO
