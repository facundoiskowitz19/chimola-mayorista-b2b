"""Tests de lógica pura agregados en la QA del rediseño (2026-10-07): medidas, parser de
ficha, curva proporcional, modelos estrictos de home/menú del admin."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_KEY", "test-key-no-usar")

import catalog  # noqa: E402


def test_medidas_formato_ancho_alto_prof():
    assert catalog.medidas_formato(29, 25, 3) == "25 × 29 × 3 cm"
    assert catalog.medidas_formato(14.5, 20, 3) == "20 × 14,5 × 3 cm"


@pytest.mark.parametrize("alto,ancho,prof", [(None, 1, 1), (0, 1, 1), (float("nan"), 1, 1), (1, -2, 1)])
def test_medidas_formato_incompletas(alto, ancho, prof):
    assert catalog.medidas_formato(alto, ancho, prof) is None


def test_ficha_texto_separa_corta_medidas_materiales():
    d = ("Un vestido cómodo y calentito para el invierno. Medidas: 18 cm alto × 12.5 cm ancho "
         "Composición: 100% algodón. Variantes: 4 colores")
    ft = catalog.ficha_texto(d)
    assert ft["corta"].startswith("Un vestido cómodo")
    assert "18 cm alto" in ft["medidas"]
    assert ft["materiales"].startswith("100% algodón")


def test_ficha_texto_vacio():
    ft = catalog.ficha_texto(None)
    assert ft["corta"] == "" and ft["medidas"] is None and ft["materiales"] is None


def test_categorias_ropa_no_usan_medidas_de_tn():
    assert {"Indumentaria", "Pijamas"} <= catalog.CATEGORIAS_ROPA


def test_repartir_proporcional_suma_exacta_y_tope():
    from api.routers.catalogo import repartir_proporcional
    stocks = {"a": 50, "b": 30, "c": 20}
    asig = repartir_proporcional(stocks, 10)
    assert sum(asig.values()) == 10
    assert asig["a"] >= asig["b"] >= asig["c"]
    # Nunca más que el stock; si no alcanza, reparte todo lo que hay.
    asig = repartir_proporcional({"a": 2, "b": 1}, 10)
    assert asig == {"a": 2, "b": 1}
    assert repartir_proporcional({}, 5) == {}


def test_home_in_rechaza_formas_ajenas():
    from pydantic import ValidationError
    from api.routers.admin import HomeIn, MenuIn
    HomeIn(hero=[], bloques=[{"img": "x"}])                      # forma válida
    with pytest.raises(ValidationError):
        HomeIn(seccion="marro", config={"hero": []})              # la respuesta del GET reenviada
    MenuIn(temporadas=[{"valor": "SS27"}])
    with pytest.raises(ValidationError):
        MenuIn(auto={}, efectivo={})
