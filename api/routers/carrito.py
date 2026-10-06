"""Carrito persistido en Firestore `carritos/{email}` (mismo doc que usa el Streamlit)."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import compra_rapida as cr
import fotos
import overrides
import pedidos

from api import deps

router = APIRouter(prefix="/carrito", tags=["carrito"])


class ItemIn(BaseModel):
    sku: str
    cantidad: int = Field(ge=0, le=100_000)


class ItemsIn(BaseModel):
    items: list[ItemIn]


class CantidadIn(BaseModel):
    cantidad: int = Field(ge=0, le=100_000)


def _vista(c: deps.Ctx, items: list[dict], avisos: list[str] | None = None) -> dict:
    cfg = overrides.get_config()
    tot = pedidos.calcular_totales(copy.deepcopy(items), c.descuento, iva_pct=cfg.get("iva_pct") or 0)
    out_items = []
    for it in items:
        d = {k: deps.jsonable(it.get(k)) for k in ("sku", "ean", "producto_cod", "producto_nombre", "color_cod",
                                                    "color", "talle", "cantidad", "precio_unit", "precio_lista",
                                                    "pct_desc", "manual")}
        d["subtotal"] = round(float(it["precio_unit"]) * int(it["cantidad"]), 2)
        d["foto"] = fotos.url_variante_publica(it["producto_cod"], it.get("color")) or None
        out_items.append(d)
    return {"items": out_items, "totales": deps.jsonable(tot), "avisos": avisos or [],
            "minimo_unidades": cfg.get("minimo_pedido_unidades"), "minimo_monto": cfg.get("minimo_pedido_monto")}


@router.get("")
def ver(c: deps.Ctx = Depends(deps.ctx_cliente)):
    return _vista(c, pedidos.cargar_carrito(c.email))


@router.post("/items")
def agregar(body: ItemsIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Suma cantidades (consolida por SKU). Acota al stock sin revelarlo."""
    df = deps.df_cliente(c)
    por_sku = df.set_index("sku", drop=False)
    items = pedidos.cargar_carrito(c.email)
    avisos: list[str] = []
    agregadas = 0
    for it in body.items:
        if it.cantidad <= 0:
            continue
        if it.sku not in por_sku.index:
            avisos.append(f"{it.sku}: no disponible")
            continue
        v = por_sku.loc[it.sku]
        if hasattr(v, "iloc") and getattr(v, "ndim", 1) == 2:
            v = v.iloc[0]
        if v["precio"] != v["precio"]:   # NaN
            avisos.append(f"{v['producto_nombre']} {v['color']}: sin precio en tu lista")
            continue
        actual = next((x["cantidad"] for x in items if x["sku"] == it.sku), 0)
        tope = max(0, int(v["stock"]) - int(actual))
        cant = min(it.cantidad, tope)
        if cant < it.cantidad:
            avisos.append(f"{v['producto_nombre']} {v['color']} Talle {v['talle']}: estás superando la "
                          "cantidad disponible — lo ajustamos al máximo posible")
        if cant <= 0:
            continue
        items = pedidos.agregar_al_carrito(items, cr.item_desde_variante(v.to_dict(), cant))
        agregadas += cant
    pedidos.guardar_carrito(c.email, items)
    out = _vista(c, items, avisos)
    out["agregadas"] = agregadas
    return out


@router.put("/items/{sku}")
def fijar(sku: str, body: CantidadIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Fija la cantidad de una línea (0 = quitar). Acota al stock conocido."""
    items = pedidos.cargar_carrito(c.email)
    avisos: list[str] = []
    nuevos = []
    for it in items:
        if it["sku"] != sku:
            nuevos.append(it)
            continue
        if body.cantidad <= 0:
            continue
        tope = int(it.get("stock") or 0)
        cant = body.cantidad if tope <= 0 else min(body.cantidad, tope)
        if cant < body.cantidad:
            avisos.append("Estás superando la cantidad disponible — lo ajustamos al máximo posible")
        nuevos.append({**it, "cantidad": cant})
    if not any(i["sku"] == sku for i in items):
        raise HTTPException(404, "Esa línea no está en el carrito")
    pedidos.guardar_carrito(c.email, nuevos)
    return _vista(c, nuevos, avisos)


@router.delete("")
def vaciar(c: deps.Ctx = Depends(deps.ctx_cliente)):
    pedidos.vaciar_carrito(c.email)
    return _vista(c, [])
