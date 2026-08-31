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


def url_foto_publica(producto_cod: str, filename: str) -> str:
    """URL pública de una foto (no vence — para links en Excel y tablas largas).
    El bucket es público hoy (lo usa el Woo); si algún día se cierra, esto
    debe migrar a otro esquema."""
    return _public_url(f"{config.FOTOS_PREFIX.rstrip('/')}/{producto_cod.strip().upper()}/{filename}")


def foto_variante_filename(producto_cod: str, color: str | None = None,
                           solo_color: bool = False) -> str | None:
    """Filename de la foto de la variante: la de SU color, o la portada.
    `solo_color=True` (Excels): si el color no tiene foto propia → None,
    nunca una foto de otro color ni la portada."""
    prod = producto_cod.strip().upper()
    files = indice_fotos().get(prod, [])
    if not files:
        return None
    if color:
        mapa = foto_por_color(prod, [color], files, _overrides_fotos(prod))
        fn = mapa.get(norm(color))
        if fn:
            return fn
    if solo_color:
        return None
    return _portada_filename(prod, files)


@lru_cache(maxsize=16384)
def url_variante_publica(producto_cod: str, color: str | None = None,
                         solo_color: bool = False) -> str:
    """URL pública de la foto de la variante ('' si no hay; con `solo_color`,
    '' también cuando el color no tiene foto propia)."""
    fn = foto_variante_filename(producto_cod, color, solo_color)
    return url_foto_publica(producto_cod, fn) if fn else ""


@lru_cache(maxsize=8192)
def miniatura_jpeg(producto_cod: str, filename: str, px: int = 56) -> bytes | None:
    """Miniatura JPEG chica (~3-5 KB) para embeber en Excel. Cache de proceso."""
    import io as _io

    from PIL import Image
    try:
        blob_name = f"{config.FOTOS_PREFIX.rstrip('/')}/{producto_cod.strip().upper()}/{filename}"
        data = _storage().bucket(config.BUCKET_FOTOS).blob(blob_name).download_as_bytes()
        im = Image.open(_io.BytesIO(data)).convert("RGB")
        im.thumbnail((px, px))
        out = _io.BytesIO()
        im.save(out, "JPEG", quality=72)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        log.warning("Miniatura %s/%s: %s", producto_cod, filename, e)
        return None


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


def _override_portada(producto_cod: str) -> str | None:
    """Portada elegida por el admin (catalogo_overrides.portada), si hay."""
    try:
        import overrides as _ov
        o = _ov.get_catalogo_overrides().get(producto_cod.strip().upper(), {})
        return o.get("portada") or None
    except Exception:  # noqa: BLE001 — tests / local sin Firestore
        return None


def _portada_filename(producto_cod: str, files: list[str]) -> str | None:
    """Filename de la portada: el override del admin si existe, si no la automática."""
    ov = _override_portada(producto_cod)
    if ov and ov in files:
        return ov
    pf = parsear_fotos(producto_cod, files)
    return pf[0]["filename"] if pf else None


def fotos_producto(producto_cod: str, colores_catalogo: list[str] | None = None) -> list[dict]:
    """Fotos del producto con URL firmada. [] si no tiene."""
    files = indice_fotos().get(producto_cod.strip().upper(), [])
    fotos = parsear_fotos(producto_cod, files, colores_catalogo)
    ov = _override_portada(producto_cod)
    if ov and any(f["filename"] == ov for f in fotos):
        fotos.sort(key=lambda f: f["filename"] != ov)   # la elegida, primera
    for f in fotos:
        f["url"] = url_foto(producto_cod, f["filename"])
    return fotos


def foto_principal(producto_cod: str) -> str:
    """URL de la foto de portada (elegida por el admin, o automática)."""
    files = indice_fotos().get(producto_cod.strip().upper(), [])
    fn = _portada_filename(producto_cod, files)
    return url_foto(producto_cod, fn) if fn else PLACEHOLDER


def fotos_por_color(fotos: list[dict], color: str) -> list[dict]:
    """Fotos del color: exacto → fuzzy (typos, mismo criterio que el Woo) →
    inclusión; si no hay nada, todas."""
    cn = norm(color)
    exact = [f for f in fotos if f["color_norm"] == cn]
    if exact:
        return exact
    colores_fotos = sorted({f["color_norm"] for f in fotos if f["color_norm"]})
    best = _resolver_color_fuzzy(cn, colores_fotos)
    if best:
        return [f for f in fotos if f["color_norm"] == best]
    aprox = [f for f in fotos if f["color_norm"] and (cn in f["color_norm"] or f["color_norm"] in cn)]
    return aprox or fotos


