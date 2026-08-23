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
    """Stock neto actual por SKU (sin cache). SKUs que no aparecen → 0."""
    if not skus:
        return {}
    df = bq_client.query(SQL_STOCK_SKUS, [bigquery.ArrayQueryParameter("skus", "STRING", list(skus))])
    actual = {r["sku"]: int(r["stock"]) for _, r in df.iterrows()}
    return {s: actual.get(s, 0) for s in skus}


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
