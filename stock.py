"""Validación de stock en vivo al confirmar (evita oversell entre que el cliente
armó el carrito con el catálogo cacheado y confirma)."""
from __future__ import annotations

import logging

from google.cloud import bigquery

import bq_client
import config
from catalog import SQL_CTE_STOCK_NETO

log = logging.getLogger(__name__)

SQL_STOCK_SKUS = f"""
WITH {SQL_CTE_STOCK_NETO}
SELECT sku, stock FROM variantes WHERE sku IN UNNEST(@skus)
"""


def stock_actual(skus: list[str]) -> dict[str, int]:
    """Stock efectivo actual por SKU (sin cache). SKUs que no aparecen → 0.
    Aplica los overrides de variante del admin (SPECS §3): stock manual
    REEMPLAZA al neto de BQ y una variante oculta vale 0 — así la validación
    al confirmar es consistente con lo que ve el cliente."""
    if not skus:
        return {}
    import overrides

    df = bq_client.query(SQL_STOCK_SKUS, [bigquery.ArrayQueryParameter("skus", "STRING", list(skus))])
    actual = {r["sku"]: int(r["stock"]) for _, r in df.iterrows()}
    stock_map, ocultas, _ = overrides.variantes_overrides()
    out = {}
    for s in skus:
        if s in ocultas:
            out[s] = 0
        elif s in stock_map:
            out[s] = stock_map[s]
        else:
            out[s] = actual.get(s, 0)
    return out


def validar_stock(items: list[dict]) -> list[dict]:
    """Devuelve la lista de items con problemas: [{sku, pedido, disponible}].
    Lista vacía = todo OK."""
    actual = stock_actual([i["sku"] for i in items])
    problemas = []
    for it in items:
        disp = actual.get(it["sku"], 0)
        if int(it["cantidad"]) > disp:
            problemas.append({"sku": it["sku"], "pedido": int(it["cantidad"]), "disponible": disp})
    if problemas:
        log.warning("Stock insuficiente en %d items: %s", len(problemas), problemas)
    return problemas