# ---------------------------------------------------------------------------
# "Encender el sitio": foto de la variante de color CLARO de cada producto
# ---------------------------------------------------------------------------
# Orden = preferencia (primero los más luminosos). Se matchea por palabra
# dentro del nombre de color de Aleph (ej. "PALE PINK", "LIGHT BLUE", "OFF WHITE").
COLORES_CLAROS = (
    "WHITE", "BLANCO", "CRUDO", "IVORY", "MARFIL", "CREAM", "CREMA", "VAINILLA", "NATURAL",
    "BEIGE", "NUDE", "ARENA", "OFF WHITE",
    "PALE", "LIGHT", "LT ", "HIELO", "SKY", "CELESTE", "AQUA", "AERO", "VERDE AGUA",
    "MINT", "MENTA", "LILA", "LILAC", "LAVANDA", "LAVANDER", "LAVENDER", "ORCHID",
    "ROSA", "PINK", "ROSE", "SALMON", "DURAZNO", "CORAL", "STRAWBERRY", "FRUTILLA",
    "MAIZ", "LEMON", "LIMON", "AMARILLO", "YELLOW", "LIME", "LIMA",
    "SILVER", "PLATA", "PLATEADO", "TRANSPARENT", "HELADO", "ICE CREAM", "SMOOTHIE",
)
# Si aparece alguno de estos, el color NO es claro aunque contenga una palabra clara
# (ej. "NUDE & NEGRO", "DARK PINK").
COLORES_OSCUROS = ("DARK", "OSCURO", "DEEP", "BLACK", "NEGRO", "BORDO", "BURGUNDY",
                   "CHOCOLATE", "MARRON", "BROWN", "NAVY", "NAVAL", "PETROLEO", "MILITAR",
                   "OLIVA", "TINTO", "FULL")


def _padded(color) -> str:
    return " " + " ".join(str(color or "").upper().replace("&", " ").split()) + " "


def es_color_claro(color: str | None) -> bool:
    """PURA: True si el nombre de color de Aleph describe un color claro.
    Match por palabra/frase completa (" PALE PINK " contiene " PALE ")."""
    c = _padded(color)
    if c.strip() == "" or any(f" {o} " in c for o in COLORES_OSCUROS):
        return False
    return any(f" {k.strip()} " in c for k in COLORES_CLAROS)


def _rank_claro(color: str) -> int:
    cp = _padded(color)
    return next((i for i, k in enumerate(COLORES_CLAROS) if f" {k.strip()} " in cp),
                len(COLORES_CLAROS))


def color_claro(colores: list[str]) -> str | None:
    """PURA: el color más claro del producto (según el orden de preferencia),
    o None si ninguna variante es clara."""
    claros = sorted((c for c in colores if es_color_claro(c)), key=_rank_claro)
    return claros[0] if claros else None


# Modo "apagado": la variante NEGRA del producto. "BLACK"/"NEGRO" exactos primero,
# después las compuestas ("FULL BLACK", "BLACK MAT", "NAVE BLACK"...).
COLORES_NEGROS = ("BLACK", "NEGRO")


def es_color_negro(color: str | None) -> bool:
    c = _padded(color)
    return any(f" {k} " in c for k in COLORES_NEGROS)


def _rank_negro(color: str) -> int:
    cu = _padded(color).strip()
    return 0 if cu in COLORES_NEGROS else (1 if cu in ("FULL BLACK", "NEGRO FULL", "NATURAL BLACK") else 2)


def colores_por_modo(colores: list[str], modo: str) -> list[str]:
    """PURA: colores del producto que califican para el modo ('claro' | 'negro'),
    ordenados por preferencia."""
    if modo == "claro":
        return sorted((c for c in colores if es_color_claro(c)), key=_rank_claro)
    return sorted((c for c in colores if es_color_negro(c)), key=_rank_negro)


def foto_card_filename(producto_cod: str, colores: list[str], modo: str,
                       filenames: list[str] | None = None,
                       overrides_color: dict | None = None) -> tuple[str | None, bool]:
    """(filename, match) de la foto para la card del catálogo en el modo dado.
    match=True SOLO si existe foto de una variante de ese tono (no la portada).
    Sin firmar URLs: sirve para ordenar todo el catálogo barato."""
    prod = producto_cod.strip().upper()
    files = filenames if filenames is not None else indice_fotos().get(prod, [])
    if not files:
        return None, False
    candidatos = colores_por_modo(list(colores or []), modo)
    if candidatos:
        ov = overrides_color if overrides_color is not None else _overrides_fotos(prod)
        mapa = foto_por_color(prod, candidatos, files, ov)
        for c in candidatos:
            fn = mapa.get(norm(c))
            if fn:
                return fn, True
    return _portada_filename(prod, files), False


def foto_card(producto_cod: str, colores: list[str], modo: str) -> str:
    """URL (firmada) de la foto de la card en el modo dado; portada si no hay
    variante de ese tono; placeholder si el producto no tiene fotos."""
    fn, _ = foto_card_filename(producto_cod, colores, modo)
    return url_foto(producto_cod, fn) if fn else PLACEHOLDER


def foto_clara(producto_cod: str, colores: list[str]) -> str:
    """URL de la foto de la variante clara del producto ("Encender el sitio")."""
    return foto_card(producto_cod, colores, "claro")


def tiene_fotos(producto_cod: str) -> bool:
    return bool(indice_fotos().get(producto_cod.strip().upper()))


