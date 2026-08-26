"""Importar historial de comprobantes de Aleph como pedidos del sitio (fase 10).

Lee el espejo `central_raw` (ventassql/itemvensql) de BigQuery — nunca el SQL
Server directo — y crea pedidos con el formato del import de Kinderland:
estado `procesado`, historial `import-aleph`, Excel + backup en GCS.

Reglas:
- Solo comprobantes de VENTA: NP (tipo 90) y facturas (tipo 1), sin anulados
  (`fechaanu`) y con neto > 0.
- IDEMPOTENTE por `np_aleph`: un comprobante ya importado se saltea, nunca se
  duplica (pedir N de nuevo no repite).
- El pedido queda colgado del usuario del sitio asociado al cliente (si hay).
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from google.cloud import bigquery

import bq_client
import catalog
import config
import db
import pedidos

log = logging.getLogger(__name__)
TZ = ZoneInfo(config.TZ)
TIPO_DESC = {90: "NP", 1: "FA"}
_MAX_BYTES = 4_000_000_000   # itemvensql ~1.5 GB por scan (sin partición)

SQL_CABECERAS = f"""
SELECT SAFE_CAST(id AS INT64) id, SAFE_CAST(tipo AS INT64) tipo, TRIM(numero) numero,
       DATE(fecha) fecha, CAST(pordscto AS FLOAT64) pordscto, SAFE_CAST(lis_pre AS INT64) lis_pre
FROM `{config.BQ_PROJECT}.central_raw.ventassql`
WHERE SAFE_CAST(codigo AS INT64) = @cliente AND SAFE_CAST(tipo AS INT64) IN (1, 90)
  AND fechaanu IS NULL AND CAST(neto AS FLOAT64) > 0
ORDER BY fecha DESC
LIMIT @n
"""

SQL_ITEMS = f"""
SELECT SAFE_CAST(ventasid AS INT64) ventasid, TRIM(producto) producto,
       CAST(preuni AS FLOAT64) preuni, SAFE_CAST(cantidad AS INT64) cantidad,
       UPPER(REGEXP_REPLACE(TRIM(IFNULL(talle2, 'U')), r'\\s+', '')) talle,
       SAFE_CAST(color AS INT64) color_cod, SAFE_CAST(item AS INT64) item
