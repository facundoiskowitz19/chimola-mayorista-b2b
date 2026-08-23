"""Tests de lógica pura (sin GCP): precios, filtros, SKU, fotos, totales, Excel, JWT."""
from __future__ import annotations

import datetime as dt
import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_KEY", "test-key-no-usar")

import auth  # noqa: E402
import catalog  # noqa: E402
import fotos  # noqa: E402
import pedidos  # noqa: E402


def _df():
    rows = [
        # producto, nombre, marca, temporada, rubro, subrubro, color_cod, color, talle, sku, ean, stock, precio1, precio4
        ("M211", "Mochila Soft Rainbow", "Chimola", "DDN25", "Mochilas", None, "2059", "AQUA", "U", "M211_U_2059", "779", 99, 32900, 65800),
        ("M211", "Mochila Soft Rainbow", "Chimola", "DDN25", "Mochilas", None, "2058", "RAINBOW", "U", "M211_U_2058", "780", 107, 32900, 65800),
        ("VEST2", "Vestido Lino", "Lima", "AW26", "Vestidos", None, "2018", "GREEN", "8", "VEST2_8_2018", "", 3, 0, 50000),
        ("VEST2", "Vestido Lino", "Lima", "AW26", "Vestidos", None, "2018", "GREEN", "10", "VEST2_10_2018", "", 2, 0, 50000),
    ]
    cols = ["producto_cod", "producto_nombre", "marca", "temporada", "rubro", "subrubro", "color_cod", "color",
            "talle", "sku", "ean", "stock", "precio1", "precio4"]
    df = pd.DataFrame(rows, columns=cols)
    for c in catalog.PRECIO_COLS:
        if c not in df:
            df[c] = 0.0
    df["descvta"] = 0.0
    df["descripcion"] = ""
    return df


def test_precio_por_lista_y_sin_precio():
    df = catalog.con_precio(_df(), 1)
    assert df.loc[df.sku == "M211_U_2059", "precio"].iloc[0] == 32900
    assert pd.isna(df.loc[df.sku == "VEST2_8_2018", "precio"].iloc[0])  # lista 1 sin precio → no se vende
    df4 = catalog.con_precio(_df(), 4)
    assert df4.loc[df4.sku == "VEST2_8_2018", "precio"].iloc[0] == 50000
    assert catalog.columna_precio(0) == "precio1" and catalog.columna_precio(11) == "precio1"


def test_descuento_cabecera():
    assert catalog.aplicar_descuento(1000, 30) == 700
    assert catalog.aplicar_descuento(1000, 0) == 1000
    assert catalog.aplicar_descuento(32900, 20) == 26320


def test_filtros_y_busqueda():
    df = catalog.con_precio(_df(), 1)
    assert len(catalog.filtrar_variantes(df, {"marca": ["Lima"]})) == 2
    assert len(catalog.filtrar_variantes(df, {}, "m211 rainbow")) == 2  # el nombre también dice Rainbow
    assert len(catalog.filtrar_variantes(df, {}, "m211 aqua")) == 1
    assert len(catalog.filtrar_variantes(df, {}, "779")) == 1
    ops = catalog.opciones_filtros(df, {"marca": ["Lima"]})
    assert ops["temporada"] == ["AW26"] and ops["marca"] == ["Chimola", "Lima"]


def test_productos_agregado_y_detalle():
    df = catalog.con_precio(_df(), 1)
    p = catalog.productos(df)
    m = p[p.producto_cod == "M211"].iloc[0]
    assert m.stock == 206 and m.n_variantes == 2 and m.colores == ["AQUA", "RAINBOW"]
    d = catalog.get_producto(df, "VEST2")
    assert d["precio"] is None and d["talles"] == ["8", "10"]
    assert catalog.get_producto(df, "NOEXISTE") is None


