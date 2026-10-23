"""Alias de nombres: cómo ve el cliente cada categoría, tipo de producto y temporada de Aleph.

Doc `config/home.alias = {"categoria": {valor: nombre}, "rubro": {...}, "temporada": {...}}`.
El valor de Aleph sigue siendo la clave de filtros y URLs; el alias solo cambia lo que se muestra
(menú, rail de filtros, título del catálogo, migaja y meta de la card)."""
from __future__ import annotations

import datetime as dt

from sitio._store import _ref, get_home_raw, invalidar

TIPOS_ALIAS = ("categoria", "rubro", "temporada")


def get_alias() -> dict[str, dict[str, str]]:
    raw = get_home_raw().get("alias") or {}
    return {t: {str(k): str(v) for k, v in (raw.get(t) or {}).items() if str(v).strip()} for t in TIPOS_ALIAS}


def nombre_de(tipo: str, valor: str | None) -> str | None:
    """Nombre visible de `valor` (None si no tiene alias)."""
    if not valor:
        return None
    return get_alias().get(tipo, {}).get(str(valor))


def set_alias(tipo: str, valor: str, nombre: str | None, por: str) -> None:
    """Fija (o borra, con nombre vacío) el alias de un valor."""
    if tipo not in TIPOS_ALIAS:
        raise KeyError(tipo)
    valor = str(valor).strip()
    if not valor:
        raise ValueError("valor vacío")
    nombre = (nombre or "").strip()
    # Las claves del mapa pueden tener puntos/espacios ("SS 2026 Indumentaria"): no sirve "alias.tipo.valor"
    # como field path → se lee el mapa completo y se reemplaza entero.
    invalidar()
    actual = {t: dict(v) for t, v in get_alias().items()}
    if nombre and nombre != valor:
        actual[tipo][valor] = nombre
    else:
        actual[tipo].pop(valor, None)
    _ref().set({"updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    _ref().update({"alias": actual})
    invalidar()
