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

Paquete (2026-10-07, antes un solo `sitio.py`): `_store` (doc Firestore + cache), `home`,
`media`, `secciones`, `menu`. Todo lo público se re-exporta acá: `sitio.X` sigue funcionando.
"""
from __future__ import annotations

from sitio._store import get_home_raw, invalidar  # noqa: F401
from sitio.home import (  # noqa: F401
    DEFAULTS, FILTROS_BANNER, SECCIONES_HOME, TIPOS_SECCION, banner_catalogo, banners_de_categoria,
    banners_de_filtro, es_personalizada, get_home, home_visible, reset_home, set_banner_categoria,
    set_banner_filtro, set_home, sitio_get_home_safe,
)
from sitio.media import MEDIA_PREFIX, MEDIA_URL, es_media, leer_media, leer_media_url, subir_imagen  # noqa: F401
from sitio.menu import (  # noqa: F401
    MENU_AUTO_TOPE, MENU_LISTAS, get_menu, menu_auto, menu_efectivo, reset_menu, set_menu,
)
from sitio.secciones import SECCIONES, filtrar_seccion, seccion_de  # noqa: F401
