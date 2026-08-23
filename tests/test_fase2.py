"""Tests fase 2: overrides (catálogo/cliente/config), compra rápida, repetir pedido."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_KEY", "test-key-no-usar")

import catalog  # noqa: E402
import compra_rapida as cr  # noqa: E402
import overrides  # noqa: E402
import pedidos  # noqa: E402


def _df():
    rows = [
        ("M211", "Mochila Soft Rainbow", "Chimola", "2059", "AQUA", "U", "M211_U_2059", "779", 99, 32900.0, 10.0),
        ("M211", "Mochila Soft Rainbow", "Chimola", "2058", "RAINBOW", "U", "M211_U_2058", "780", 5, 32900.0, 10.0),
        ("VEST2", "Vestido Lino", "Lima", "2018", "GREEN", "8", "VEST2_8_2018", "", 3, 50000.0, 0.0),
    ]
    cols = ["producto_cod", "producto_nombre", "marca", "color_cod", "color", "talle", "sku", "ean",
            "stock", "precio1", "descvta"]
    df = pd.DataFrame(rows, columns=cols)
    for c in catalog.PRECIO_COLS:
        if c not in df:
            df[c] = 0.0
    df["temporada"] = "SS26"
    df["rubro"] = "X"
    df["subrubro"] = None
    df["descripcion"] = ""
    return df


def test_aplicar_overrides(monkeypatch):
    ov = {
        "M211": {"publicado": False},
        "VEST2": {"nombre": "Vestido Edit", "precios": {"1": 44000}, "destacado": True},
    }
    monkeypatch.setattr(overrides, "get_catalogo_overrides", lambda: ov)
    out = overrides.aplicar_overrides(_df())
    assert set(out["producto_cod"]) == {"VEST2"}                      # M211 oculto
    assert out.iloc[0]["producto_nombre"] == "Vestido Edit"           # nombre pisado
    assert out.iloc[0]["precio1"] == 44000 and out.iloc[0]["destacado"]
    todo = overrides.aplicar_overrides(_df(), incluir_ocultos=True)
    assert set(todo["producto_cod"]) == {"M211", "VEST2"}
    assert todo[todo.producto_cod == "M211"]["publicado"].iloc[0] is False
    # sin overrides → intacto
    monkeypatch.setattr(overrides, "get_catalogo_overrides", lambda: {})
    assert len(overrides.aplicar_overrides(_df())) == 3


def test_override_cliente(monkeypatch):
    monkeypatch.setattr(overrides, "get_clientes_overrides",
                        lambda: {2722: {"descuento_pct": 25.0, "lista_precios": 2}})
    c = overrides.aplicar_override_cliente({"cliente_cod": 2722, "descuento": 20.0, "lista_precios": 1})
    assert c["descuento"] == 25.0 and c["descuento_origen"] == "Override"
    assert c["lista_precios"] == 2 and c["lista_origen"] == "Override"
    c2 = overrides.aplicar_override_cliente({"cliente_cod": 2723, "descuento": 30.0, "lista_precios": 1})
    assert c2["descuento"] == 30.0 and c2["descuento_origen"] == "Aleph"


def test_con_precio_descvta():
    df = _df()
    sin = catalog.con_precio(df, 1, aplicar_descvta=False)
    con = catalog.con_precio(df, 1, aplicar_descvta=True)
    assert sin[sin.sku == "M211_U_2059"]["precio"].iloc[0] == 32900
    assert con[con.sku == "M211_U_2059"]["precio"].iloc[0] == pytest.approx(32900 * 0.9)
    assert con[con.sku == "VEST2_8_2018"]["precio"].iloc[0] == 50000   # descvta 0


def test_parsear_lineas():
    txt = "M211_U_2059,3\n779;2\nM211_U_2058\t4\nVEST2_8_2018 5\n\nXXX,abc\n"
    out = cr.parsear_lineas(txt)
    assert out == [("M211_U_2059", 3, 1), ("779", 2, 2), ("M211_U_2058", 4, 3),
                   ("VEST2_8_2018", 5, 4), ("XXX", -1, 6)]


def test_resolver_pegado():
    df = catalog.con_precio(_df(), 1, aplicar_descvta=False)
    items, avisos = cr.resolver_pegado("m211_u_2059,3\n779,2\nNOEXISTE,1\nM211_U_2058,99", df)
    por_sku = {i["sku"]: i for i in items}
    assert por_sku["M211_U_2059"]["cantidad"] == 5          # SKU + EAN consolidados
    assert por_sku["M211_U_2058"]["cantidad"] == 5          # recortado al stock
    assert any("NOEXISTE" in a for a in avisos) and any("solo hay 5" in a for a in avisos)


def test_repetir_pedido():
    df = catalog.con_precio(_df(), 1, aplicar_descvta=False)
    viejo = {"items": [
        {"sku": "M211_U_2059", "producto_nombre": "x", "color": "AQUA", "talle": "U", "cantidad": 3},
        {"sku": "M211_U_2058", "producto_nombre": "x", "color": "RAINBOW", "talle": "U", "cantidad": 10},
        {"sku": "YA_NO_EXISTE", "producto_nombre": "x", "color": "-", "talle": "U", "cantidad": 1},
    ]}
    items, avisos = pedidos.repetir_pedido(viejo, df)
    assert {i["sku"]: i["cantidad"] for i in items} == {"M211_U_2059": 3, "M211_U_2058": 5}
    assert items[0]["precio_unit"] == 32900                  # precio ACTUAL
    assert any("YA_NO_EXISTE" in a for a in avisos) and any("solo quedan 5" in a for a in avisos)


def test_estados_validos():
    assert pedidos.ESTADOS_SIGUIENTES["confirmado"] == ["procesado", "cancelado"]
    assert pedidos.ESTADOS_SIGUIENTES["cancelado"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
