"""Home por sección (hero, bloques, filas de productos, banner de grilla, banners de colección):
defaults, config del admin, limpieza al guardar y helpers de banners por filtro."""
from __future__ import annotations

import datetime as dt
import re

from sitio._store import _ref, get_home_raw, invalidar
from sitio.secciones import SECCIONES

SECCIONES_HOME = {"marro": "Marroquinería (Chimola)", "indu": "Indumentaria (Chimola)", "lima": "LIMA"}
TIPOS_SECCION = {"destacados": "Destacados (los marcados en Catálogo)", "ofertas": "Oportunidades (con descuento)",
                 "manual": "Lista manual de productos", "filtro": "Por filtro (tipo / temporada)"}

DEFAULTS: dict[str, dict] = {
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
        "banner_grilla": {"img": "/banners/banner_pets.jpg", "titulo": "PETS", "subtitulo": "chimola® nuevo lanzamiento",
                          "cta": "Ver productos", "link": "/c/marro?rubro=Pets"},
        "banners_catalogo": [
            {"temporada": "Summer 2027", "img": "/banners/hero_marro.jpg", "kicker": "Grupo_ Denim Indigo",
             "titulo": "summer\n_stories", "cta": "Ver productos", "link": "/c/marro?temporada=Summer 2027"},
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
        "banner_grilla": None,
        "banners_catalogo": [
            {"temporada": "SS27 Indumentaria", "img": "/banners/hero_indu.jpg", "kicker": "Colección",
             "titulo": "summer\n_stories", "cta": "Ver productos", "link": "/c/indu?temporada=SS27 Indumentaria"},
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
        "banner_grilla": None,
        "banners_catalogo": [],
    },
}


def get_home(seccion: str) -> dict:
    """Config efectiva de una sección: lo guardado por el admin, o DEFAULTS."""
    if seccion not in DEFAULTS:
        raise KeyError(seccion)
    guardado = get_home_raw().get(seccion)
    return {**DEFAULTS[seccion], **(guardado or {})}


def es_personalizada(seccion: str) -> bool:
    return bool(get_home_raw().get(seccion))


def set_home(seccion: str, data: dict, por: str) -> None:
    if seccion not in DEFAULTS:
        raise KeyError(seccion)
    limpio = {
        "hero": [_limpiar_bloque(b) for b in (data.get("hero") or []) if (b.get("img") or b.get("titulo"))],
        "bloques": [_limpiar_bloque(b) for b in (data.get("bloques") or []) if (b.get("img") or b.get("titulo"))],
        "secciones": [_limpiar_seccion(s) for s in (data.get("secciones") or []) if s.get("titulo")],
        "banner_grilla": _limpiar_bloque(data["banner_grilla"]) if data.get("banner_grilla") else None,
        "banners_catalogo": [b for b in (_limpiar_banner_cat(x) for x in (data.get("banners_catalogo") or [])) if b],
    }
    _ref().set({seccion: limpio, "updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    invalidar()


def reset_home(seccion: str, por: str) -> None:
    from google.cloud import firestore
    _ref().set({"updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    _ref().update({seccion: firestore.DELETE_FIELD})
    invalidar()


def _limpiar_bloque(b: dict) -> dict:
    out = {k: (str(b.get(k) or "").strip()) for k in ("img", "titulo", "subtitulo", "tag", "cta", "link", "kicker")}
    out["ancho"] = "doble" if str(b.get("ancho") or "").lower().startswith("d") else "simple"
    out = {k: v for k, v in out.items() if v != "" or k in ("img", "titulo")}
    if b.get("oculto"):   # guardado pero no visible (pruebas, estacionales)
        out["oculto"] = True
    return out


FILTROS_BANNER = ("temporada", "rubro", "categoria")


def _limpiar_banner_cat(b: dict) -> dict | None:
    """Banner de arriba del catálogo, atado a UN filtro (temporada / tipo de producto / categoría)."""
    out = _limpiar_bloque(b)
    out["kicker"] = str(b.get("kicker") or "").strip()
    filtros = {k: str(b.get(k) or "").strip() for k in FILTROS_BANNER if str(b.get(k) or "").strip()}
    if not filtros or not (out.get("img") or out.get("titulo")):
        return None
    out.update(filtros)
    return out


def home_visible(seccion: str) -> dict:
    """Config efectiva SIN los elementos marcados `oculto` (lo que ve el cliente)."""
    cfg = get_home(seccion)
    vis = lambda xs: [x for x in (xs or []) if not x.get("oculto")]  # noqa: E731
    bg = cfg.get("banner_grilla")
    return {**cfg, "hero": vis(cfg.get("hero")), "bloques": vis(cfg.get("bloques")),
            "secciones": vis(cfg.get("secciones")), "banner_grilla": bg if bg and not bg.get("oculto") else None,
            "banners_catalogo": vis(cfg.get("banners_catalogo"))}


def banners_de_filtro(clave: str, valor: str) -> dict[str, dict | None]:
    """{seccion: banner} del banner de colección atado a `clave=valor` (categoria / rubro / temporada)."""
    if clave not in FILTROS_BANNER:
        raise KeyError(clave)
    out = {}
    for sec in SECCIONES:
        out[sec] = next((b for b in get_home(sec).get("banners_catalogo") or []
                         if b.get(clave) == valor and not any(b.get(k) for k in FILTROS_BANNER if k != clave)), None)
    return out


def set_banner_filtro(seccion: str, clave: str, valor: str, banner: dict | None, por: str) -> None:
    """Crea/reemplaza/borra el banner de colección de `clave=valor` en la sección, conservando el
    resto de la home (incluidos los defaults, que pasan a quedar guardados)."""
    if clave not in FILTROS_BANNER:
        raise KeyError(clave)
    cfg = get_home(seccion)
    es_este = lambda b: b.get(clave) == valor and not any(b.get(k) for k in FILTROS_BANNER if k != clave)  # noqa: E731
    resto = [b for b in cfg.get("banners_catalogo") or [] if not es_este(b)]
    if banner:
        banner = {**banner, **{k: "" for k in FILTROS_BANNER}, clave: valor}
        resto.append(banner)
    set_home(seccion, {**cfg, "banners_catalogo": resto}, por)


def banners_de_categoria(nombre: str) -> dict[str, dict | None]:
    return banners_de_filtro("categoria", nombre)


def set_banner_categoria(seccion: str, nombre: str, banner: dict | None, por: str) -> None:
    set_banner_filtro(seccion, "categoria", nombre, banner, por)


def banner_catalogo(seccion: str, seleccion: dict) -> dict | None:
    """El banner cuya condición matchea la selección actual del catálogo (listas de valores
    por filtro). Primera regla que matchea, todas sus condiciones incluidas en la selección."""
    for b in (home_visible(seccion) if seccion in DEFAULTS else {}).get("banners_catalogo") or []:
        cond = {k: b[k] for k in FILTROS_BANNER if b.get(k)}
        if cond and all(b[k] in (seleccion.get(k) or []) for k in cond):
            return b
    return None


def sitio_get_home_safe(seccion: str) -> dict:
    try:
        return get_home(seccion)
    except KeyError:
        return {}


def _limpiar_seccion(s: dict) -> dict:
    tipo = s.get("tipo") if s.get("tipo") in TIPOS_SECCION else "destacados"
    prods = s.get("productos") or []
    if isinstance(prods, str):
        prods = [p for p in re.split(r"[,\s;]+", prods) if p]
    filtro = s.get("filtro") or {}
    for k in ("rubro", "temporada", "categoria"):
        v = filtro.get(k)
        if isinstance(v, str):
            filtro[k] = [x.strip() for x in v.split(",") if x.strip()]
    filtro = {k: v for k, v in filtro.items() if v}
    return {"titulo": str(s.get("titulo") or "").strip(), "tipo": tipo, "link": str(s.get("link") or "").strip() or None,
            "productos": [str(p).strip().upper() for p in prods], "filtro": filtro, "oculto": bool(s.get("oculto"))}
