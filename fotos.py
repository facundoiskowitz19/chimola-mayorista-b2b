"""Fotos de productos desde GCS (`gs://ecommerce-b2b-imagenes/catalogo/fotos_productos/<PROD>/`).

- Índice de TODO el prefijo en 1 listado (cache 1h) → no hacemos 1 list por card.
- Signed URLs V4 con TTL 1h, firmadas vía IAM signBlob (Cloud Run no tiene
  private key). Local sin SA → fallback a URL pública (el bucket hoy es público).
- Parsing de nombres para agrupar por color, misma convención que el pipeline Woo:
  "M211 AQUA (1).jpg", "VEST2 - GREEN Frente.jpg", "L11 VISON.jpg", "M211 allcolors.jpg".
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
import unicodedata
from functools import lru_cache
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage

import config

log = logging.getLogger(__name__)

IMG_EXT = re.compile(r"\.(?:jpe?g|png|webp)$", re.IGNORECASE)
RE_NUM = re.compile(r"^(?P<prod>\S+)\s+(?:(?P<color>.*?)\s+)?\((?P<n>\d+)\)\.\w+$")
RE_VIEW = re.compile(
    r"^(?P<prod>\S+)\s*-\s*(?P<color>.+?)\s+(?P<view>Frente|Perfil|Back|Inside.*|Accesorio.*|Dorso.*)\.\w+$",
    re.IGNORECASE,
)
RE_ALLCOLORS = re.compile(r"all\s*-?\s*colors?|todos\s+los\s+colores", re.IGNORECASE)

PLACEHOLDER = (
    "data:image/svg+xml;utf8,"
    + quote(
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600">'
        '<rect width="100%" height="100%" fill="#f1f1f1"/>'
        '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        'font-family="sans-serif" font-size="28" fill="#999">Sin foto</text></svg>'
    )
)


def norm(s: str) -> str:
    """UPPER + sin acentos + sin espacios/guiones (para cruzar color foto ↔ color catálogo)."""
    s = unicodedata.normalize("NFD", (s or "").strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s\-_]+", "", s).upper()


# ---------------------------------------------------------------------------
# GCS
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _storage() -> storage.Client:
    return storage.Client(project=config.GCP_PROJECT)


_idx_lock = threading.Lock()
_idx: dict[str, list[str]] = {}
_idx_ts = 0.0
_IDX_TTL = 3600


def indice_fotos(force: bool = False) -> dict[str, list[str]]:
    """{producto_cod (UPPER): [filename, ...]} de todo el bucket (cache 1h)."""
    global _idx, _idx_ts
    with _idx_lock:
        if _idx and not force and time.time() - _idx_ts < _IDX_TTL:
            return _idx
        t0 = time.time()
        prefix = config.FOTOS_PREFIX.rstrip("/") + "/"
        out: dict[str, list[str]] = {}
        for blob in _storage().list_blobs(config.BUCKET_FOTOS, prefix=prefix):
            rel = blob.name[len(prefix):]
            if "/" not in rel:
                continue
            prod, fn = rel.split("/", 1)
            if not fn or "/" in fn or not IMG_EXT.search(fn):
                continue
            out.setdefault(prod.strip().upper(), []).append(fn)
        _idx, _idx_ts = out, time.time()
        log.info("Índice de fotos: %d productos en %.1fs", len(out), time.time() - t0)
        return _idx


# ---------------------------------------------------------------------------
# Signed URLs
# ---------------------------------------------------------------------------
_signer_lock = threading.Lock()
_signer: dict | None = None   # kwargs para generate_signed_url, o {} si no se puede firmar


def _signer_kwargs() -> dict:
    """Credenciales para firmar. En Cloud Run: SA sin key → signBlob con
    service_account_email + access_token. Local (usuario ADC): {} → URL pública."""
    global _signer
    with _signer_lock:
        if _signer is not None and _signer.get("_exp", 0) > time.time():
            return {k: v for k, v in _signer.items() if not k.startswith("_")}
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        kwargs: dict = {}
        if hasattr(creds, "sign_bytes") and getattr(creds, "signer", None) is not None \
                and getattr(creds, "_private_key", None) is not None:
            kwargs = {}  # SA con private key: firma local
        elif getattr(creds, "service_account_email", None) and creds.service_account_email != "default":
            creds.refresh(Request())
            kwargs = {"service_account_email": creds.service_account_email, "access_token": creds.token}
        else:
            try:  # compute/Cloud Run creds: email llega al refrescar
                creds.refresh(Request())
                email = getattr(creds, "service_account_email", None)
                if email and email != "default":
                    kwargs = {"service_account_email": email, "access_token": creds.token}
            except Exception as e:  # noqa: BLE001
                log.info("No se puede firmar URLs (%s); uso URL pública", e)
        kwargs["_exp"] = time.time() + 40 * 60
        _signer = kwargs
        return {k: v for k, v in kwargs.items() if not k.startswith("_")}


_url_cache: dict[str, tuple[str, float]] = {}
_url_lock = threading.Lock()


def url_foto(producto_cod: str, filename: str) -> str:
    """URL (firmada, TTL 1h) de una foto. Cacheada 50 min."""
    blob_name = f"{config.FOTOS_PREFIX.rstrip('/')}/{producto_cod}/{filename}"
    with _url_lock:
        hit = _url_cache.get(blob_name)
        if hit and hit[1] > time.time():
            return hit[0]
    url = _public_url(blob_name)
    try:
        kw = _signer_kwargs()
        blob = _storage().bucket(config.BUCKET_FOTOS).blob(blob_name)
        if kw or getattr(_storage()._credentials, "signer", None):
            url = blob.generate_signed_url(version="v4", expiration=dt.timedelta(seconds=config.FOTO_URL_TTL_SEG),
                                           method="GET", **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("Fallo firmando %s (%s); uso URL pública", blob_name, e)
    with _url_lock:
        _url_cache[blob_name] = (url, time.time() + config.FOTO_URL_TTL_SEG - 600)
    return url


def _public_url(blob_name: str) -> str:
    return f"https://storage.googleapis.com/{config.BUCKET_FOTOS}/{quote(blob_name)}"


# ---------------------------------------------------------------------------
# Parsing de nombres → fotos ordenadas y agrupadas por color
# ---------------------------------------------------------------------------
def parsear_fotos(producto_cod: str, filenames: list[str], colores_catalogo: list[str] | None = None) -> list[dict]:
    """[{filename, color_norm, order, is_main, is_cover}] ordenadas con la portada primero."""
    colores_norm = sorted({norm(c) for c in (colores_catalogo or []) if c}, key=len, reverse=True)
    fotos = []
    for fn in filenames:
        stem = IMG_EXT.sub("", fn)
        m = RE_NUM.match(fn)
        if m:
            color, n = (m.group("color") or "").strip(), int(m.group("n"))
            is_main, order = (n == 1), (0 if n == 1 else n)
        else:
            m = RE_VIEW.match(fn)
            if m:
                color = m.group("color").strip()
                is_main = m.group("view").strip().lower().startswith("frente")
                order = 0 if is_main else 1
            else:
                # "L11 VISON.jpg": sacar el código y quedarse con el resto como color
                resto = re.sub(r"^" + re.escape(producto_cod) + r"[\s\-_]*", "", stem, flags=re.IGNORECASE)
                color = ""
                rn = norm(resto)
                for ck in colores_norm:
                    if ck and ck in rn:
                        color = ck
                        break
                color = color or resto
                is_main, order = (True, 0)
        is_cover = bool(RE_ALLCOLORS.search(stem)) or norm(stem) == norm(producto_cod)
        fotos.append({"filename": fn, "color_norm": norm(color) if color and not is_cover else "",
                      "order": order, "is_main": is_main, "is_cover": is_cover})

    # Portada: 1) cover  2) BLACK main  3) cualquier main  4) primera alfabética
    principal = next((f for f in fotos if f["is_cover"]), None) \
        or next((f for f in fotos if f["is_main"] and f["color_norm"] == "BLACK"), None) \
        or next((f for f in fotos if f["is_main"]), None) \
        or (min(fotos, key=lambda f: (f["color_norm"], f["order"], f["filename"])) if fotos else None)
    if principal is None:
        return []
    resto = sorted((f for f in fotos if f is not principal),
                   key=lambda f: (not f["is_cover"], f["color_norm"], f["order"], f["filename"]))
    return [principal] + resto


def fotos_producto(producto_cod: str, colores_catalogo: list[str] | None = None) -> list[dict]:
    """Fotos del producto con URL firmada. [] si no tiene."""
    files = indice_fotos().get(producto_cod.strip().upper(), [])
    fotos = parsear_fotos(producto_cod, files, colores_catalogo)
    for f in fotos:
        f["url"] = url_foto(producto_cod, f["filename"])
    return fotos


def foto_principal(producto_cod: str) -> str:
    """URL de la foto de portada (o placeholder)."""
    files = indice_fotos().get(producto_cod.strip().upper(), [])
    fotos = parsear_fotos(producto_cod, files)
    return url_foto(producto_cod, fotos[0]["filename"]) if fotos else PLACEHOLDER


def fotos_por_color(fotos: list[dict], color: str) -> list[dict]:
    """Fotos del color (exacto o fuzzy por inclusión); si no hay, todas."""
    cn = norm(color)
    exact = [f for f in fotos if f["color_norm"] == cn]
    if exact:
        return exact
    aprox = [f for f in fotos if f["color_norm"] and (cn in f["color_norm"] or f["color_norm"] in cn)]
    return aprox or fotos


def tiene_fotos(producto_cod: str) -> bool:
    return bool(indice_fotos().get(producto_cod.strip().upper()))