FROM `{config.BQ_PROJECT}.central_raw.itemvensql`
WHERE SAFE_CAST(ventasid AS INT64) IN UNNEST(@ids)
ORDER BY ventasid, item
"""

SQL_NOMBRES = f"""
SELECT TRIM(codigo) codigo, TRIM(nombre) nombre
FROM `{config.BQ_PROJECT}.{config.DS_RAW}.articulosol`
WHERE TRIM(codigo) IN UNNEST(@cods)
"""

SQL_COLORES = f"""
SELECT SAFE_CAST(color_cod AS INT64) color_cod, TRIM(color) color
FROM `{config.BQ_PROJECT}.{config.DS_DWH}.dim_color`
WHERE SAFE_CAST(color_cod AS INT64) IN UNNEST(@cods)
"""


def np_ya_importadas() -> set[str]:
    """Números de comprobante ya importados (en cualquier pedido)."""
    out = set()
    for snap in db.client().collection(db.COL_PEDIDOS).stream():
        np = (snap.to_dict() or {}).get("np_aleph")
        if np:
            out.add(str(np))
    return out


def armar_pedido(cab: dict, items: list[dict], nombre_de: dict, color_de: dict,
                 cliente: dict, usuario_email: str, numero: int,
                 ahora: dt.datetime | None = None) -> dict:
    """PURA (testeable): arma el dict del pedido con el formato Kinderland."""
    pedido_items = []
    for r in items:
        cant = int(r["cantidad"])
        preuni = float(r["preuni"])
        ccod = int(r.get("color_cod") or 0)
        talle = str(r.get("talle") or "U")
        pedido_items.append({
            "sku": f"{r['producto']}_{talle}_{ccod}", "producto_cod": str(r["producto"]),
            "precio_unit": preuni, "subtotal": round(preuni * cant, 2), "ean": "",
            "cantidad": cant, "color": color_de.get(ccod, str(ccod)),
            "producto_nombre": nombre_de.get(str(r["producto"]), str(r["producto"])),
            "color_cod": str(ccod), "talle": talle})
    subtotal = round(sum(i["subtotal"] for i in pedido_items), 2)
    desc_pct = float(cab.get("pordscto") or 0)
    desc_monto = round(subtotal * desc_pct / 100, 2)
    f = cab["fecha"]
    confirmed = dt.datetime(f.year, f.month, f.day, 12, 0, tzinfo=TZ)
    tipo_d = TIPO_DESC.get(int(cab["tipo"]), str(cab["tipo"]))
    return {
        "numero": int(numero), "cliente_cod": int(cliente["cliente_cod"]),
        "cliente_cuit": str(cliente.get("cuit") or ""),
        "cliente_nombre": cliente.get("nombre_display") or cliente.get("nombre") or "",
        "usuario_email": usuario_email,
        "lista_precios": int(cab.get("lis_pre") or 1), "items": pedido_items,
        "subtotal": subtotal, "descuento_pct": desc_pct, "descuento_monto": desc_monto,
        "total": round(subtotal - desc_monto, 2),
        "unidades": sum(i["cantidad"] for i in pedido_items),
        "estado": "procesado", "env": config.APP_ENV, "np_aleph": str(cab["numero"]),
        "observaciones": f"Importado de Aleph — {tipo_d} {cab['numero']} del {f.strftime('%d/%m/%Y')}",
        "confirmed_at": confirmed, "created_at": confirmed,
        "fecha_str": f.strftime("%d/%m/%Y"),
        "historial": [{"estado": "procesado", "por": "import-aleph",
                       "en": ahora or dt.datetime.now(dt.timezone.utc)}],
        "email": {"enviado": False, "error": "importado de Aleph, sin email", "destinatarios": []},
    }


def importar(cliente_cod: int, n: int) -> list[str]:
    """Importa los últimos `n` comprobantes de venta del cliente. → mensajes."""
    msgs = []
    cliente = catalog.get_cliente(int(cliente_cod))
    if cliente is None:
        return [f"El cliente {cliente_cod} no existe en Aleph."]
    usuario_email = ""
    for snap in db.client().collection(db.COL_USUARIOS).stream():
        if (snap.to_dict() or {}).get("cliente_cod") == int(cliente_cod):
            usuario_email = snap.id
            break

    cab = bq_client.query(SQL_CABECERAS, [
        bigquery.ScalarQueryParameter("cliente", "INT64", int(cliente_cod)),
        bigquery.ScalarQueryParameter("n", "INT64", int(n)),
    ], max_bytes=_MAX_BYTES)
    if cab.empty:
        return ["Este cliente no tiene comprobantes de venta (NP/FA) en Aleph."]

    existentes = np_ya_importadas()
    for _, c in cab.iterrows():
        if str(c["numero"]) in existentes:
            msgs.append(f"{TIPO_DESC.get(int(c['tipo']), c['tipo'])} {c['numero']} "
                        f"({c['fecha'].strftime('%d/%m/%Y')}): ya estaba importada — salteada.")
    pendientes = cab[~cab["numero"].astype(str).isin(existentes)]
    if pendientes.empty:
        msgs.append("Nada nuevo para importar.")
        return msgs

    ids = [int(x) for x in pendientes["id"]]
    items = bq_client.query(SQL_ITEMS, [bigquery.ArrayQueryParameter("ids", "INT64", ids)],
                            max_bytes=_MAX_BYTES)
    nombres = bq_client.query(SQL_NOMBRES, [bigquery.ArrayQueryParameter(
        "cods", "STRING", sorted({str(p) for p in items["producto"]}))])
    nombre_de = dict(zip(nombres["codigo"], nombres["nombre"]))
    ccods = sorted({int(c) for c in items["color_cod"].dropna()})
    colores = bq_client.query(SQL_COLORES, [bigquery.ArrayQueryParameter("cods", "INT64", ccods)]) \
        if ccods else None
    color_de = dict(zip(colores["color_cod"], colores["color"])) if colores is not None else {}

    for _, c in pendientes.sort_values("fecha").iterrows():
        its = items[items["ventasid"] == int(c["id"])].to_dict("records")
        if not its:
            msgs.append(f"{c['numero']}: sin líneas en itemvensql — salteada.")
            continue
        numero = db.proximo_numero_pedido()
        p = armar_pedido(c.to_dict(), its, nombre_de, color_de, cliente, usuario_email, numero)
        p["xlsx_filename"] = pedidos.nombre_archivo(p)
        xlsx = pedidos.generar_excel(p)
        p["xlsx_gcs_path"] = pedidos.subir_backup(pedidos.gcs_path(p), xlsx)
        db.client().collection(db.COL_PEDIDOS).document(f"{numero:06d}").set(p)
        log.info("Importado %s como pedido %06d (cliente %s)", p["np_aleph"], numero, cliente_cod)
        msgs.append(f"Pedido {numero:06d} creado desde {TIPO_DESC.get(int(c['tipo']), c['tipo'])} "
                    f"{c['numero']} ({c['fecha'].strftime('%d/%m/%Y')}) · "
                    f"{len(its)} items · {p['unidades']} u. · total $ {p['total']:,.0f}.")
    return msgs
