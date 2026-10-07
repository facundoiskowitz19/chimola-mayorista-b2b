"""Imágenes subidas por el admin: bucket privado de pedidos, prefijo `sitio/`, servidas por la API en /media."""
from __future__ import annotations

import mimetypes
import re
import time
import unicodedata
from functools import lru_cache

from google.cloud import storage

import config

MEDIA_PREFIX = "sitio/"
MEDIA_URL = "/api/media/"

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
