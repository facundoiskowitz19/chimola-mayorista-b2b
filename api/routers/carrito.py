"""Carrito persistido en Firestore `carritos/{email}` (mismo doc que usa el Streamlit)."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import compra_rapida as cr
import fotos
import overrides
import pedidos
import sitio

from api import deps

router = APIRouter(prefix="/carrito", tags=["carrito"])


class ItemIn(BaseModel):
    sku: str
    cantidad: int = Field(ge=0, le=100_000)


class ItemsIn(BaseModel):
    items: list[ItemIn]
    # recortar=True: lo que supera lo disponible se agrega acotado (comportamiento histórico, lo usa Reposición).
    # recortar=False: si ALGO supera lo disponible no se agrega nada y la respuesta trae `ajustes` con el máximo
    # por SKU, para que el cliente vea el número, lo confirme y recién ahí se agregue.
    recortar: bool = True


class CantidadIn(BaseModel):
    cantidad: int = Field(ge=0, le=100_000)


def _secciones(c: deps.Ctx) -> dict[str, str]:
    """producto_cod → sección del header (marro/indu/lima) según el catálogo actual."""
    df = deps.df_cliente(c).drop_duplicates("producto_cod")
    return {cod: sitio.seccion_de(m, cat) for cod, m, cat in zip(df["producto_cod"], df["marca"], df["categoria"])}


def _vista(c: deps.Ctx, items: list[dict], avisos: list[str] | None = None) -> dict:
    cfg = overrides.get_config()
    tot = pedidos.calcular_totales(copy.deepcopy(items), c.descuento, iva_pct=cfg.get("iva_pct") or 0)
    secs = _secciones(c)
    out_items = []
    for it in items:
        d = {k: deps.jsonable(it.get(k)) for k in ("sku", "ean", "producto_cod", "producto_nombre", "color_cod",
                                                    "color", "talle", "cantidad", "precio_unit", "precio_lista",
                                                    "pct_desc", "manual")}
        d["subtotal"] = round(float(it["precio_unit"]) * int(it["cantidad"]), 2)
        d["foto"] = fotos.url_variante_publica(it["producto_cod"], it.get("color")) or None
        d["seccion"] = secs.get(it["producto_cod"]) or it.get("seccion") or "marro"
        out_items.append(d)
    return {"items": out_items, "totales": deps.jsonable(tot), "avisos": avisos or [],
            "minimo_unidades": cfg.get("minimo_pedido_unidades"), "minimo_monto": cfg.get("minimo_pedido_monto")}


@router.get("")
def ver(c: deps.Ctx = Depends(deps.ctx_cliente)):
    return _vista(c, pedidos.cargar_carrito(c.email))


@router.post("/items")
def agregar(body: ItemsIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Suma cantidades (consolida por SKU). Acota al stock (ver `ItemsIn.recortar`)."""
    df = deps.df_cliente(c)
    por_sku = df.drop_duplicates("sku").set_index("sku", drop=False)
    items = pedidos.cargar_carrito(c.email)
    avisos: list[str] = []
    ajustes: list[dict] = []
    a_agregar: list[tuple[dict, int]] = []
    for it in body.items:
        if it.cantidad <= 0:
            continue
        if it.sku not in por_sku.index:
            avisos.append(f"{it.sku}: no disponible")
            continue
        v = por_sku.loc[it.sku]
        if v["precio"] != v["precio"]:   # NaN
            avisos.append(f"{v['producto_nombre']} {v['color']}: sin precio en tu lista")
            continue
        actual = next((x["cantidad"] for x in items if x["sku"] == it.sku), 0)
        tope = max(0, int(v["stock"]) - int(actual))
        cant = min(it.cantidad, tope)
        if cant < it.cantidad:
            if not body.recortar:
                ajustes.append({"sku": it.sku, "producto_nombre": v["producto_nombre"], "color": v["color"],
                                "talle": v["talle"], "pedido": it.cantidad, "maximo": tope, "en_carrito": int(actual)})
                continue
            avisos.append(f"{v['producto_nombre']} {v['color']} Talle {v['talle']}: estás superando la "
                          "cantidad disponible — lo ajustamos al máximo posible")
        if cant <= 0:
            continue
        a_agregar.append((v.to_dict(), cant))
    if ajustes:   # nada se agrega: el cliente ve los máximos, los acepta y vuelve a enviar
        out = _vista(c, items, avisos)
        out["agregadas"] = 0
        out["ajustes"] = ajustes
        return out
    agregadas = 0
    for v, cant in a_agregar:
        items = pedidos.agregar_al_carrito(items, cr.item_desde_variante(v, cant))
        agregadas += cant
    pedidos.guardar_carrito(c.email, items)
    out = _vista(c, items, avisos)
    out["agregadas"] = agregadas
    out["ajustes"] = []
    return out


@router.put("/items/{sku}")
def fijar(sku: str, body: CantidadIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Fija la cantidad de una línea (0 = quitar). Acota al stock conocido."""
    items = pedidos.cargar_carrito(c.email)
    avisos: list[str] = []
    nuevos = []
    por_sku = deps.df_cliente(c).drop_duplicates("sku").set_index("sku", drop=False)
    for it in items:
        if it["sku"] != sku:
            nuevos.append(it)
            continue
        if body.cantidad <= 0:
            continue
        if sku in por_sku.index:   # stock y precio ACTUALES (la línea guarda los del momento de agregar)
            v = por_sku.loc[sku]
            if v["precio"] == v["precio"]:
                it = {**it, **cr.item_desde_variante(v.to_dict(), 1), "cantidad": it["cantidad"]}
        tope = int(it.get("stock") or 0)
        cant = body.cantidad if tope <= 0 else min(body.cantidad, tope)
        if cant < body.cantidad:
            avisos.append(f"{it['producto_nombre']} {it['color']}: el máximo disponible es {cant} u. — lo ajustamos")
        nuevos.append({**it, "cantidad": cant})
    if not any(i["sku"] == sku for i in items):
        raise HTTPException(404, "Esa línea no está en el carrito")
    pedidos.guardar_carrito(c.email, nuevos)
    return _vista(c, nuevos, avisos)


class QuitarIn(BaseModel):
    skus: list[str]


@router.post("/quitar")
def quitar(body: QuitarIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Quita varias líneas de una (todas las variantes de un producto)."""
    items = pedidos.cargar_carrito(c.email)
    fuera = set(body.skus)
    nuevos = [i for i in items if i["sku"] not in fuera]
    pedidos.guardar_carrito(c.email, nuevos)
    return _vista(c, nuevos)


@router.delete("")
def vaciar(c: deps.Ctx = Depends(deps.ctx_cliente)):
    pedidos.vaciar_carrito(c.email)
    return _vista(c, [])
