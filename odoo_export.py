"""Export de un pedido en formato de importación masiva de Odoo (solo franquicias).

Calca las dos plantillas que usan las franquicias:
- hoja "Sin talle": Cliente | Producto ("Comodín") | Código | Color | Cantidad
  → productos de talle único.
- hoja "Indu":      Cliente | Talle | Producto (vacío) | Código | Color | Cantidad
  → productos con talle (una fila por talle).

Reglas: "Cliente" SOLO en la primera fila de cada hoja (las siguientes quedan
vacías = misma orden), sin totales ni filas extra; el nombre del cliente es el
de Odoo (`clientes_overrides.odoo_cliente`), no el de Aleph.
"""
from __future__ import annotations

import io

import xlsxwriter

COMODIN = "Comodín"
HOJA_SIN_TALLE = "Sin talle"
HOJA_INDU = "Indu"
CAB_SIN_TALLE = ["Cliente", "Líneas de la orden / Producto", "Líneas de la orden / Código Excel",
                 "Líneas de la orden / Color Excel", "Líneas de la orden / Cantidad"]
CAB_INDU = ["Cliente", "Líneas de la orden / Talle Excel", "Líneas de la orden / Producto",
            "Líneas de la orden / Código Excel", "Líneas de la orden / Color Excel",
            "Líneas de la orden / Cantidad"]
_SIN_TALLE = ("", "U", "UNICO", "ÚNICO")


def tiene_talle(item: dict) -> bool:
    """PURA: la variante tiene talle real (va a la hoja Indu)."""
    return str(item.get("talle") or "").strip().upper() not in _SIN_TALLE


def _talle(valor) -> int | str:
    t = str(valor).strip()
    return int(t) if t.isdigit() else t


def armar_filas(items: list[dict], cliente_odoo: str) -> tuple[list[list], list[list]]:
    """PURA: (filas hoja Sin talle, filas hoja Indu) sin cabecera. Cliente solo
    en la primera fila de cada hoja; el resto de esa columna vacío."""
    sin_talle, indu = [], []
    for it in items:
        cant = int(it.get("cantidad") or 0)
        if cant <= 0:
            continue
        cod = str(it.get("producto_cod") or "").strip()
        color = str(it.get("color") or "").strip()
        if tiene_talle(it):
            indu.append(["", _talle(it["talle"]), "", cod, color, cant])
        else:
            sin_talle.append(["", COMODIN, cod, color, cant])
    for filas in (sin_talle, indu):
        if filas:
            filas[0][0] = cliente_odoo
    return sin_talle, indu


def generar_excel_odoo(pedido: dict, cliente_odoo: str) -> bytes:
    """Excel de dos hojas, exactamente cabecera + filas (ninguna línea de más)."""
    sin_talle, indu = armar_filas(pedido.get("items") or [], cliente_odoo)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    for nombre, cab, filas in ((HOJA_SIN_TALLE, CAB_SIN_TALLE, sin_talle), (HOJA_INDU, CAB_INDU, indu)):
        ws = wb.add_worksheet(nombre)
        ws.write_row(0, 0, cab)
        for r, fila in enumerate(filas, start=1):
            ws.write_row(r, 0, fila)
        ws.set_column(0, 0, 34)
        ws.set_column(1, len(cab) - 1, 30)
    wb.close()
    return buf.getvalue()


def nombre_archivo(pedido: dict) -> str:
    return f"odoo_pedido_{int(pedido.get('numero') or 0):06d}.xlsx"
