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


# ---------------------------------------------------------------------------
# Excel de la compra rápida: exportar el filtro actual y re-importarlo editado
# ---------------------------------------------------------------------------
COLS_PLANTILLA = ["SKU", "EAN", "Código", "Producto", "Color", "Talle",
                  "Precio lista", "Cantidad", "Subtotal", "Foto"]


def _letra(idx: int) -> str:
    return chr(ord("A") + idx)


def excel_plantilla(df_variantes: pd.DataFrame, cantidades: dict[str, int] | None = None,
                    cliente: dict | None = None, iva_pct: float = 0.0,
                    links_foto: dict[str, str] | None = None,
                    miniaturas: dict[str, bytes] | None = None) -> bytes:
    """Excel editable del filtro actual, listo para completar offline y resubir.

    - Hoja «Compra rápida»: una fila por variante, Cantidad editable, Subtotal
      con fórmula (precio de la lista DEL CLIENTE × cantidad) y link «ver foto».
      Si `miniaturas` ({sku: bytes JPEG}), embebe la imagen en la columna A.
    - Hoja «Pedido»: totales en función del cliente (unidades, subtotal,
      descuento cabecera en %, TOTAL, IVA informativo) + listado dinámico de
      SOLO lo elegido (FILTER sobre Cantidad > 0; requiere Excel moderno).
    - Reimportable tal cual: la carga lee SKU/EAN + Cantidad de la hoja 1.
    """
    import io
    import xlsxwriter

    cant = cantidades or {}
    links = links_foto or {}
    minis = miniaturas or {}
    cli = cliente or {}
    desc = float(cli.get("descuento") or 0)
    lista = int(cli.get("lista_precios") or 1)
    off = 1 if minis else 0            # columna A reservada para la imagen
    C = {n: _letra(off + i) for i, n in enumerate(COLS_PLANTILLA)}
    n = len(df_variantes)

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    hdr = wb.add_format({"bold": True, "bottom": 1})
    plata = wb.add_format({"num_format": "$ #,##0"})
    ws = wb.add_worksheet("Compra rápida")
    if minis:
        ws.write(0, 0, "", hdr)
        ws.set_column(0, 0, 8.5)
    ws.write_row(0, off, COLS_PLANTILLA, hdr)
    for r, (_, v) in enumerate(df_variantes.iterrows(), start=1):
        sku = str(v["sku"])
        q = int(cant.get(sku, 0))
        precio = float(v["precio"]) if pd.notna(v.get("precio")) else 0.0
        ws.write_row(r, off, [sku, str(v.get("ean") or ""), str(v["producto_cod"]),
                             str(v.get("producto_nombre") or ""), str(v.get("color") or ""),
                             str(v.get("talle") or "")])
        ws.write_number(r, off + 6, precio, plata)
        ws.write_number(r, off + 7, q)
        ws.write_formula(r, off + 8, f"={C['Precio lista']}{r+1}*{C['Cantidad']}{r+1}",
                         plata, precio * q)
        url = links.get(sku)
        if url:
            ws.write_url(r, off + 9, url, string="ver foto")
        b = minis.get(sku)
        if b:
            ws.set_row(r, 34)
            ws.insert_image(r, 0, f"{sku}.jpg", {"image_data": io.BytesIO(b),
                                                 "x_offset": 3, "y_offset": 3,
                                                 "object_position": 1})
    ws.set_column(off, off, 18); ws.set_column(off + 1, off + 1, 15)
    ws.set_column(off + 3, off + 3, 34); ws.set_column(off + 4, off + 8, 11)
    ws.freeze_panes(1, 0)

    # ---- hoja Pedido: totales del cliente + solo lo elegido ----
    wp = wb.add_worksheet("Pedido")
    kick = wb.add_format({"bold": True})
    tot_u = sum(int(cant.get(str(v["sku"]), 0)) for _, v in df_variantes.iterrows())
    tot_s = sum(int(cant.get(str(v["sku"]), 0)) * (float(v["precio"]) if pd.notna(v.get("precio")) else 0)
                for _, v in df_variantes.iterrows())
    wp.write(0, 0, f"Pedido de {cli.get('nombre_display') or cli.get('nombre') or 'cliente'}", kick)
    wp.write(1, 0, f"Lista de precios {lista} · descuento cabecera {desc:g}%")
    rango_c = f"'Compra rápida'!{C['Cantidad']}2:{C['Cantidad']}{n+1}"
    rango_s = f"'Compra rápida'!{C['Subtotal']}2:{C['Subtotal']}{n+1}"
    filas_tot = [("Unidades", f"=SUM({rango_c})", tot_u, None),
                 (f"Subtotal (lista {lista}, sin IVA)", f"=SUM({rango_s})", tot_s, plata),
                 (f"Descuento cabecera {desc:g}%", f"=-B5*{desc}/100", -tot_s * desc / 100, plata),
                 ("TOTAL", "=B5+B6", tot_s * (1 - desc / 100), plata)]
    if iva_pct:
        filas_tot += [(f"IVA {iva_pct:g}% (informativo)", f"=B7*{iva_pct}/100",
                       tot_s * (1 - desc / 100) * iva_pct / 100, plata),
                      ("Total c/IVA", "=B7+B8", tot_s * (1 - desc / 100) * (1 + iva_pct / 100), plata)]
    for i, (lbl, f, valor, fmt) in enumerate(filas_tot, start=3):
        wp.write(i, 0, lbl, kick if lbl.startswith("TOTAL") else None)
        wp.write_formula(i, 1, f, fmt, valor)
    fila_h = len(filas_tot) + 4
    wp.write(fila_h, 0, "Solo lo elegido (Cantidad > 0) — se completa al abrir en Excel:", kick)
    wp.write_row(fila_h + 1, 0, COLS_PLANTILLA[:9], hdr)
    rango_t = f"'Compra rápida'!{C['SKU']}2:{C['Subtotal']}{n+1}"
    wp.write_dynamic_array_formula(fila_h + 2, 0, fila_h + 2, 0,
                                   f'=FILTER({rango_t},{rango_c}>0,"")')
    wp.set_column(0, 0, 30); wp.set_column(1, 8, 14); wp.set_column(3, 3, 34)
    wb.close()
    return buf.getvalue()


def texto_desde_excel(data: bytes) -> tuple[str, str | None]:
    """Excel exportado (o cualquiera con columnas SKU/EAN y Cantidad) →
    texto "codigo,cantidad" por línea para `resolver_pegado`. (texto, error)."""
    import io
    try:
        xl = pd.ExcelFile(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        return "", f"No pude leer el archivo: {e}"
    alguna_hoja_valida = False
    for hoja in xl.sheet_names:
        try:
            df = xl.parse(hoja)
        except Exception:  # noqa: BLE001
            continue
        cols = {str(c).strip().lower(): c for c in df.columns}
        col_cant = next((cols[k] for k in ("cantidad", "cant", "qty") if k in cols), None)
        col_cod = next((cols[k] for k in ("sku", "ean", "codigo", "código") if k in cols), None)
        if col_cant is None or col_cod is None:
            continue
        alguna_hoja_valida = True
        lineas = []
        for _, r in df.iterrows():
            try:
                c = int(float(r[col_cant])) if pd.notna(r[col_cant]) else 0
            except (TypeError, ValueError):
                continue
            if c > 0 and pd.notna(r[col_cod]):
                lineas.append(f"{str(r[col_cod]).strip()},{c}")
        if lineas:
            return "\n".join(lineas), None
    if alguna_hoja_valida:
        return "", None
    return "", "El archivo necesita una columna SKU (o EAN) y una columna Cantidad."
