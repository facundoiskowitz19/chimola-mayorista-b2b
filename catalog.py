"""Catálogo B2B: query base a BigQuery (1 fila por variante con stock neto en
Ezeiza) + helpers de filtrado/precio en pandas.

Reglas (ver CLAUDE.md):
- Stock B2B = stock_ezeiza NETO de OC pendientes (misma lógica que el pipeline Woo).
- SKU = {producto_cod}_{TALLE}_{color_cod}.
- Precio = precio{N} de articulosol según dim_cliente.lista_precios (1..10).
  `dim_producto` solo expone la lista 4, por eso vamos a la raw.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import pandas as pd
from google.cloud import bigquery

import bq_client
import config
import overrides

log = logging.getLogger(__name__)

# CTEs compartidos con stock.py: stock físico neto de OC por variante.
SQL_CTE_STOCK_NETO = f"""
oc_snap AS (
  SELECT MAX(fecha_snapshot) AS fecha FROM {config.V_STOCK_CENTRAL}
),
oc_pendiente AS (
  SELECT st.producto AS producto_cod, st.color AS color_cod, st.talle2 AS talle, SUM(st.oc) AS oc
  FROM {config.T_STOCK_RAW} st
  CROSS JOIN oc_snap
  WHERE st.deposito = 1 AND DATE(st._ingested_at) = oc_snap.fecha
  GROUP BY 1, 2, 3
),
variantes AS (
  SELECT
    s.producto_cod,
    TRIM(s.producto_nombre)                                   AS producto_nombre,
    s.marca, s.temporada, s.rubro, s.subrubro,
    s.color_cod,
    UPPER(TRIM(s.color))                                      AS color,
    UPPER(REGEXP_REPLACE(TRIM(IFNULL(s.talle, '')), r'\\s+', '')) AS talle,
    CONCAT(s.producto_cod, '_',
           UPPER(REGEXP_REPLACE(TRIM(IFNULL(s.talle, '')), r'\\s+', '')), '_',
           CAST(s.color_cod AS STRING))                       AS sku,
    TRIM(IFNULL(s.sku, ''))                                   AS ean,
    CAST(GREATEST(s.stock_ezeiza - IFNULL(oc.oc, 0), 0) AS INT64) AS stock
  FROM {config.V_STOCK_OMNI} s
  LEFT JOIN oc_pendiente oc
    ON oc.producto_cod = s.producto_cod AND oc.color_cod = s.color_cod AND oc.talle = s.talle
  WHERE s.producto_nombre IS NOT NULL AND s.color IS NOT NULL AND s.talle IS NOT NULL
    AND s.stock_ezeiza > 0
)
"""

PRECIO_COLS = [f"precio{i}" for i in range(1, 11)]

SQL_CATALOGO = f"""
WITH {SQL_CTE_STOCK_NETO}
SELECT
  v.*,
  {", ".join(f"CAST(a.{c} AS FLOAT64) AS {c}" for c in PRECIO_COLS)},
  CAST(a.descvta AS FLOAT64)            AS descvta,
  TRIM(IFNULL(a.observa, ''))           AS descripcion
FROM variantes v
LEFT JOIN {config.T_ARTICULOSOL} a ON a.codigo = v.producto_cod
WHERE v.stock > 0
ORDER BY v.producto_cod, v.color, v.talle
"""

SQL_CLIENTE = f"""
SELECT cliente_cod, nombre, fantasia, email, lista_precios, descuento,
       localidad, provincia_desc, direccion, cuit
FROM {config.T_DIM_CLIENTE}
WHERE cliente_cod = @cliente_cod
"""

SQL_CLIENTES = f"""
SELECT cliente_cod, nombre, fantasia, email, lista_precios, descuento,
       localidad, provincia_desc, direccion, cuit
