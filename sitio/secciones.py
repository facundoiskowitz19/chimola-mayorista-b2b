"""Secciones del header (los 3 "homes": marro / indu / lima) — compartido por API y admin."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Secciones del header (los 3 "homes") — compartido por API y admin
# ---------------------------------------------------------------------------
SECCIONES = {
    "marro": {"nombre": "Marroquinería", "marca": "Chimola", "excluir_cat": {"Indumentaria", "Pijamas"}},
    "indu": {"nombre": "Indumentaria", "marca": "Chimola", "solo_cat": {"Indumentaria", "Pijamas"}},
    "lima": {"nombre": "LIMA", "marca": "Lima"},
}


def filtrar_seccion(df, seccion: str | None):
    """Variantes de una sección del header (None = todo)."""
    if not seccion:
        return df
    s = SECCIONES[seccion]
    import catalog
    sub = df[df["marca"] == s["marca"]]
    indu = SECCIONES["indu"]["solo_cat"]
    if "excluir_cat" in s:   # marro: tiene alguna categoría que NO es de indumentaria (multicategoría)
        if "categorias" in sub.columns:
            sub = sub[sub["categorias"].map(lambda cs: any(c not in indu for c in (cs or [])) or not cs)]
        else:
            sub = sub[~sub["categoria"].isin(s["excluir_cat"])]
    if "solo_cat" in s:
        sub = sub[catalog.mask_categoria(sub, s["solo_cat"])]
    return sub


def seccion_de(marca: str, categoria: str) -> str:
    if marca == "Lima":
        return "lima"
    return "indu" if categoria in SECCIONES["indu"]["solo_cat"] else "marro"
