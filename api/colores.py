"""Nombre de color de Aleph → hex para los swatches de las cards.

Heurística por palabra clave (primera que matchea gana; las compuestas se
listan antes). Desconocido → gris neutro. El admin podrá pisar esto más
adelante desde Firestore si hace falta."""
from __future__ import annotations

import unicodedata

_MAPA: list[tuple[str, str]] = [
    ("LIGHT PINK", "#f4c2d0"), ("PALE PINK", "#f1c9d3"), ("LIGHT PURPLE", "#c9b6e4"),
    ("LIGHT BLUE", "#a9cfe8"), ("LIGHT GREEN", "#b7dcb0"), ("LIGHT GREY", "#c8c8c8"),
    ("DARK PINK", "#c2185b"), ("DARK GREEN", "#1f4d2b"), ("DARK BLUE", "#1a2b5e"),
    ("OFF WHITE", "#f3efe6"), ("VERDE AGUA", "#9fd8cb"), ("CEBRA", "#8a6a4f"),
    ("RAINBOW", "linear-gradient(135deg,#ff6b6b,#feca57,#48dbfb,#ff9ff3)"),
    ("MULTICOLOR", "linear-gradient(135deg,#ff6b6b,#feca57,#48dbfb,#ff9ff3)"),
    ("PRINT", "linear-gradient(135deg,#d7ccc8,#8d6e63)"), ("ESTAMPADO", "linear-gradient(135deg,#d7ccc8,#8d6e63)"),
    ("ANIMAL", "#a67c52"), ("LEOPARDO", "#a67c52"),
    ("BLACK", "#111111"), ("NEGRO", "#111111"),
    ("WHITE", "#f7f7f7"), ("BLANCO", "#f7f7f7"), ("CRUDO", "#efe8da"), ("IVORY", "#f2ead7"),
    ("MARFIL", "#f2ead7"), ("CREAM", "#f1e7cf"), ("CREMA", "#f1e7cf"), ("NATURAL", "#e9dcc3"),
    ("BEIGE", "#d9c3a5"), ("NUDE", "#e3c6b0"), ("ARENA", "#d8c39a"), ("CAMEL", "#b98a5a"),
    ("TOSTADO", "#b07a45"), ("CARAMELO", "#b9793f"), ("SUELA", "#a8744a"), ("HABANO", "#8c5a2b"),
    ("CHOCOLATE", "#4e2a14"), ("MARRON", "#6b3e1e"), ("BROWN", "#6b3e1e"), ("CAFE", "#5b3a1a"),
    ("VISON", "#a8907a"), ("TAUPE", "#8b7d6b"), ("TOPO", "#8b7d6b"),
    ("GRIS", "#9a9a9a"), ("GREY", "#9a9a9a"), ("GRAY", "#9a9a9a"), ("PLOMO", "#777777"),
    ("SILVER", "#c0c0c0"), ("PLATA", "#c0c0c0"), ("PLATEADO", "#c0c0c0"),
    ("GOLD", "#d4af37"), ("DORADO", "#d4af37"), ("ORO", "#d4af37"),
    ("ROJO", "#d62828"), ("RED", "#d62828"), ("BORDO", "#6d1a2b"), ("BURGUNDY", "#6d1a2b"),
    ("VINO", "#722f37"), ("TINTO", "#722f37"), ("CORAL", "#ff7f6e"), ("SALMON", "#fa9a85"),
    ("DURAZNO", "#f7b48b"), ("NARANJA", "#f77f00"), ("ORANGE", "#f77f00"), ("MANDARINA", "#f98b2a"),
    ("AMARILLO", "#f4d03f"), ("YELLOW", "#f4d03f"), ("LEMON", "#f6e96b"), ("LIMON", "#f6e96b"),
    ("MOSTAZA", "#d4a017"), ("MUSTARD", "#d4a017"), ("MAIZ", "#f1cf5a"),
    ("FUCSIA", "#e0218a"), ("FUCHSIA", "#e0218a"), ("MAGENTA", "#d6006c"),
    ("ROSA", "#f28cb1"), ("PINK", "#f28cb1"), ("ROSE", "#e8a0b4"), ("FRUTILLA", "#ef5a7a"),
    ("STRAWBERRY", "#ef5a7a"), ("CHICLE", "#ff9ecb"),
    ("LILA", "#b89bd9"), ("LILAC", "#b89bd9"), ("LAVANDA", "#b7a4dc"), ("LAVENDER", "#b7a4dc"),
    ("VIOLETA", "#7d4fb3"), ("PURPLE", "#7d4fb3"), ("MORADO", "#6a2c91"), ("UVA", "#5e2d79"),
    ("ORCHID", "#c678c6"),
    ("CELESTE", "#8ecae6"), ("SKY", "#8ecae6"), ("AQUA", "#7fd8d8"), ("AERO", "#9ad0ec"),
    ("TURQUESA", "#2ab7b7"), ("TURQUOISE", "#2ab7b7"), ("MINT", "#a8e6cf"), ("MENTA", "#a8e6cf"),
    ("AZUL", "#1f4fa3"), ("BLUE", "#1f4fa3"), ("NAVY", "#1a2b5e"), ("NAVAL", "#1a2b5e"),
    ("MARINO", "#1a2b5e"), ("DENIM", "#4f6d9a"), ("INDIGO", "#3f4f8f"), ("PETROLEO", "#1d4e5f"),
    ("FRANCIA", "#2d5be3"), ("ROYAL", "#2d5be3"), ("COBALTO", "#2c4fcf"),
    ("VERDE", "#3a8f4f"), ("GREEN", "#3a8f4f"), ("MILITAR", "#5c6b3c"), ("OLIVA", "#6b7a34"),
    ("OLIVE", "#6b7a34"), ("KHAKI", "#9b8a5a"), ("KAKI", "#9b8a5a"), ("SAGE", "#9caf88"),
    ("BOSQUE", "#2f5d3a"), ("ESMERALDA", "#2e8b57"), ("LIME", "#b5d33d"), ("LIMA", "#b5d33d"),
    ("TRANSPARENTE", "#e8f4f8"), ("TRANSPARENT", "#e8f4f8"), ("HIELO", "#e6f2f7"),
]

_DEFAULT = "#cccccc"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("&", " ").replace("/", " ").split())


def hex_de(color: str | None) -> str:
    n = " " + _norm(color) + " "
    for key, val in _MAPA:
        if f" {key} " in n or (len(key) > 4 and key in n):
            return val
    return _DEFAULT