FROM {config.T_DIM_CLIENTE}
-- cliente_cod es NUMERIC en BQ: sin CAST, `IN UNNEST(ARRAY<INT64>)` da BadRequest
WHERE CAST(cliente_cod AS INT64) IN UNNEST(@cods)
"""


# ---------------------------------------------------------------------------
# Cache simple con TTL (process-wide, thread-safe). Independiente de Streamlit.
# ---------------------------------------------------------------------------
@dataclass
class _Cache:
    df: pd.DataFrame | None = None
    ts: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


_cache = _Cache()


def load_variantes(force: bool = False) -> pd.DataFrame:
    """Todas las variantes con stock B2B > 0 (cache TTL `CATALOGO_TTL_SEG`)."""
    with _cache.lock:
        vigente = _cache.df is not None and (time.time() - _cache.ts) < config.CATALOGO_TTL_SEG
        if vigente and not force:
            return _cache.df
        t0 = time.time()
        df = bq_client.query(SQL_CATALOGO)
        for c in PRECIO_COLS + ["descvta"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df["stock"] = df["stock"].astype(int)
        df["color_cod"] = df["color_cod"].astype(str)
        _cache.df, _cache.ts = df, time.time()
        log.info("Catálogo cargado: %d variantes / %d productos en %.1fs",
                 len(df), df["producto_cod"].nunique(), time.time() - t0)
        return df


def catalogo_actualizado_hace() -> int:
    """Segundos desde la última carga (para mostrar en UI)."""
    return int(time.time() - _cache.ts) if _cache.df is not None else -1


def variantes_publicadas(force: bool = False) -> pd.DataFrame:
    """Catálogo visible para clientes: BQ (cache 30 min) + overrides admin
    (cache 60 s): ocultos filtrados, nombre/descripcion/precios pisados,
    columna `destacado`."""
    return overrides.aplicar_overrides(load_variantes(force=force))


def variantes_admin(force: bool = False) -> pd.DataFrame:
    """Como variantes_publicadas pero INCLUYE ocultos (vista admin)."""
    return overrides.aplicar_overrides(load_variantes(force=force), incluir_ocultos=True)


# ---------------------------------------------------------------------------
# Cliente / precios
# ---------------------------------------------------------------------------
def get_cliente(cliente_cod: int) -> dict | None:
    df = bq_client.query(SQL_CLIENTE, [bigquery.ScalarQueryParameter("cliente_cod", "INT64", int(cliente_cod))])
    if df.empty:
        return None
    r = df.iloc[0].to_dict()
    r["lista_precios"] = int(r.get("lista_precios") or 1)
    r["descuento"] = float(r.get("descuento") or 0)
    r["cliente_cod"] = int(r["cliente_cod"])
    # Razón social como display (la fantasía en Aleph suele ser un apodo interno, ej: "GENTILE").
    r["nombre_display"] = (r.get("nombre") or r.get("fantasia") or f"Cliente {cliente_cod}").strip()
    return overrides.aplicar_override_cliente(r)


def get_clientes(cods: list[int]) -> dict[int, dict]:
    """Batch: {cliente_cod: dict efectivo (con overrides)} en 1 sola query BQ."""
    if not cods:
        return {}
    df = bq_client.query(SQL_CLIENTES, [bigquery.ArrayQueryParameter("cods", "INT64", [int(c) for c in cods])])
    out = {}
    for _, row in df.iterrows():
        r = row.to_dict()
        r["lista_precios"] = int(r.get("lista_precios") or 1)
        r["descuento"] = float(r.get("descuento") or 0)
        r["cliente_cod"] = int(r["cliente_cod"])
        r["nombre_display"] = (r.get("nombre") or r.get("fantasia") or f"Cliente {r['cliente_cod']}").strip()
        out[r["cliente_cod"]] = overrides.aplicar_override_cliente(r)
    return out


def columna_precio(lista_precios: int) -> str:
    n = int(lista_precios) if lista_precios else 1
    if n < 1 or n > 10:
        n = 1
    return f"precio{n}"


def con_precio(df: pd.DataFrame, lista_precios: int, aplicar_descvta: bool | None = None) -> pd.DataFrame:
    """Agrega columna `precio` (precio de lista del cliente, sin descuento
    cabecera). Si la lista no tiene precio cargado (0) queda NaN → no se vende.
    Si config/global.aplicar_descvta está activo, aplica además el descuento
    por artículo de Aleph (descvta), como hace el pipeline Woo."""
    col = columna_precio(lista_precios)
    out = df.copy()
    precio = out[col].where(out[col] > 0)
    if aplicar_descvta is None:
        try:
            aplicar_descvta = bool(overrides.get_config().get("aplicar_descvta"))
        except Exception:  # noqa: BLE001 — sin Firestore (tests/local aislado)
            aplicar_descvta = False
    if aplicar_descvta and "descvta" in out.columns:
        precio = (precio * (1 - out["descvta"].clip(lower=0, upper=90) / 100)).round(2)
    out["precio"] = precio
    return out


def aplicar_descuento(monto: float, descuento_pct: float) -> float:
    return round(float(monto) * (1 - float(descuento_pct or 0) / 100), 2)


# ---------------------------------------------------------------------------
# Filtros y agregación a nivel producto
# ---------------------------------------------------------------------------
FILTROS = ["marca", "temporada", "rubro", "subrubro"]


def opciones_filtros(df: pd.DataFrame, seleccion: dict | None = None) -> dict[str, list[str]]:
    """Valores disponibles por filtro (facetado: respeta las otras selecciones)."""
    seleccion = seleccion or {}
    out = {}
    for f in FILTROS:
        sub = df
        for g, vals in seleccion.items():
            if g != f and vals:
                sub = sub[sub[g].isin(vals)]
        vals = sorted(v for v in sub[f].dropna().unique() if str(v).strip())
        out[f] = vals
    return out


def _matches_busqueda(df: pd.DataFrame, texto: str) -> pd.Series:
    t = (texto or "").strip().lower()
    if not t:
        return pd.Series(True, index=df.index)
    tokens = t.split()
    hay = (df["producto_cod"].str.lower() + " " + df["producto_nombre"].str.lower()
           + " " + df["ean"].str.lower() + " " + df["color"].str.lower())
    mask = pd.Series(True, index=df.index)
    for tok in tokens:
        mask &= hay.str.contains(tok, regex=False)
    return mask


def filtrar_variantes(df: pd.DataFrame, seleccion: dict | None = None, busqueda: str = "") -> pd.DataFrame:
    sub = df
    for f, vals in (seleccion or {}).items():
        if vals:
            sub = sub[sub[f].isin(vals)]
    return sub[_matches_busqueda(sub, busqueda)]


def productos(df_variantes: pd.DataFrame) -> pd.DataFrame:
    """1 fila por producto: nombre, atributos, precio (min), stock total, colores."""
    if df_variantes.empty:
        return pd.DataFrame(columns=["producto_cod", "producto_nombre", "marca", "temporada", "rubro",
                                     "subrubro", "precio", "stock", "n_variantes", "colores"])
    g = df_variantes.groupby("producto_cod", sort=True)
    out = g.agg(
        producto_nombre=("producto_nombre", "first"),
        marca=("marca", "first"),
        temporada=("temporada", "first"),
        rubro=("rubro", "first"),
        subrubro=("subrubro", "first"),
        precio=("precio", "min"),
        stock=("stock", "sum"),
        n_variantes=("sku", "count"),
        colores=("color", lambda s: sorted(set(s))),
    ).reset_index()
    return out


_ORDEN_TALLES = {t: i for i, t in enumerate(["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "U"])}


def talle_key(t: str) -> tuple:
    """Orden natural de talles: numéricos ascendentes, después XS<S<M<L<XL..., U al final."""
    t = str(t or "").strip().upper()
    try:
        return (0, float(t), "")
    except ValueError:
        return (1, _ORDEN_TALLES.get(t, 50), t)


def get_producto(df: pd.DataFrame, producto_cod: str) -> dict | None:
    sub = df[df["producto_cod"] == producto_cod].copy()
    sub["_tk"] = sub["talle"].map(talle_key)
    sub = sub.sort_values(["color", "_tk"]).drop(columns="_tk")
    if sub.empty:
        return None
    first = sub.iloc[0]
    ub = first.get("ub") if "ub" in sub.columns else None
    return {
        "producto_cod": producto_cod,
        "producto_nombre": first["producto_nombre"],
        "marca": first["marca"], "temporada": first["temporada"],
        "rubro": first["rubro"], "subrubro": first["subrubro"],
        "descripcion": first.get("descripcion", ""),
        "ub": int(ub) if pd.notna(ub) and ub else None,
        "precio": float(first["precio"]) if pd.notna(first["precio"]) else None,
        "variantes": sub[["sku", "ean", "color_cod", "color", "talle", "stock", "precio"]].to_dict("records"),
        "colores": sorted(sub["color"].unique()),
        "talles": list(dict.fromkeys(sub["talle"])),
    }
