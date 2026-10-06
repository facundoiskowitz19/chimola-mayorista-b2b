"""Home por sección (marro / indu / lima), administrable desde Firestore `config/home`.

Estructura del doc (una clave por sección):
  {
    "marro": {
      "hero": [{"img", "titulo", "subtitulo", "cta", "link", "tag"}],      # carrusel
      "bloques": [{"img", "titulo", "subtitulo", "cta", "link", "ancho": "doble"|"simple"}],
      "secciones": [{"titulo", "tipo": "destacados"|"ofertas"|"manual"|"filtro",
                     "productos": [cods], "filtro": {"rubro": [...], "temporada": [...]} , "link"}],
      "banner_grilla": {"img", "titulo", "subtitulo", "cta", "link"}      # banner intercalado en la grilla
    }, ...
  }
Si no hay doc o falta la sección, se usan DEFAULTS. El admin (Streamlit) edita este doc.
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, HTTPException

import catalog
import db
import fotos

from api import deps
from api.routers.catalogo import SECCIONES, _seccion_df, card

router = APIRouter(prefix="/home", tags=["home"])

DEFAULTS = {
    "marro": {
        "hero": [{"img": "/banners/hero_marro.jpg", "titulo": "summer\n_stories", "tag": "SS_2027",
                  "cta": "Ver colección", "link": "/c/marro?temporada=Summer 2027"}],
        "bloques": [
            {"img": "/banners/bloque_marro_1.jpg", "titulo": "DÍA DE LA MADRE",
             "subtitulo": "Conocé las mejores opciones de marroquinería y bazar", "cta": "Ver todo",
             "link": "/c/marro", "ancho": "doble"},
            {"img": "/banners/bloque_marro_2.jpg", "titulo": "BAZAR", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/marro?categoria=Bazar", "ancho": "simple"},
            {"img": "/banners/bloque_marro_3.jpg", "titulo": "OFERTAS", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/marro?solo_desc=1", "ancho": "simple"},
        ],
        "secciones": [
            {"titulo": "Lo mejor de la temporada", "tipo": "destacados", "link": "/c/marro"},
            {"titulo": "Oportunidades", "tipo": "ofertas", "link": "/c/marro?solo_desc=1"},
        ],
    },
    "indu": {
        "hero": [{"img": "/banners/hero_indu.jpg", "titulo": "summer\n_stories", "tag": "SS_2027",
                  "cta": "Ver colección", "link": "/c/indu?temporada=SS27 Indumentaria"}],
        "bloques": [
            {"img": "/banners/bloque_indu_1.jpg", "titulo": "GIRLS", "subtitulo": "Descubrí todas nuestras propuestas",
             "cta": "Ver todo", "link": "/c/indu", "ancho": "doble"},
            {"img": "/banners/bloque_indu_2.jpg", "titulo": "BOYS", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/indu", "ancho": "simple"},
            {"img": "/banners/bloque_indu_3.jpg", "titulo": "SWIMWEAR", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/indu?rubro=Trajes de baño", "ancho": "simple"},
        ],
        "secciones": [
            {"titulo": "Imperdibles de temporada", "tipo": "destacados", "link": "/c/indu"},
            {"titulo": "Oportunidades", "tipo": "ofertas", "link": "/c/indu?solo_desc=1"},
        ],
    },
    "lima": {
        "hero": [{"img": "/banners/hero_lima.jpg", "titulo": "LIMA", "tag": "AW26",
                  "cta": "Ver colección", "link": "/c/lima"}],
        "bloques": [
            {"img": "/banners/bloque_lima_1.jpg", "titulo": "CARTERAS", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver todo", "link": "/c/lima?rubro=Carteras", "ancho": "doble"},
            {"img": "/banners/bloque_lima_2.jpg", "titulo": "BILLETERAS", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/lima?rubro=Billeteras", "ancho": "simple"},
            {"img": "/banners/bloque_lima_3.jpg", "titulo": "ACCESORIOS", "subtitulo": "Descubrí todas las novedades",
             "cta": "Ver", "link": "/c/lima?categoria=Accesorios", "ancho": "simple"},
        ],
        "secciones": [
            {"titulo": "Lo mejor de LIMA", "tipo": "destacados", "link": "/c/lima"},
            {"titulo": "Oportunidades", "tipo": "ofertas", "link": "/c/lima?solo_desc=1"},
        ],
    },
}

_cache: dict = {"data": None, "ts": 0.0}
_lock = threading.Lock()


def get_home_config() -> dict:
    with _lock:
        if _cache["data"] is not None and time.time() - _cache["ts"] < 60:
            return _cache["data"]
    snap = db.client().collection(db.COL_CONFIG).document("home").get()
    data = snap.to_dict() if snap.exists else {}
    with _lock:
        _cache.update(data=data or {}, ts=time.time())
    return data or {}


def _productos_seccion(sec: dict, df, n: int = 8) -> list[dict]:
    tipo = sec.get("tipo", "destacados")
    sub = df[df["precio"].notna()]
    if tipo == "manual":
        cods = [c.upper() for c in sec.get("productos", [])]
        prods = catalog.productos(sub[sub["producto_cod"].isin(cods)])
        prods = prods.set_index("producto_cod").reindex([c for c in cods if c in set(prods["producto_cod"])]).reset_index()
    elif tipo == "ofertas":
        prods = catalog.productos(sub[sub["pct_desc"] > 0]).sort_values("pct_desc", ascending=False)
    elif tipo == "filtro":
        prods = catalog.productos(catalog.filtrar_variantes(sub, sec.get("filtro") or {}))
    else:   # destacados: los marcados por el admin; si no alcanzan, completa con lo más nuevo
        dest = sub[sub["destacado"] == True] if "destacado" in sub.columns else sub.iloc[0:0]  # noqa: E712
        prods = catalog.productos(dest)
        if len(prods) < n:
            resto = catalog.productos(sub[~sub["producto_cod"].isin(prods["producto_cod"])])
            resto = resto.sort_values("producto_cod", ascending=False)
            prods = __import__("pandas").concat([prods, resto])
    prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]
    return [card(r) for _, r in prods.head(n).iterrows()]


@router.get("/{seccion}")
def home(seccion: str, c: deps.Ctx = Depends(deps.ctx_requerido)):
    if seccion not in SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    cfg = {**DEFAULTS[seccion], **(get_home_config().get(seccion) or {})}
    df = _seccion_df(deps.df_cliente(c), seccion)
    return {
        "seccion": seccion, "nombre": SECCIONES[seccion]["nombre"],
        "hero": cfg.get("hero", []), "bloques": cfg.get("bloques", []),
        "banner_grilla": cfg.get("banner_grilla"),
        "secciones": [{"titulo": s.get("titulo"), "link": s.get("link"), "tipo": s.get("tipo"),
                       "productos": _productos_seccion(s, df)} for s in cfg.get("secciones", [])],
    }