def test_parseo_fotos():
    files = ["M211 AQUA (2).jpg", "M211 AQUA (1).jpg", "M211 LIGHT PINK (1).jpg", "M211 allcolors.jpg", "notas.txt.jpg"]
    out = fotos.parsear_fotos("M211", files, ["AQUA", "LIGHT PINK"])
    assert out[0]["filename"] == "M211 allcolors.jpg" and out[0]["is_cover"]
    aqua = fotos.fotos_por_color(out, "Aqua")
    assert [f["filename"] for f in aqua] == ["M211 AQUA (1).jpg", "M211 AQUA (2).jpg"]
    pink = fotos.fotos_por_color(out, "LIGHT PINK")
    assert [f["filename"] for f in pink] == ["M211 LIGHT PINK (1).jpg"]
    # sin paréntesis: "L11 VISON.jpg" → color VISON
    out2 = fotos.parsear_fotos("L11", ["L11 VISON.jpg", "L11 MINT (2).jpg"], ["VISON", "MINT"])
    assert {f["color_norm"] for f in out2} == {"VISON", "MINT"}
    assert fotos.parsear_fotos("X", []) == []
    assert fotos.norm("Light  Pink") == "LIGHTPINK" and fmt_ok()


def fmt_ok():
    return fotos.norm("Visón") == "VISON"


def test_carrito_y_totales():
    items = pedidos.agregar_al_carrito([], {"sku": "A", "cantidad": 2, "precio_unit": 100, "stock": 10})
    items = pedidos.agregar_al_carrito(items, {"sku": "A", "cantidad": 3, "precio_unit": 100, "stock": 10})
    items = pedidos.agregar_al_carrito(items, {"sku": "B", "cantidad": 1, "precio_unit": 50.5, "stock": 1})
    assert len(items) == 2 and items[0]["cantidad"] == 5
    tot = pedidos.calcular_totales(items, 30)
    assert tot["unidades"] == 6 and tot["subtotal"] == 550.5
    assert tot["total"] == round(550.5 * 0.7, 2) and tot["descuento_monto"] == round(550.5 - tot["total"], 2)


def _pedido():
    ahora = dt.datetime(2026, 8, 21, 15, 30, tzinfo=dt.timezone.utc)
    items = [
        {"sku": "M211_U_2059", "ean": "779", "producto_cod": "M211", "producto_nombre": "Mochila Soft Rainbow",
         "color_cod": "2059", "color": "AQUA", "talle": "U", "cantidad": 3, "precio_unit": 32900.0},
        {"sku": "M211_U_2058", "ean": "780", "producto_cod": "M211", "producto_nombre": "Mochila Soft Rainbow",
         "color_cod": "2058", "color": "RAINBOW", "talle": "U", "cantidad": 1, "precio_unit": 32900.0},
    ]
    tot = pedidos.calcular_totales(items, 20)
    p = {"numero": 12, "cliente_cod": 2722, "cliente_nombre": "Franquicia Jujuy", "cliente_cuit": "30-1",
         "usuario_email": "x@y.com", "lista_precios": 1, "items": items, **tot, "estado": "confirmado",
         "observaciones": "urgente", "confirmed_at": ahora, "fecha_str": "21/08/2026 12:30"}
    p["xlsx_filename"] = pedidos.nombre_archivo(p)
    return p


def test_excel_y_nombres():
    p = _pedido()
    assert p["xlsx_filename"] == "pedido_2722_12_20260821_123000.xlsx"
    assert pedidos.gcs_path(p) == "2026-08/pedido_2722_12_20260821_123000.xlsx"
    data = pedidos.generar_excel(p)
    assert data[:2] == b"PK" and len(data) > 2000
    import openpyxl  # viene con pandas? no siempre — si falta, solo validamos el zip
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Resumen", "Detalle"]
    det = wb["Detalle"]
    assert det["A2"].value == "M211" and det["H2"].value == 3 and det["I2"].value == 32900
    res = wb["Resumen"]
    vals = {res.cell(r, 1).value: res.cell(r, 2).value for r in range(1, 25)}
    assert vals["TOTAL"] == p["total"] == round(4 * 32900 * 0.8, 2)


def test_password_y_jwt():
    h = auth.hash_password("secreta123")
    assert auth.verify_password("secreta123", h) and not auth.verify_password("otra", h)
    assert not auth.verify_password("x", None)
    tok = auth.create_jwt({"email": "a@b.com", "cliente_cod": 2722, "rol": "cliente", "nombre_display": "A"})
    claims = auth.verify_jwt(tok)
    assert claims["sub"] == "a@b.com" and claims["cliente_cod"] == 2722
    assert auth.verify_jwt(tok + "x") is None and auth.verify_jwt(None) is None
    vencido = auth.create_jwt({"email": "a@b.com", "cliente_cod": 1}, ttl_hours=-1)
    assert auth.verify_jwt(vencido) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