# ---------------------------------------------------------------------------
# Foto ↔ VARIANTE (fase 9 — port de pipeline/images.py del Woo)
# ---------------------------------------------------------------------------
FUZZY_THRESHOLD = 0.85


def _resolver_color_fuzzy(color_norm: str, candidatos_norm: list[str]) -> str | None:
    """Mejor candidato para un color con typos (port del Woo): inclusión
    ponderada o difflib; umbral 0.85 y sin ambigüedad (dos parecidos → None)."""
    import difflib

    if not color_norm or not candidatos_norm:
        return None
    scored = []
    for c in candidatos_norm:
        if color_norm in c or c in color_norm:
            score = min(len(color_norm), len(c)) / max(len(color_norm), len(c))
        else:
            score = difflib.SequenceMatcher(None, color_norm, c).ratio()
        scored.append((score, c))
    scored.sort(reverse=True)
    best_score, best = scored[0]
    if best_score < FUZZY_THRESHOLD:
        return None
    if len(scored) > 1 and scored[1][0] >= best_score - 0.05:
        return None
    return best


def foto_por_color(producto_cod: str, colores_catalogo: list[str],
                   filenames: list[str] | None = None,
                   overrides_color: dict | None = None) -> dict[str, str]:
    """{color_catalogo_NORM: filename} — la foto principal de cada color.
    Matching exacto por nombre normalizado + fuzzy para typos (el mismo
    criterio que arma el imagenes.csv del pipeline Woo). `overrides_color`
    ({color: filename}, cargado por el admin) pisa el matching automático."""
    prod = producto_cod.strip().upper()
    files = filenames if filenames is not None else indice_fotos().get(prod, [])
    fotos = parsear_fotos(producto_cod, files, colores_catalogo)
    colores_norm = [norm(c) for c in colores_catalogo if c]

    main_by_color: dict[str, dict] = {}
    for f in fotos:
        c = f["color_norm"]
        if not c:
            continue
        cur = main_by_color.get(c)
        if cur is None or (f["is_main"] and not cur["is_main"]) \
                or (f["is_main"] == cur["is_main"] and f["order"] < cur["order"]):
            main_by_color[c] = f

    out: dict[str, str] = {}
    for cfoto, f in sorted(main_by_color.items()):
        destino = cfoto if cfoto in colores_norm else _resolver_color_fuzzy(cfoto, colores_norm)
        if destino and destino not in out:
            out[destino] = f["filename"]
    for c, fn in (overrides_color or {}).items():
        cn = norm(c)
        if fn and fn in files:
            out[cn] = fn
        elif not fn:
            out.pop(cn, None)
    return out


def _overrides_fotos(producto_cod: str) -> dict:
    """fotos_color del override del producto ({} si no hay o sin Firestore)."""
    try:
        import overrides as _ov
        o = _ov.get_catalogo_overrides().get(producto_cod.strip().upper(), {})
        return o.get("fotos_color") or {}
    except Exception:  # noqa: BLE001 — tests / local sin Firestore
        return {}


def miniatura(producto_cod: str, color: str | None = None) -> str:
    """URL (firmada) de la miniatura de una VARIANTE: la foto de SU color
    (matching automático o asignación manual del admin); portada si no."""
    fn = foto_variante_filename(producto_cod, color)
    return url_foto(producto_cod.strip().upper(), fn) if fn else PLACEHOLDER


def mapeo_variantes(variantes: list[dict], indice: dict[str, list[str]] | None = None,
                    overrides_por_prod: dict | None = None) -> list[dict]:
    """Mapa foto ↔ variante para exportar/auditar (equivalente al imagenes.csv
    del Woo): [{producto_cod, sku, color, talle, foto, origen}] con
    origen = color (automático) | manual (override) | portada | sin_foto."""
    idx = indice if indice is not None else indice_fotos()
    ovs = overrides_por_prod or {}
    por_prod: dict[str, list[dict]] = {}
    for v in variantes:
        por_prod.setdefault(str(v["producto_cod"]).strip().upper(), []).append(v)
    out = []
    for prod, vs in sorted(por_prod.items()):
        files = idx.get(prod, [])
        colores = sorted({str(v.get("color") or "") for v in vs if v.get("color")})
        ov_fotos = (ovs.get(prod) or {}).get("fotos_color") or {}
        mapa = foto_por_color(prod, colores, files, ov_fotos) if files else {}
        portada = None
        if files:
            pf = parsear_fotos(prod, files, colores)
            portada = pf[0]["filename"] if pf else None
        manual_norm = {norm(c) for c, fn in ov_fotos.items() if fn}
        for v in sorted(vs, key=lambda x: (str(x.get("color") or ""), str(x.get("talle") or ""))):
            cn = norm(str(v.get("color") or ""))
            fn = mapa.get(cn)
            if fn:
                origen = "manual" if cn in manual_norm else "color"
            elif portada:
                fn, origen = portada, "portada"
            else:
                fn, origen = "", "sin_foto"
            out.append({"producto_cod": prod, "sku": v["sku"], "color": v.get("color", ""),
                        "talle": v.get("talle", ""), "foto": fn, "origen": origen})
    return out
