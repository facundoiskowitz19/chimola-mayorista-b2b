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
import re
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
    """Merge de campos de producto {publicado, destacado, nombre, descripcion,
    precios, ub} y de variante `variantes: {sku: {stock, oculta, precios}}`.
    ub = múltiplo/mínimo de compra (unidad de bulto). Ver SPECS §3."""
    permitidos = {"publicado", "destacado", "nombre", "descripcion", "precios", "ub", "variantes",
                  "variantes_extra", "fotos_color"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if "variantes_extra" in campos:
        limpio = {}
        for sku, vo in (campos["variantes_extra"] or {}).items():
            precios_x = {str(k): float(p) for k, p in (vo.get("precios") or {}).items() if p and float(p) > 0}
            if not precios_x.get("1") or vo.get("stock") is None:
                continue   # stock y precio L1 son obligatorios (no hay Aleph de fallback)
            limpio[sku] = {"color": str(vo.get("color") or "").strip().upper(),
                           "talle": str(vo.get("talle") or "U").strip().upper().replace(" ", ""),
                           "stock": max(0, int(vo["stock"])), "precios": precios_x,
                           "ean": str(vo.get("ean") or "").strip()}
        campos["variantes_extra"] = limpio
    if "precios" in campos and campos["precios"]:
        campos["precios"] = {str(k): float(v) for k, v in campos["precios"].items() if v and float(v) > 0}
    if "ub" in campos:
        campos["ub"] = int(campos["ub"]) if campos["ub"] and int(campos["ub"]) > 1 else None
    if "variantes" in campos:
        limpio = {}
        for sku, vo in (campos["variantes"] or {}).items():
            v = {}
            if vo.get("stock") is not None:
                v["stock"] = max(0, int(vo["stock"]))
            if vo.get("oculta"):
                v["oculta"] = True
            precios = {str(k): float(p) for k, p in (vo.get("precios") or {}).items() if p and float(p) > 0}
            if precios:
                v["precios"] = precios
            if v:
                limpio[sku] = v
        campos["variantes"] = limpio
    if "fotos_color" in campos:   # {color: filename} — asignación manual foto↔variante
        campos["fotos_color"] = {str(c): str(fn) for c, fn in (campos["fotos_color"] or {}).items() if fn}
    ref = db.catalogo_overrides_col().document(str(producto_cod))
    # `precios`, `variantes` y `fotos_color` se REEMPLAZAN completos (merge
    # fusionaría por clave y no se podría quitar un override puntual).
    variantes = campos.pop("variantes", None)
    extras = campos.pop("variantes_extra", None)
    fotos_color = campos.pop("fotos_color", None)
    precios = campos.pop("precios", None) if "precios" in campos else "__keep__"
    ref.set(_audit(campos, por), merge=True)
    reemplazos = {}
    if variantes is not None:
        reemplazos["variantes"] = variantes
    if extras is not None:
        reemplazos["variantes_extra"] = extras
    if fotos_color is not None:
        reemplazos["fotos_color"] = fotos_color
    if precios != "__keep__":
        reemplazos["precios"] = precios or {}
    if reemplazos:
        ref.update(reemplazos)
    invalidar("catalogo")
    log.info("Override catálogo %s por %s: %s variantes=%s", producto_cod, por, campos,
             list(variantes) if variantes else None)


def quitar_catalogo_override(producto_cod: str) -> None:
    db.catalogo_overrides_col().document(str(producto_cod)).delete()
    invalidar("catalogo")


def aplicar_overrides(df: pd.DataFrame, incluir_ocultos: bool = False) -> pd.DataFrame:
    """Pisa nombre/descripcion/precios (producto), stock/oculta/precios (variante),
    agrega `destacado`, `publicado`, `ub`, `stock_manual`, `var_oculta` y filtra
    ocultos y variantes sin stock (salvo incluir_ocultos=True, vista admin)."""
    out = df.copy()
    out["destacado"] = False
    out["publicado"] = None
    out["ub"] = None
    out["stock_manual"] = False
    out["var_oculta"] = False
    out["es_manual"] = False
    ov = get_catalogo_overrides()
    if ov:
        idx = out["producto_cod"]
        out["publicado"] = idx.map(lambda p: ov.get(p, {}).get("publicado"))
        out["destacado"] = idx.map(lambda p: bool(ov.get(p, {}).get("destacado"))).astype(bool)
        out["ub"] = idx.map(lambda p: ov.get(p, {}).get("ub"))
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
        # Overrides por VARIANTE (SPECS §3): stock manual reemplaza, oculta excluye,
        # precio por variante pisa al del producto.
        stock_map, ocultas, var_precios = variantes_overrides()
        if stock_map:
            manual = out["sku"].map(stock_map)
            out["stock_manual"] = manual.notna()
            out["stock"] = manual.fillna(out["stock"]).astype(int)
        if ocultas:
            out["var_oculta"] = out["sku"].isin(ocultas)
        for sku, precios in var_precios.items():
            for lista, precio in precios.items():
                col = f"precio{int(lista)}"
                if col in out.columns:
                    out.loc[out["sku"] == sku, col] = float(precio)
        # Variantes MANUALES fuera de Aleph (fase 6, E4): se sintetizan filas
        # heredando los atributos del producto; stock/precio son 100% manuales.
        nuevas = []
        for p, o in ov.items():
            extras = o.get("variantes_extra") or {}
            if not extras:
                continue
            base_rows = out[out["producto_cod"] == p]
            if base_rows.empty:
                continue   # el producto no está en el catálogo actual
            base = base_rows.iloc[0]
            for sku, vo in extras.items():
                fila = base.copy()
                fila["sku"] = sku
                fila["color"] = vo.get("color", "")
                fila["color_cod"] = "X" + re.sub(r"[^A-Z0-9]", "", str(vo.get("color", "")).upper())[:12]
                fila["talle"] = vo.get("talle", "U")
                fila["ean"] = vo.get("ean", "")
                fila["stock"] = int(vo.get("stock") or 0)
                fila["stock_manual"] = True
                fila["var_oculta"] = False
                fila["es_manual"] = True
                for lista, precio in (vo.get("precios") or {}).items():
                    col = f"precio{int(lista)}"
                    if col in out.columns:
                        fila[col] = float(precio)
                nuevas.append(fila)
        if nuevas:
            out = pd.concat([out, pd.DataFrame(nuevas)], ignore_index=True)
        if not incluir_ocultos:
            out = out[out["publicado"].map(lambda v: v is not False)]
            out = out[~out["var_oculta"] & (out["stock"] > 0)]
    return out


def variantes_overrides() -> tuple[dict, set, dict]:
    """(stock_map {sku: int}, ocultas {sku}, var_precios {sku: {lista: precio}})."""
    stock_map, ocultas, var_precios = {}, set(), {}
    for _, o in get_catalogo_overrides().items():
        for sku, vo in (o.get("variantes") or {}).items():
            if vo.get("stock") is not None:
                stock_map[sku] = int(vo["stock"])
            if vo.get("oculta"):
                ocultas.add(sku)
            if vo.get("precios"):
                var_precios[sku] = vo["precios"]
        # Las variantes manuales SIEMPRE resuelven por su stock manual
        # (BQ no las conoce) — clave para la validación al confirmar.
        for sku, vo in (o.get("variantes_extra") or {}).items():
            stock_map[sku] = int(vo.get("stock") or 0)
            if vo.get("precios"):
                var_precios[sku] = vo["precios"]
    return stock_map, ocultas, var_precios


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
def get_clientes_overrides() -> dict[int, dict]:
    def load():
        return {int(d.id): (d.to_dict() or {}) for d in db.clientes_overrides_col().stream()}
    return _cached("clientes", load)


def set_cliente_override(cliente_cod: int, campos: dict, por: str) -> None:
    permitidos = {"descuento_pct", "lista_precios", "notas",
                  "contacto_nombre", "contacto_email", "cuit", "odoo_cliente"}
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
    # Contacto (no existe en Aleph: siempre viene del override si está)
    out["contacto_nombre"] = o.get("contacto_nombre") or ""
    out["contacto_email"] = o.get("contacto_email") or ""
    out["odoo_cliente"] = o.get("odoo_cliente") or ""   # nombre del cliente en Odoo (export franquicias)
    # CUIT: el override pisa al de Aleph
    out["cuit_origen"] = "Aleph"
    if o.get("cuit"):
        out["cuit"] = o["cuit"]
        out["cuit_origen"] = "Override"
    return out


# ---------------------------------------------------------------------------
# Config global
# ---------------------------------------------------------------------------
DEFAULTS_CONFIG = {
    "pedidos_email_to": None,          # None → env config.PEDIDOS_EMAIL_TO
    "banner_texto": "",
    "aplicar_descvta": False,
    "minimo_pedido_unidades": None,
    # Las listas mayoristas de Aleph son SIN IVA (el Woo muestra "+IVA" y la NP
    # suma 21%). Se muestra como línea informativa en carrito/Excel. 0 = ocultar.
    "iva_pct": 21.0,
    # Mail al cliente + Chimola cuando un pedido cambia de estado (procesado/cancelado).
    "notificar_estados": True,
    # Reposición sugerida (franquicias): días de venta a cubrir con el pedido.
    "repo_dias_objetivo": 21,
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


def get_emails_config() -> dict:
    """Doc config/emails: {evento: {formato, asunto, cuerpo}} (vacío = defaults)."""
    def load():
        snap = db.emails_ref().get()
        return snap.to_dict() or {}
    return _cached("emails", load)


def set_email_template(evento: str, campos: dict, por: str) -> None:
    permitidos = {"formato", "asunto", "cuerpo"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if campos.get("formato") not in (None, "texto", "html"):
        raise ValueError("formato debe ser 'texto' o 'html'")
    db.emails_ref().set({evento: campos, **_audit({}, por)}, merge=True)
    db.emails_ref().update({evento: campos})   # reemplaza el evento completo
    invalidar("emails")
    log.info("Template email '%s' por %s (formato=%s)", evento, por, campos.get("formato"))


def reset_email_template(evento: str, por: str) -> None:
    from google.cloud import firestore as _fs

    db.emails_ref().set(_audit({}, por), merge=True)
    db.emails_ref().update({evento: _fs.DELETE_FIELD})
    invalidar("emails")


def set_masivo(cods: list[str], campos: dict, por: str) -> int:
    """Aplica el MISMO override simple (publicado/destacado) a muchos productos
    con batched writes de Firestore (fase 8, T5). Solo campos escalares del
    lote — nunca precios/variantes (esos van por set_catalogo_override)."""
    permitidos = {"publicado", "destacado"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos or not cods:
        return 0
    cli = db.client()
    batch = cli.batch()
    n = 0
    for cod in cods:
        batch.set(db.catalogo_overrides_col().document(str(cod)), _audit(dict(campos), por), merge=True)
        n += 1
        if n % 400 == 0:   # límite de Firestore: 500 writes por batch
            batch.commit()
            batch = cli.batch()
    batch.commit()
    invalidar("catalogo")
    log.info("Override masivo %s a %d productos por %s", campos, n, por)
    return n


def pedidos_email_to() -> list[str]:
    v = get_config().get("pedidos_email_to")
    if v:
        return [e.strip() for e in str(v).split(",") if e.strip()]
    return config.PEDIDOS_EMAIL_TO
