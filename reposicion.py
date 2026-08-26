"""Reposición sugerida para FRANQUICIAS (fase 11).

Cruza el sell-out de la sucursal del cliente (marts
`v_reposicion_sku_omnicanal`, calculada por el pipeline hermano) con el
catálogo vendible del sitio, y sugiere cantidades:

    sugerido = ceil(velocidad_30d × días_objetivo − stock_sucursal)
               → redondeado ARRIBA al múltiplo U.B.
               → capeado al stock neto vendible del sitio (sin mostrarlo)

Solo aplica a clientes titulares de un punto de venta (`dim_pv`).
Gotchas: el `sku` de la vista es el EAN (fallback: producto+color+talle);
`unidades_en_stock` puede venir negativo (ajustes contables) → se toma 0.
"""
from __future__ import annotations

import logging
import math
import threading
import time

import pandas as pd
from google.cloud import bigquery

import bq_client
import config
import fotos

log = logging.getLogger(__name__)
_MAX_BYTES = 2_000_000_000
_TTL = 900   # 15 min

SQL_PVS = f"""
SELECT SAFE_CAST(pv_cod AS INT64) pv_cod, TRIM(pv_nombre) pv_nombre,
       SAFE_CAST(cliente_cod_titular AS INT64) cliente_cod
FROM `{config.BQ_PROJECT}.{config.DS_DWH}.dim_pv`
WHERE cliente_cod_titular IS NOT NULL
"""

SQL_REPO = f"""
SELECT TRIM(sku) ean, TRIM(producto_cod) producto_cod, UPPER(TRIM(color)) color,
       UPPER(REGEXP_REPLACE(TRIM(IFNULL(talle, 'U')), r'\\s+', '')) talle,
       SAFE_CAST(unidades_en_stock AS INT64) stock_pv,
       SAFE_CAST(unidades_vendidas_30d AS INT64) vendidas_30d,
       CAST(velocidad_venta_diaria_30d AS FLOAT64) vel_30d,
       CAST(cobertura_dias AS FLOAT64) cobertura_dias
FROM `{config.BQ_PROJECT}.{config.DS_MARTS}.v_reposicion_sku_omnicanal`
WHERE pv_cod = @pv AND unidades_vendidas_30d > 0
"""

_lock = threading.Lock()
_pvs: dict | None = None
_pvs_ts = 0.0
_repo_cache: dict[int, tuple[pd.DataFrame, float]] = {}


def pv_de_cliente(cliente_cod: int) -> dict | None:
    """{pv_cod, pv_nombre} si el cliente es titular de un punto de venta."""
    global _pvs, _pvs_ts
    with _lock:
        if _pvs is None or time.time() - _pvs_ts > 3600:
            df = bq_client.query(SQL_PVS)
            _pvs = {int(r["cliente_cod"]): {"pv_cod": int(r["pv_cod"]), "pv_nombre": r["pv_nombre"]}
                    for _, r in df.iterrows() if pd.notna(r["cliente_cod"])}
            _pvs_ts = time.time()
    return _pvs.get(int(cliente_cod))


def _vista_pv(pv_cod: int) -> pd.DataFrame:
    with _lock:
        hit = _repo_cache.get(pv_cod)
        if hit and time.time() - hit[1] < _TTL:
            return hit[0]
    df = bq_client.query(SQL_REPO, [bigquery.ScalarQueryParameter("pv", "INT64", int(pv_cod))],
                         max_bytes=_MAX_BYTES)
    with _lock:
        _repo_cache[pv_cod] = (df, time.time())
    return df


def calcular_sugerido(vel_30d: float, stock_pv: int, dias_objetivo: int,
                      ub: int, tope: int) -> int:
    """PURA: cantidad sugerida para una variante (0 si no hace falta/no hay)."""
    necesidad = math.ceil(float(vel_30d or 0) * int(dias_objetivo) - max(0, int(stock_pv or 0)))
    if necesidad <= 0 or tope <= 0:
        return 0
    ub = max(1, int(ub or 1))
    sugerido = math.ceil(necesidad / ub) * ub   # redondeo ARRIBA al múltiplo
    return min(sugerido, (tope // ub) * ub if ub > 1 else tope)


def cruzar_con_catalogo(vista: pd.DataFrame, cat: pd.DataFrame) -> pd.DataFrame:
    """PURA: matchea filas de la vista con el catálogo vendible del sitio.
    1º por EAN (el `sku` de la vista ES el EAN); 2º por (producto_cod, color,
    talle). Devuelve el catálogo enriquecido con stock_pv / vendidas_30d /
    vel_30d / cobertura_dias, ordenado por urgencia (cobertura asc)."""
    extra = ["stock_pv", "vendidas_30d", "vel_30d", "cobertura_dias"]
    por_ean = vista[vista["ean"].str.len() > 0].drop_duplicates("ean").set_index("ean")
    m1 = cat.merge(por_ean[extra], left_on="ean", right_index=True, how="inner")
    resto = vista[~vista["ean"].isin(set(m1["ean"]))]
    m2 = cat[~cat["sku"].isin(set(m1["sku"]))].merge(
        resto[["producto_cod", "color", "talle"] + extra].drop_duplicates(
            ["producto_cod", "color", "talle"]),
        on=["producto_cod", "color", "talle"], how="inner")
    out = pd.concat([m1, m2], ignore_index=True)
    return out.sort_values("cobertura_dias", na_position="last")


def sugerencias(cliente_cod: int, df_catalogo: pd.DataFrame, dias_objetivo: int = 21) -> tuple:
    """(pv, DataFrame de sugerencias) para la página de Reposición.
    df_catalogo: variantes del sitio CON columna `precio` del cliente."""
    pv = pv_de_cliente(int(cliente_cod))
    if pv is None:
        return None, pd.DataFrame()
    vista = _vista_pv(pv["pv_cod"])
    if vista.empty:
        return pv, pd.DataFrame()
    cruce = cruzar_con_catalogo(vista, df_catalogo[df_catalogo["precio"].notna()])
    if cruce.empty:
        return pv, cruce
    cruce["sugerido"] = [
        calcular_sugerido(r["vel_30d"], r["stock_pv"], dias_objetivo,
                          int(r["ub"]) if "ub" in cruce.columns and pd.notna(r.get("ub")) and r.get("ub") else 1,
                          int(r["stock"]))
        for _, r in cruce.iterrows()]
    cruce = cruce[cruce["sugerido"] > 0].copy()
    cruce["foto"] = cruce.apply(
        lambda r: fotos.miniatura(r["producto_cod"], r["color"]) if fotos.tiene_fotos(r["producto_cod"]) else "",
        axis=1)
    return pv, cruce
