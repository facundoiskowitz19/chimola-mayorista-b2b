"""Home por sección (marro / indu / lima) + imágenes subidas por el admin.

La config vive en `sitio.py` (compartido con el admin Streamlit): doc Firestore
`config/home` con defaults. Acá solo se resuelven las secciones de productos a cards.
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

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
    cfg = sitio.home_visible(seccion)
    df = _seccion_df(deps.df_cliente(c), seccion)
    return {
        "seccion": seccion, "nombre": SECCIONES[seccion]["nombre"],
        "hero": cfg.get("hero", []), "bloques": cfg.get("bloques", []),
        "banner_grilla": cfg.get("banner_grilla"),
        "secciones": [{"titulo": s.get("titulo"), "link": s.get("link"), "tipo": s.get("tipo"),
                       "productos": _productos_seccion(s, df)} for s in cfg.get("secciones", [])],
    }


@router.get("/home/{seccion}/banner")
def banner_grilla(seccion: str, temporada: list[str] | None = Query(None), rubro: list[str] | None = Query(None),
                  categoria: list[str] | None = Query(None), c: deps.Ctx = Depends(deps.ctx_requerido)):
    """Banner intercalado en la grilla + banner de arriba del catálogo si algún filtro activo tiene uno."""
    if seccion not in SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    cfg = sitio.home_visible(seccion)
    sel = {"temporada": temporada or [], "rubro": rubro or [], "categoria": categoria or []}
    return {"banner_grilla": cfg.get("banner_grilla"), "banner_top": sitio.banner_catalogo(seccion, sel)}


@router.get("/media/{path:path}")
def media(path: str):
    """Imágenes subidas por el admin (bucket privado). Públicas: son banners del sitio."""
    r = sitio.leer_media(path)
    if r is None:
        raise HTTPException(404, "No existe")
    data, ct = r
    return Response(data, media_type=ct, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/config/sitio")
def config_sitio(c: deps.Ctx = Depends(deps.ctx_requerido)):
    """Textos globales del sitio para el front: barra negra superior y mínimos de compra.
    La barra muestra `banner_texto` (Admin → Config); vacío → la compra mínima configurada."""
    import overrides
    cfg = overrides.get_config()
    minimo_m = cfg.get("minimo_pedido_monto")
    minimo_u = cfg.get("minimo_pedido_unidades")
    texto = (cfg.get("banner_texto") or "").strip()
    if not texto:
        if minimo_m:
            texto = f"Compra mínima: ${int(float(minimo_m)):,} + IVA".replace(",", ".")
        elif minimo_u:
            texto = f"Compra mínima: {int(minimo_u)} unidades"
    return {"topbar": texto, "minimo_monto": minimo_m, "minimo_unidades": minimo_u}
