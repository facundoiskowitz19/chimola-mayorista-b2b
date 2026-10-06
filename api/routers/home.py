"""Home por sección (marro / indu / lima) + imágenes subidas por el admin.

La config vive en `sitio.py` (compartido con el admin Streamlit): doc Firestore
`config/home` con defaults. Acá solo se resuelven las secciones de productos a cards.
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response

import catalog
import fotos
import sitio

from api import deps
from api.routers.catalogo import SECCIONES, _seccion_df, card

router = APIRouter(tags=["home"])


def _productos_seccion(sec: dict, df: pd.DataFrame, n: int = 8) -> list[dict]:
    tipo = sec.get("tipo", "destacados")
    sub = df[df["precio"].notna()]
    if tipo == "manual":
        cods = [c.upper() for c in sec.get("productos", [])]
        prods = catalog.productos(sub[sub["producto_cod"].isin(cods)])
        orden = {c: i for i, c in enumerate(cods)}
        prods = prods.assign(_o=prods["producto_cod"].map(orden)).sort_values("_o").drop(columns="_o")
        n = max(n, len(cods))
    elif tipo == "ofertas":
        prods = catalog.productos(sub[sub["pct_desc"] > 0]).sort_values("pct_desc", ascending=False)
    elif tipo == "filtro":
        prods = catalog.productos(catalog.filtrar_variantes(sub, sec.get("filtro") or {}))
        prods = prods.sort_values("producto_cod", ascending=False)
    else:   # destacados: los marcados por el admin; si no alcanzan, completa con lo más nuevo
        dest = sub[sub["destacado"] == True] if "destacado" in sub.columns else sub.iloc[0:0]  # noqa: E712
        prods = catalog.productos(dest)
        if len(prods) < n:
            resto = catalog.productos(sub[~sub["producto_cod"].isin(prods["producto_cod"])])
            resto = resto.sort_values("producto_cod", ascending=False)
            prods = resto if prods.empty else pd.concat([prods, resto])
    prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]
    return [card(r) for _, r in prods.head(n).iterrows()]


@router.get("/home/{seccion}")
def home(seccion: str, c: deps.Ctx = Depends(deps.ctx_requerido)):
    if seccion not in SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    cfg = sitio.get_home(seccion)
    df = _seccion_df(deps.df_cliente(c), seccion)
    return {
        "seccion": seccion, "nombre": SECCIONES[seccion]["nombre"],
        "hero": cfg.get("hero", []), "bloques": cfg.get("bloques", []),
        "banner_grilla": cfg.get("banner_grilla"),
        "secciones": [{"titulo": s.get("titulo"), "link": s.get("link"), "tipo": s.get("tipo"),
                       "productos": _productos_seccion(s, df)} for s in cfg.get("secciones", [])],
    }


@router.get("/home/{seccion}/banner")
def banner_grilla(seccion: str, c: deps.Ctx = Depends(deps.ctx_requerido)):
    if seccion not in SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    return {"banner_grilla": sitio.get_home(seccion).get("banner_grilla")}


@router.get("/media/{path:path}")
def media(path: str):
    """Imágenes subidas por el admin (bucket privado). Públicas: son banners del sitio."""
    r = sitio.leer_media(path)
    if r is None:
        raise HTTPException(404, "No existe")
    data, ct = r
    return Response(data, media_type=ct, headers={"Cache-Control": "public, max-age=3600"})
