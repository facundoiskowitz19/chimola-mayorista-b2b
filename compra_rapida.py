"""Compra rápida (SPECS §7): helpers puros para armar items de carrito desde
la tabla editable y desde texto pegado (SKU/EAN + cantidad). La UI vive en app.py.
"""
from __future__ import annotations

import re

import pandas as pd

SEPARADORES = re.compile(r"[,;\t]+|\s{2,}")


def item_desde_variante(v, cantidad: int) -> dict:
    """Row del catálogo (con columna `precio`) → item de carrito."""
    return {"sku": v["sku"], "ean": v["ean"], "producto_cod": v["producto_cod"],
            "producto_nombre": v["producto_nombre"], "color_cod": str(v["color_cod"]),
            "color": v["color"], "talle": v["talle"], "cantidad": int(cantidad),
            "precio_unit": float(v["precio"]), "stock": int(v["stock"])}


def parsear_lineas(texto: str) -> list[tuple[str, int, int]]:
    """Texto pegado → [(codigo, cantidad, nro_linea)]. Acepta `SKU,3`, `EAN;2`,
    `SKU<TAB>4` o `SKU 3` (un espacio también vale). Sin cantidad → 1."""
    out = []
    for n, raw in enumerate((texto or "").splitlines(), start=1):
        linea = raw.strip()
        if not linea:
            continue
        partes = [p for p in SEPARADORES.split(linea) if p.strip()]
        if len(partes) == 1 and " " in partes[0]:
            partes = partes[0].rsplit(" ", 1)
        codigo = partes[0].strip().upper()
        cant = 1
        if len(partes) > 1:
            try:
                cant = int(float(partes[1].strip().replace(",", ".")))
            except ValueError:
                out.append((codigo, -1, n))   # cantidad ilegible
                continue
        out.append((codigo, cant, n))
    return out


def resolver_pegado(texto: str, df_publicadas: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Texto pegado → (items de carrito, avisos). Busca por SKU o EAN.
    Consolida cantidades por SKU y recorta al stock."""
    por_sku = {str(r["sku"]).upper(): r for _, r in df_publicadas.iterrows()}
    por_ean = {str(r["ean"]).upper(): r for _, r in df_publicadas.iterrows() if str(r["ean"]).strip()}
    pedidos: dict[str, int] = {}
    avisos: list[str] = []
    for codigo, cant, n in parsear_lineas(texto):
        if cant == -1:
            avisos.append(f"Línea {n}: cantidad ilegible ({codigo})")
            continue
        if cant <= 0:
            avisos.append(f"Línea {n}: cantidad debe ser > 0 ({codigo})")
            continue
        v = por_sku.get(codigo)
        if v is None:
            v = por_ean.get(codigo)
        if v is None:
            avisos.append(f"Línea {n}: código '{codigo}' no encontrado o sin stock publicado")
            continue
        pedidos[str(v["sku"])] = pedidos.get(str(v["sku"]), 0) + cant

    items = []
    for sku, cant in pedidos.items():
        v = por_sku[sku.upper()]
        if pd.isna(v["precio"]):
            avisos.append(f"{sku}: sin precio en tu lista — consultá a Chimola")
            continue
        disp = int(v["stock"])
        if cant > disp:
            avisos.append(f"{sku}: solo hay {disp} u. (pediste {cant}); se cargó {disp}")
            cant = disp
        if cant > 0:
            items.append(item_desde_variante(v, cant))
    return items, avisos
