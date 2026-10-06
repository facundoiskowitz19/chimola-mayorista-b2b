"""Configuración del SITIO nuevo (Next.js): homes por sección + imágenes subidas.

Doc Firestore `config/home` con una clave por sección ("marro" / "indu" / "lima"):
  hero[]        {img, titulo, tag, cta, link}          carrusel de arriba
  bloques[]     {img, titulo, subtitulo, cta, link, ancho: doble|simple}
  secciones[]   {titulo, tipo: destacados|ofertas|manual|filtro, productos[], filtro{rubro[],temporada[]}, link}
  banner_grilla {img, titulo, subtitulo, cta, link}    banner intercalado en el catálogo

Las imágenes subidas por el admin viven en `gs://BUCKET_PEDIDOS/sitio/…` (bucket
privado; la API las sirve en `/media/<blob>`). En la config se guardan como
`/api/media/sitio/<archivo>`: así el front las pide same-origin. Las que empiezan
con `/banners/` son las estáticas por defecto del front.
"""
from __future__ import annotations

import datetime as dt
import mimetypes
import re
import threading
import time
import unicodedata
from functools import lru_cache

from google.cloud import storage

import config
import db

SECCIONES_HOME = {"marro": "Marroquinería (Chimola)", "indu": "Indumentaria (Chimola)", "lima": "LIMA"}
TIPOS_SECCION = {"destacados": "Destacados (los marcados en Catálogo)", "ofertas": "Oportunidades (con descuento)",
                 "manual": "Lista manual de productos", "filtro": "Por filtro (tipo / temporada)"}
MEDIA_PREFIX = "sitio/"
MEDIA_URL = "/api/media/"

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
        "banner_grilla": None,
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
    },
}

_cache: dict = {"data": None, "ts": 0.0}
_lock = threading.Lock()
_TTL = 60


def _ref():
    return db.client().collection(db.COL_CONFIG).document("home")


def invalidar() -> None:
    with _lock:
        _cache.update(data=None, ts=0.0)


def get_home_raw() -> dict:
    """Doc `config/home` tal cual está (sin defaults). Cache 60 s."""
    with _lock:
        if _cache["data"] is not None and time.time() - _cache["ts"] < _TTL:
            return _cache["data"]
    snap = _ref().get()
    data = (snap.to_dict() or {}) if snap.exists else {}
    with _lock:
        _cache.update(data=data, ts=time.time())
    return data


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
    }
    _ref().set({seccion: limpio, "updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    invalidar()


def reset_home(seccion: str, por: str) -> None:
    from google.cloud import firestore
    _ref().set({"updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    _ref().update({seccion: firestore.DELETE_FIELD})
    invalidar()


def _limpiar_bloque(b: dict) -> dict:
    out = {k: (str(b.get(k) or "").strip()) for k in ("img", "titulo", "subtitulo", "tag", "cta", "link")}
    out["ancho"] = "doble" if str(b.get("ancho") or "").lower().startswith("d") else "simple"
    return {k: v for k, v in out.items() if v != "" or k in ("img", "titulo")}


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
            "productos": [str(p).strip().upper() for p in prods], "filtro": filtro}


# ---------------------------------------------------------------------------
# Imágenes subidas por el admin (bucket privado de pedidos, prefijo sitio/)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _storage() -> storage.Client:
    return storage.Client(project=config.GCP_PROJECT)


def _slug(nombre: str) -> str:
    base = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9.]+", "-", base).strip("-")
    return base or "imagen"


def subir_imagen(data: bytes, nombre: str, content_type: str | None = None) -> str:
    """Sube la imagen y devuelve la URL para guardar en la config (`/api/media/sitio/…`)."""
    ct = content_type or mimetypes.guess_type(nombre)[0] or "image/jpeg"
    blob_name = f"{MEDIA_PREFIX}{int(time.time())}-{_slug(nombre)}"
    blob = _storage().bucket(config.BUCKET_PEDIDOS).blob(blob_name)
    blob.cache_control = "public, max-age=3600"
    blob.upload_from_string(data, content_type=ct)
    return f"{MEDIA_URL}{blob_name}"


def es_media(url: str | None) -> bool:
    return bool(url) and url.startswith(MEDIA_URL)


def leer_media(path: str) -> tuple[bytes, str] | None:
    """(bytes, content_type) de un blob bajo `sitio/`; None si no existe o el path se sale."""
    path = path.lstrip("/")
    if not path.startswith(MEDIA_PREFIX) or ".." in path:
        return None
    blob = _storage().bucket(config.BUCKET_PEDIDOS).blob(path)
    if not blob.exists():
        return None
    return blob.download_as_bytes(), (blob.content_type or "image/jpeg")


def leer_media_url(url: str) -> tuple[bytes, str] | None:
    """Para previews en el admin: acepta la URL guardada (`/api/media/sitio/…`)."""
    if not es_media(url):
        return None
    return leer_media(url[len(MEDIA_URL):])
