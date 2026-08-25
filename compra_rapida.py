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
            "precio_unit": float(v["precio"]), "stock": int(v["stock"]),
            "manual": bool(v.get("es_manual", False))}


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


def resolver_pegado(texto: str, df_publicadas: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Texto pegado → (items de carrito, incidencias). Busca por SKU o EAN,
    consolida cantidades por SKU y recorta al stock.

    Cada incidencia (una por línea leída) es:
      {"linea": n, "codigo": str, "tipo": "ok"|"ajustada"|"no_encontrada"|
       "sin_precio"|"ilegible", "pedido": int, "cargado": int, "detalle": str}
    (una línea consolidada sobre un SKU repetido hereda el resultado final).
    """
    por_sku = {str(r["sku"]).upper(): r for _, r in df_publicadas.iterrows()}
    por_ean = {str(r["ean"]).upper(): r for _, r in df_publicadas.iterrows() if str(r["ean"]).strip()}
    incidencias: list[dict] = []
    pedidos: dict[str, int] = {}
    lineas_por_sku: dict[str, list[int]] = {}

    def inc(n, codigo, tipo, pedido, cargado, detalle):
        incidencias.append({"linea": n, "codigo": codigo, "tipo": tipo,
                            "pedido": pedido, "cargado": cargado, "detalle": detalle})

    for codigo, cant, n in parsear_lineas(texto):
        if cant == -1:
            inc(n, codigo, "ilegible", 0, 0, "cantidad ilegible")
            continue
        if cant <= 0:
            inc(n, codigo, "ilegible", cant, 0, "la cantidad debe ser mayor a 0")
            continue
        v = por_sku.get(codigo)
        if v is None:
            v = por_ean.get(codigo)
        if v is None:
            inc(n, codigo, "no_encontrada", cant, 0, "código no encontrado o sin stock publicado")
            continue
        sku = str(v["sku"])
        pedidos[sku] = pedidos.get(sku, 0) + cant
        lineas_por_sku.setdefault(sku, []).append(n)
        inc(n, codigo, "ok", cant, cant, "")   # provisional; se corrige abajo si hubo ajuste

    items = []
    for sku, cant in pedidos.items():
        v = por_sku[sku.upper()]
        propias = [i for i in incidencias if i["linea"] in lineas_por_sku[sku]]
        if pd.isna(v["precio"]):
            for i in propias:
                i.update(tipo="sin_precio", cargado=0, detalle="sin precio en tu lista — consultá a Chimola")
            continue
        disp = int(v["stock"])
        final = min(cant, disp)
        if final < cant:
            for i in propias:
                i.update(tipo="ajustada", cargado=final,
                         detalle=f"supera la cantidad disponible — se cargó {final} de {cant}")
        if final > 0:
            items.append(item_desde_variante(v, final))
        elif final == 0 and disp == 0:
            for i in propias:
                i.update(tipo="ajustada", cargado=0, detalle="sin stock disponible")
    return items, incidencias


def resumen_incidencias(incidencias: list[dict]) -> dict[str, int]:
    """{agregadas, ajustadas, sin_reconocer} para los contadores de la UI."""
    return {
        "agregadas": sum(1 for i in incidencias if i["tipo"] == "ok"),
        "ajustadas": sum(1 for i in incidencias if i["tipo"] == "ajustada"),
        "sin_reconocer": sum(1 for i in incidencias if i["tipo"] in ("no_encontrada", "sin_precio", "ilegible")),
    }
