"""Mayorista B2B Chimola/Lautin — UI Streamlit.

Páginas: login → catálogo → producto → carrito → mis pedidos.
Sesión: `st.session_state` + cookie JWT (24h) para sobrevivir al refresh.
"""
from __future__ import annotations

import base64
import logging
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import admin_ui
import auth
import catalog
import compra_rapida as cr
import config
import fotos
import overrides
import pedidos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

st.set_page_config(page_title="Mayorista Chimola", page_icon="🛍️", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource(show_spinner=False)
def _warmup() -> bool:
    """Una vez por proceso: precarga catálogo + índice de fotos en un thread para
    que el cold start (~12s BQ + ~20s listado GCS) se solape con el login."""
    import threading

    def run():
        for fn in (catalog.load_variantes, fotos.indice_fotos):
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("warmup %s falló", fn.__name__)

    threading.Thread(target=run, name="warmup", daemon=True).start()
    return True


_warmup()

# Identidad Lautin (tomada del WP: Elementor global → Lato, #1C1C1A, #AC9B91, #F2F2F2)
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap');
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
  .stMarkdown, .stButton, .stTextInput, .stSelectbox, .stMultiSelect, .stNumberInput, .stDataFrame,
  [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] div, [data-testid="stAppViewContainer"] span,
  [data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] button,
  [data-testid="stAppViewContainer"] input, [data-testid="stAppViewContainer"] textarea,
  h1, h2, h3, h4, h5 {font-family: 'Lato', 'Helvetica Neue', Arial, sans-serif !important;}
  h1, h2, h3 {font-weight: 900 !important; letter-spacing: -.01em;}
  .block-container {padding-top: .4rem; padding-bottom: 1rem; max-width: 1280px;}
  header[data-testid="stHeader"] {background: transparent;}

  /* Top bar + header (como lautin.com.ar) */
  .lt-topbar {background:#1C1C1A; color:#fff; font-size:.82rem; padding:.45rem 1rem; display:flex;
              justify-content:space-between; align-items:center; letter-spacing:.02em; border-radius:0 0 6px 6px;}
  .lt-topbar a {color:#fff; text-decoration:none;}
  .lt-header {display:flex; align-items:center; gap:1.2rem; padding:.7rem .2rem .5rem; border-bottom:1px solid #e8e8e8;}
  .lt-header img {height:44px;}
  .lt-header .lt-tag {font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:#AC9B91; font-weight:700;}
  .lt-user {margin-left:auto; text-align:right; font-size:.82rem; color:#666; line-height:1.25;}
  .lt-user b {color:#1C1C1A;}
  .lt-hero img {border-radius:10px;}
  .lt-kicker {text-align:center; letter-spacing:.16em; text-transform:uppercase; font-size:.8rem; color:#1C1C1A; margin:.6rem 0 .2rem;}
  .lt-footer {background:#1C1C1A; color:#cfcfcf; padding:1.6rem 1.6rem 1.2rem; margin-top:2.5rem; border-radius:8px;
              display:grid; grid-template-columns:repeat(3, 1fr); gap:1rem; font-size:.84rem;}
  .lt-footer h5 {color:#fff; font-weight:700; font-size:.8rem; letter-spacing:.12em; text-transform:uppercase; margin:0 0 .55rem;}
  .lt-footer a {color:#fff; text-decoration:none;}
  .lt-copy {grid-column:1 / -1; border-top:1px solid #333; padding-top:.7rem; margin-top:.4rem; color:#888; font-size:.76rem;}

  /* Botones pill negros (INGRESAR AHORA) */
  .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {border-radius:999px !important; font-weight:700 !important;
        letter-spacing:.02em; text-transform:uppercase; font-size:.72rem !important; white-space:nowrap; padding:.4rem .7rem;}
  .stButton > button[kind="secondary"], .stDownloadButton > button {border:1px solid #1C1C1A !important; color:#1C1C1A !important; background:#fff !important;}
  .stButton > button[kind="secondary"]:hover {background:#1C1C1A !important; color:#fff !important;}
  div[data-testid="stSegmentedControl"] button {font-weight:700; letter-spacing:.06em; text-transform:uppercase; font-size:.78rem;}

  /* Cards del catálogo */
  div[class*="st-key-card_"] > div {border-color:#ececec !important; border-radius:10px !important;}
  div[data-testid="stImage"] img {border-radius:8px;}
  /* solo las cards (contenedor con borde) recortan a cuadrado; banners y galería quedan naturales */
  div[class*="st-key-card_"] div[data-testid="stImage"] img {object-fit:cover; aspect-ratio:1/1; background:#F2F2F2;}
  .card-title {font-weight:700; font-size:.95rem; margin-top:.4rem; line-height:1.2;
               white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#1C1C1A;}
  .card-sub {color:#7A7A7A; font-size:.78rem;}
  .card-price {font-weight:900; font-size:1.08rem; margin-top:.2rem; color:#1C1C1A;}
  .muted {color:#7A7A7A; font-size:.85rem;}
  .total-box {background:#F2F2F2; border-radius:10px; padding:1rem 1.2rem; border:1px solid #e5e5e5;}
  .lt-login-card {background:#fff; border:1px solid #ececec; border-radius:10px; padding:1.4rem 1.6rem .6rem;}
  [data-testid="stSidebar"] {border-right:1px solid #e8e8e8;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_money(n) -> str:
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return f"$ {float(n):,.0f}".replace(",", ".")


STATIC = Path(__file__).resolve().parent / "static"
WHATSAPP = "+54 9 11 3680 8217"
MARCAS = ["Chimola", "Lima"]


@lru_cache(maxsize=8)
def static_b64(name: str) -> str:
    """data URI de un asset chico de static/ (logo)."""
    p = STATIC / name
    mime = "image/png" if p.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def topbar() -> None:
    st.markdown(f"<div class='lt-topbar'><span>Venta exclusiva mayorista</span>"
                f"<span>📞 <a href='https://wa.me/{WHATSAPP.replace(' ', '').replace('+', '')}' target='_blank'>{WHATSAPP}</a></span></div>",
                unsafe_allow_html=True)


def _sync_marca_from_header() -> None:
    v = st.session_state.get("hdr_marca")
    st.session_state.f_marca = [v] if v in MARCAS else []
    st.session_state.page = "catalogo"   # elegir marca desde el header siempre lleva al catálogo


def header(con_marcas: bool = True) -> None:
    """Logo Lautin + selector de marca (CHIMOLA / LIMA, sincronizado con el filtro) + usuario."""
    user = st.session_state.get("user")
    cli = cliente_efectivo() if user else None
    c1, c2, c3 = st.columns([1, 2.4, 1.8], vertical_alignment="center")
    with c1:
        st.markdown(f"<div class='lt-header' style='border:0'><img src='{static_b64('logo_lautin.png')}' alt='Lautin'></div>",
                    unsafe_allow_html=True)
    with c2:
        if con_marcas and user:
            actual = st.session_state.get("f_marca", [])
            st.session_state.hdr_marca = actual[0] if len(actual) == 1 and actual[0] in MARCAS else "Todo"
            st.segmented_control("Marca", ["Todo"] + MARCAS, key="hdr_marca", label_visibility="collapsed",
                                 on_change=_sync_marca_from_header)
    with c3:
        if user:
            n_items = sum(int(i["cantidad"]) for i in st.session_state.get("cart", []))
            st.markdown(f"<div class='lt-user'><b>{cli['nombre_display']}</b><br>{user['email']} · 🛒 {n_items} u.</div>",
                        unsafe_allow_html=True)
    st.markdown("<div style='border-bottom:1px solid #e8e8e8; margin:-.2rem 0 .9rem'></div>", unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f"""<div class='lt-footer'>
      <div><h5>Nuestras marcas</h5><b style='color:#fff'>CHIMOLA</b><br><b style='color:#fff'>LIMA</b></div>
      <div><h5>Contactanos</h5>📞 {WHATSAPP}<br><a href='https://instagram.com/chimolaoficial' target='_blank'>@chimolaoficial</a><br>
           <a href='https://instagram.com/lima.oficial' target='_blank'>@lima.oficial</a></div>
      <div><h5>Información relevante</h5>Los pedidos se confirman por email con el Excel adjunto.<br>
           Sin pago online: el equipo de Lautin coordina la entrega y facturación.</div>
      <div class='lt-copy'>© 2026 Lautin Accesorios. Todos los derechos reservados.{" · Ambiente " + config.APP_ENV.upper() if config.APP_ENV != "prod" else ""}</div>
    </div>""", unsafe_allow_html=True)


def _is_https() -> bool:
    try:
        h = st.context.headers
        return h.get("X-Forwarded-Proto", "").lower() == "https" or "run.app" in h.get("Host", "")
    except Exception:  # noqa: BLE001
        return False


def set_cookie(token: str) -> None:
    secure = "; Secure" if _is_https() else ""
    components.html(
        f"<script>(function(){{var d=window.parent&&window.parent.document?window.parent.document:document;"
        f"d.cookie='{config.COOKIE_NAME}={token}; path=/; max-age={config.JWT_TTL_HORAS * 3600}; SameSite=Lax{secure}';}})();</script>",
        height=0, width=0)


def clear_cookie() -> None:
    components.html(
        f"<script>(function(){{var d=window.parent&&window.parent.document?window.parent.document:document;"
        f"d.cookie='{config.COOKIE_NAME}=; path=/; max-age=0';}})();</script>", height=0, width=0)


def read_cookie() -> str | None:
    try:
        return st.context.cookies.get(config.COOKIE_NAME)
    except Exception:  # noqa: BLE001
        return None


def cargar_sesion(user: dict) -> None:
    st.session_state.user = user
    st.session_state.logged_out = False
    cliente = None
    if user.get("cliente_cod") is not None:
        try:
            cliente = catalog.get_cliente(int(user["cliente_cod"]))
        except Exception:  # noqa: BLE001
            log.exception("No pude leer dim_cliente para %s", user.get("cliente_cod"))
        if cliente is None:
            st.session_state.cliente_error = (f"El cliente {user['cliente_cod']} no existe en dim_cliente. "
                                              "Avisá a Chimola.")
    st.session_state.cliente = cliente
    st.session_state.cart = pedidos.cargar_carrito(user["email"])
    st.session_state.page = "catalogo"


def usuario_actual() -> dict | None:
    if st.session_state.get("user"):
        return st.session_state.user
    # st.context.cookies refleja las cookies del handshake del websocket (no se
    # actualiza cuando JS las borra): tras un logout NO restaurar desde cookie.
    if st.session_state.get("logged_out"):
        return None
    claims = auth.verify_jwt(read_cookie())
    if claims:
        user = auth.get_usuario(claims["sub"])
        if user and user.get("activo", True):
            cargar_sesion(user)
            return user
    return None


def logout() -> None:
    for k in ("user", "cliente", "cart", "page", "producto_sel", "cliente_error", "pedido_ok"):
        st.session_state.pop(k, None)
    st.session_state.logged_out = True


def cliente_efectivo() -> dict:
    """Cliente para precios. Admin sin cliente_cod → lista 1 sin descuento (solo navega)."""
    c = st.session_state.get("cliente")
    if c:
        return c
    return {"cliente_cod": None, "nombre_display": "Admin (sin cliente)", "lista_precios": 1, "descuento": 0.0}


def puede_pedir() -> bool:
    return bool(st.session_state.get("cliente"))


def guardar_cart(items: list[dict]) -> None:
    st.session_state.cart = items
    pedidos.guardar_carrito(st.session_state.user["email"], items)


def ir(page: str, **kw) -> None:
    st.session_state.page = page
    for k, v in kw.items():
        st.session_state[k] = v
    st.rerun()


def df_catalogo() -> pd.DataFrame:
    with st.spinner("Cargando catálogo..."):
        df = catalog.variantes_publicadas()   # BQ + overrides del admin
    return catalog.con_precio(df, cliente_efectivo()["lista_precios"])


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def page_login() -> None:
    if st.session_state.get("logged_out"):
        clear_cookie()   # se renderiza acá (run completo) y no en el handler del botón
    st.markdown("<p class='lt-kicker'>Logueate y descubrí todo nuestro catálogo</p>", unsafe_allow_html=True)
    col_img, col = st.columns([1.45, 1], gap="large", vertical_alignment="center")
    with col_img:
        st.image(str(STATIC / "banner_1.jpg"), use_container_width=True)
    with col:
        with st.container(border=True):
            st.markdown("### Ya tengo cuenta")
            st.caption("Completá tus datos e ingresá al catálogo mayorista.")
            with st.form("login", border=False):
                email = st.text_input("Email", autocomplete="username")
                pwd = st.text_input("Contraseña", type="password", autocomplete="current-password")
                ok = st.form_submit_button("Ingresar ahora", type="primary", use_container_width=True)
        if ok:
            token, user, err = auth.login(email, pwd)
            if err:
                st.error(err)
            else:
                # La cookie se escribe en el PRÓXIMO run (ver main): un st.rerun()
                # inmediato descartaría el iframe JS antes de llegar al browser.
                st.session_state.pending_cookie = token
                cargar_sesion(user)
                st.rerun()
        st.markdown('<p class="muted">¿No tenés cuenta? Pedila al equipo de Chimola.</p>', unsafe_allow_html=True)
        if config.APP_ENV != "prod":
            st.caption(f"Ambiente: **{config.APP_ENV.upper()}** · proyecto `{config.GCP_PROJECT}`")


# ---------------------------------------------------------------------------
# Layout común
# ---------------------------------------------------------------------------
def sidebar() -> None:
    user, cli = st.session_state.user, cliente_efectivo()
    with st.sidebar:
        st.markdown(f"<img src='{static_b64('logo_lautin.png')}' style='height:34px'>", unsafe_allow_html=True)
        st.markdown(f"**{cli['nombre_display']}**  \n<span class='muted'>{user['email']}</span>",
                    unsafe_allow_html=True)
        if puede_pedir():
            st.caption(f"Cliente {cli['cliente_cod']} · lista {cli['lista_precios']} · "
                       f"desc. cabecera {cli['descuento']:g}%")
        elif user.get("rol") == "admin":
            st.caption("Rol admin · solo navegación e historial")
        if st.session_state.get("cliente_error"):
            st.warning(st.session_state.cliente_error)
        st.divider()
        n_items = sum(int(i["cantidad"]) for i in st.session_state.get("cart", []))
        page = st.session_state.get("page", "catalogo")
        if st.button("📚 Catálogo", use_container_width=True,
                     type="primary" if page in ("catalogo", "producto") else "secondary"):
            ir("catalogo")
        if puede_pedir() and st.button("⚡ Compra rápida", use_container_width=True,
                                       type="primary" if page == "compra_rapida" else "secondary"):
            ir("compra_rapida")
        if st.button(f"🛒 Carrito ({n_items})", use_container_width=True,
                     type="primary" if page == "carrito" else "secondary"):
            ir("carrito")
        if st.button("📦 Mis pedidos", use_container_width=True,
                     type="primary" if page == "pedidos" else "secondary"):
            ir("pedidos")
        if user.get("rol") == "admin":
            try:
                sin_procesar = pedidos.contar_por_estado().get("confirmado", 0)
            except Exception:  # noqa: BLE001
                sin_procesar = 0
            label_admin = "🛠 Administración" + (f" ({sin_procesar})" if sin_procesar else "")
            if st.button(label_admin, use_container_width=True,
                         type="primary" if page == "admin" else "secondary"):
                ir("admin")
        st.divider()
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()
        hace = catalog.catalogo_actualizado_hace()
        if hace >= 0:
            st.caption(f"Catálogo actualizado hace {hace // 60} min")
        if user.get("rol") == "admin" and st.button("↻ Refrescar catálogo", use_container_width=True):
            catalog.load_variantes(force=True)
            fotos.indice_fotos(force=True)
            st.rerun()
        if config.APP_ENV != "prod":
            st.caption(f"Ambiente {config.APP_ENV.upper()}")


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def page_catalogo() -> None:
    df = df_catalogo()
    # Hero del slider de lautin.com.ar: banner Chimola ("ON THE GO") o Lima según marca elegida
    marca_sel = st.session_state.get("f_marca", [])
    banner = "banner_2.jpg" if marca_sel == ["Lima"] else "banner_1.jpg"
    if st.session_state.get("cat_pagina", 1) == 1 and not st.session_state.get("f_busqueda"):
        st.image(str(STATIC / banner), use_container_width=True)
    banner_texto = overrides.get_config().get("banner_texto")
    if banner_texto:
        st.info(banner_texto, icon="📣")
    st.markdown("## Catálogo")

    with st.sidebar:
        st.markdown("#### Filtros")
        busqueda = st.text_input("Buscar (código, nombre, EAN, color)", key="f_busqueda",
                                 placeholder="Ej: M211, mochila, rainbow")
        sel = {f: st.session_state.get(f"f_{f}", []) for f in catalog.FILTROS}
        opciones = catalog.opciones_filtros(df, sel)
        labels = {"marca": "Marca", "temporada": "Temporada", "rubro": "Rubro", "subrubro": "Subrubro"}
        for f in catalog.FILTROS:
            if not opciones[f] and not sel[f]:
                continue
            sel[f] = st.multiselect(labels[f], opciones[f], key=f"f_{f}")
        solo_fotos = st.checkbox("Solo productos con foto", value=True, key="f_fotos")
        if st.button("Limpiar filtros", use_container_width=True):
            for f in catalog.FILTROS:
                st.session_state.pop(f"f_{f}", None)
            st.session_state.pop("f_busqueda", None)
            st.session_state.pop("f_fotos", None)
            st.rerun()

    variantes = catalog.filtrar_variantes(df, sel, busqueda)
    prods = catalog.productos(variantes)
    if solo_fotos and not prods.empty:
        prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]

    # Paginación (reset al cambiar filtros)
    firma = (busqueda, tuple(tuple(v) for v in sel.values()), solo_fotos)
    if st.session_state.get("cat_firma") != firma:
        st.session_state.cat_firma, st.session_state.cat_pagina = firma, 1
    por_pag = config.ITEMS_POR_PAGINA
    total = len(prods)
    n_pag = max(1, math.ceil(total / por_pag))
    pag = min(st.session_state.get("cat_pagina", 1), n_pag)

    c1, c2 = st.columns([3, 1])
    c1.caption(f"{total} productos · {len(variantes)} variantes con stock en depósito · "
               f"precios lista {cliente_efectivo()['lista_precios']} (sin descuento cabecera)")
    with c2:
        pag = st.number_input("Página", min_value=1, max_value=n_pag, value=pag, step=1,
                              key="cat_pagina_input", label_visibility="collapsed")
        st.session_state.cat_pagina = int(pag)
    if total == 0:
        st.info("No hay productos con stock para esos filtros.")
        return

    sub = prods.iloc[(pag - 1) * por_pag: pag * por_pag]
    cols = st.columns(4)
    for i, (_, p) in enumerate(sub.iterrows()):
        with cols[i % 4]:
            with st.container(border=True, key=f"card_{p['producto_cod']}"):
                st.image(fotos.foto_principal(p["producto_cod"]), use_container_width=True)
                st.markdown(f"<div class='card-title' title='{p['producto_nombre']}'>{p['producto_nombre']}</div>"
                            f"<div class='card-sub'>{p['producto_cod']} · {p['marca'] or ''} · {p['temporada'] or ''}</div>"
                            f"<div class='card-price'>{fmt_money(p['precio'])}</div>"
                            f"<div class='card-sub'>{int(p['stock'])} u. · {len(p['colores'])} color(es) · "
                            f"{int(p['n_variantes'])} variante(s)</div>", unsafe_allow_html=True)
                if st.button("Ver producto", key=f"ver_{p['producto_cod']}", use_container_width=True):
                    ir("producto", producto_sel=p["producto_cod"])
    st.caption(f"Página {pag} de {n_pag}")


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------
def page_producto() -> None:
    cod = st.session_state.get("producto_sel")
    df = df_catalogo()
    prod = catalog.get_producto(df, cod) if cod else None
    if st.button("← Volver al catálogo"):
        ir("catalogo")
    if not prod:
        st.warning("Producto no disponible (sin stock o no existe).")
        return
    cli = cliente_efectivo()

    col_img, col_info = st.columns([1.05, 1])
    with col_img:
        galeria = fotos.fotos_producto(cod, prod["colores"])
        if galeria:
            color_foto = st.selectbox("Ver fotos del color", ["Todas"] + prod["colores"], key="foto_color")
            visibles = galeria if color_foto == "Todas" else fotos.fotos_por_color(galeria, color_foto)
            idx = 0
            if len(visibles) > 1:
                idx = st.radio("Foto", range(len(visibles)), horizontal=True, key=f"foto_idx_{cod}_{color_foto}",
                               format_func=lambda i: str(i + 1), label_visibility="collapsed")
            st.image(visibles[idx]["url"], use_container_width=True)
            if len(visibles) > 1:
                thumbs = st.columns(min(len(visibles), 8))
                for j, f in enumerate(visibles[:16]):
                    with thumbs[j % 8]:
                        st.image(f["url"], use_container_width=True)
        else:
            st.image(fotos.PLACEHOLDER, use_container_width=True)
            st.caption("Este producto todavía no tiene fotos cargadas.")

    with col_info:
        st.markdown(f"## {prod['producto_nombre']}")
        st.markdown(f"**{prod['producto_cod']}** · {prod['marca'] or ''} · {prod['temporada'] or ''} · "
                    f"{prod['rubro'] or ''}{(' / ' + prod['subrubro']) if prod.get('subrubro') else ''}")
        if prod["precio"] is None:
            st.error(f"Este producto no tiene precio cargado en la lista {cli['lista_precios']}. "
                     "No se puede pedir — consultá a Chimola.")
        else:
            iva_tag = " + IVA" if float(overrides.get_config().get("iva_pct") or 0) > 0 else ""
            st.markdown(f"### {fmt_money(prod['precio'])} <span class='muted'>precio lista {cli['lista_precios']}{iva_tag}</span>",
                        unsafe_allow_html=True)
            if cli.get("descuento"):
                st.caption(f"Con tu descuento cabecera ({cli['descuento']:g}%): "
                           f"**{fmt_money(catalog.aplicar_descuento(prod['precio'], cli['descuento']))}** por unidad")
        if prod.get("descripcion"):
            st.markdown(f"<p class='muted'>{prod['descripcion']}</p>", unsafe_allow_html=True)

        st.markdown("#### Variantes y cantidades")
        ub = int(prod.get("ub") or 0)   # múltiplo/mínimo por variante (U.B. del admin)
        if ub > 1:
            st.caption(f"📦 Este producto se vende en múltiplos de **{ub} unidades** por variante.")
        ver = st.session_state.get("qty_ver", 0)
        seleccion = []
        por_color: dict[str, list[dict]] = {}
        for v in prod["variantes"]:
            por_color.setdefault(v["color"], []).append(v)
        for color, vs in por_color.items():
            st.markdown(f"**{color}**")
            filas = [vs[k:k + 4] for k in range(0, len(vs), 4)]
            for fila in filas:
                cc = st.columns(4)
                for k, v in enumerate(fila):
                    with cc[k]:
                        paso = ub if ub > 1 else 1
                        tope = (int(v["stock"]) // paso) * paso
                        q = st.number_input(f"T {v['talle']} · stock {int(v['stock'])}", min_value=0,
                                            max_value=max(tope, 0), value=0, step=paso,
                                            key=f"qty_{ver}_{v['sku']}",
                                            disabled=prod["precio"] is None or tope <= 0)
                        if q > 0:
                            seleccion.append((v, int(q)))
        total_sel = sum(q for _, q in seleccion)
        if prod["precio"] is not None:
            st.caption(f"Seleccionadas: {total_sel} u. · {fmt_money(total_sel * prod['precio'])} (precio lista)")
        if st.button("🛒 Agregar al carrito", type="primary", disabled=not seleccion or not puede_pedir(),
                     use_container_width=True):
            items = st.session_state.cart
            for v, q in seleccion:
                items = pedidos.agregar_al_carrito(items, {
                    "sku": v["sku"], "ean": v["ean"], "producto_cod": prod["producto_cod"],
                    "producto_nombre": prod["producto_nombre"], "color_cod": str(v["color_cod"]),
                    "color": v["color"], "talle": v["talle"], "cantidad": q,
                    "precio_unit": float(v["precio"]), "stock": int(v["stock"]),
                })
            guardar_cart(items)
            st.session_state.qty_ver = ver + 1
            st.toast(f"Agregadas {total_sel} unidades al carrito", icon="✅")
            st.rerun()
        if not puede_pedir():
            st.caption("Tu usuario no tiene cliente asociado: podés navegar pero no pedir.")


# ---------------------------------------------------------------------------
# Carrito
# ---------------------------------------------------------------------------
def page_carrito() -> None:
    st.markdown("## Carrito")
    cli = cliente_efectivo()
    items = st.session_state.get("cart", [])

    if st.session_state.get("pedido_ok"):
        p, xlsx = st.session_state.pedido_ok
        st.success(f"✅ Pedido **N° {p['numero']}** confirmado · {p['unidades']} unidades · total {fmt_money(p['total'])}")
        em = p.get("email") or {}
        if em.get("enviado"):
            st.info(f"Te enviamos el Excel a: {', '.join(em['destinatarios'])}")
        else:
            st.warning(f"El pedido quedó registrado pero el email no salió ({em.get('error')}). "
                       "Descargá el Excel acá y avisá a Chimola.")
        st.download_button("⬇️ Descargar Excel del pedido", data=xlsx, file_name=p["xlsx_filename"],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        if st.button("Hacer otro pedido"):
            st.session_state.pop("pedido_ok")
            ir("catalogo")
        return

    if not items:
        st.info("El carrito está vacío.")
        if st.button("Ir al catálogo"):
            ir("catalogo")
        return

    df = pd.DataFrame(items)
    df["foto"] = df["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    df["subtotal"] = df["cantidad"].astype(int) * df["precio_unit"].astype(float)
    df["quitar"] = False
    cols = ["foto", "producto_cod", "producto_nombre", "color", "talle", "stock", "cantidad", "precio_unit", "subtotal", "quitar"]
    edited = st.data_editor(
        df[cols], hide_index=True, use_container_width=True, key="cart_editor",
        disabled=[c for c in cols if c not in ("cantidad", "quitar")],
        column_config={
            "foto": st.column_config.ImageColumn("", width="small"),
            "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color", "talle": "Talle",
            "stock": st.column_config.NumberColumn("Stock", format="%d"),
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, format="%d"),
            "precio_unit": st.column_config.NumberColumn("Precio lista", format="$ %.0f"),
            "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.0f"),
            "quitar": st.column_config.CheckboxColumn("Quitar"),
        },
    )
    # Aplicar cambios (cantidad / quitar)
    cambios = False
    nuevos = []
    for it, (_, row) in zip(items, edited.iterrows()):
        if bool(row["quitar"]) or int(row["cantidad"]) <= 0:
            cambios = True
            continue
        q = min(int(row["cantidad"]), int(it.get("stock") or row["cantidad"]))
        if q != int(it["cantidad"]):
            cambios = True
        nuevos.append({**it, "cantidad": q})
    if cambios:
        guardar_cart(nuevos)
        st.rerun()

    iva_pct = float(overrides.get_config().get("iva_pct") or 0)
    tot = pedidos.calcular_totales([dict(i) for i in items], cli.get("descuento", 0), iva_pct=iva_pct)
    iva_html = ""
    if iva_pct > 0:
        iva_html = (f"<div class='muted'>IVA {tot['iva_pct']:g}%: {fmt_money(tot['iva_monto'])}</div>"
                    f"<div class='muted'>Total c/IVA: <b>{fmt_money(tot['total_con_iva'])}</b></div>")
    c1, c2 = st.columns([2, 1])
    with c2:
        st.markdown(f"""<div class='total-box'>
          <div>Unidades: <b>{tot['unidades']}</b></div>
          <div>Subtotal (lista {cli['lista_precios']}{', sin IVA' if iva_pct > 0 else ''}): <b>{fmt_money(tot['subtotal'])}</b></div>
          <div>Descuento cabecera {tot['descuento_pct']:g}%: <b>-{fmt_money(tot['descuento_monto'])}</b></div>
          <div style='font-size:1.3rem;margin-top:.4rem'>TOTAL: <b>{fmt_money(tot['total'])}</b></div>
          {iva_html}
          </div>""", unsafe_allow_html=True)
    with c1:
        if not puede_pedir():
            st.warning("Tu usuario no tiene cliente asociado; no podés confirmar pedidos.")
        # Form: observaciones + botón viajan en UN solo evento (si no, el cambio del
        # textarea dispara un rerun que interrumpe el script en medio de la confirmación).
        with st.form("confirmar_form", border=False):
            obs = st.text_area("Observaciones para Chimola (opcional)", height=100)
            confirmar = st.form_submit_button("✅ Confirmar pedido", type="primary", use_container_width=True,
                                              disabled=not puede_pedir())
        if confirmar and not st.session_state.get("confirmando"):
            st.session_state.confirmando = True   # guard contra doble submit
            try:
                with st.spinner("Validando stock y generando el pedido..."):
                    p, xlsx = pedidos.confirmar_pedido(st.session_state.user, cli, items, obs)
                    # Guardar estado ANTES de que el spinner se cierre (cualquier st.* puede
                    # ser interrumpido por un rerun; session_state no).
                    st.session_state.cart = []
                    st.session_state.pedido_ok = (p, xlsx)
                    st.session_state.confirmando = False
                st.rerun()
            except pedidos.StockInsuficiente as e:
                st.session_state.confirmando = False
                disp = {x["sku"]: x["disponible"] for x in e.problemas}
                st.error("Cambió el stock de algunos ítems. Ajustamos el carrito a lo disponible; revisá y volvé a confirmar.")
                st.dataframe(pd.DataFrame(e.problemas), hide_index=True)
                ajust = []
                for it in items:
                    if it["sku"] in disp:
                        if disp[it["sku"]] <= 0:
                            continue
                        it = {**it, "cantidad": disp[it["sku"]], "stock": disp[it["sku"]]}
                    ajust.append(it)
                guardar_cart(ajust)
                catalog.load_variantes(force=True)
            except pedidos.MinimoNoAlcanzado as e:
                st.session_state.confirmando = False
                st.error(f"El pedido mínimo es de {e.minimo} unidades y tenés {e.unidades}. "
                         "Agregá más productos para confirmar.")
            except Exception as e:  # noqa: BLE001
                st.session_state.confirmando = False
                log.exception("Error confirmando pedido")
                st.error(f"No se pudo confirmar el pedido: {e}")
        if st.button("Vaciar carrito"):
            guardar_cart([])
            st.rerun()


# ---------------------------------------------------------------------------
# Mis pedidos
# ---------------------------------------------------------------------------
def page_pedidos() -> None:
    user = st.session_state.user
    es_admin = user.get("rol") == "admin"
    st.markdown("## Mis pedidos" if not es_admin else "## Pedidos (todos los clientes)")
    cliente_cod = None if es_admin else (st.session_state.get("cliente") or {}).get("cliente_cod")
    if not es_admin and cliente_cod is None:
        st.info("Tu usuario no tiene cliente asociado.")
        return
    with st.spinner("Buscando pedidos..."):
        lista = pedidos.listar_pedidos(cliente_cod)
    if not lista:
        st.info("Todavía no hay pedidos.")
        return
    rows = [{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""), "Cliente": f"{p['cliente_cod']} · {p['cliente_nombre']}",
        "Usuario": p["usuario_email"], "Unidades": p["unidades"], "Total": p["total"], "Estado": p["estado"],
        "Email": "✅" if (p.get("email") or {}).get("enviado") else "❌",
    } for p in lista]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})

    nums = [p["numero"] for p in lista]
    sel = st.selectbox("Ver detalle / descargar Excel del pedido N°", nums)
    p = next(x for x in lista if x["numero"] == sel)
    st.markdown(f"**Pedido N° {p['numero']}** · {p['fecha_str']} · {p['cliente_nombre']} · "
                f"total {fmt_money(p['total'])} (desc. {p['descuento_pct']:g}%)")
    if p.get("observaciones"):
        st.caption(f"Obs: {p['observaciones']}")
    st.dataframe(pd.DataFrame(p["items"])[["producto_cod", "producto_nombre", "color", "talle", "cantidad",
                                            "precio_unit", "subtotal"]],
                 hide_index=True, use_container_width=True,
                 column_config={"precio_unit": st.column_config.NumberColumn("Precio lista", format="$ %.0f"),
                                "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.0f")})
    if puede_pedir() and st.button("🔁 Repetir este pedido", key=f"rep_{p['numero']}"):
        with st.spinner("Cargando el pedido al carrito con stock y precios actuales..."):
            items, avisos = pedidos.repetir_pedido(p, df_catalogo())
        for a in avisos:
            st.warning(a)
        if items:
            total = sum(i["cantidad"] for i in items)
            nuevos = st.session_state.cart
            for it in items:
                nuevos = pedidos.agregar_al_carrito(nuevos, it)
            guardar_cart(nuevos)
            st.toast(f"{total} unidades cargadas al carrito", icon="🔁")
            if not avisos:
                ir("carrito")
        else:
            st.error("Ninguna variante de ese pedido está disponible hoy.")
    if p.get("xlsx_gcs_path"):
        try:
            data = pedidos.descargar_backup(p["xlsx_gcs_path"])
            st.download_button("⬇️ Descargar Excel", data=data, file_name=p["xlsx_filename"],
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:  # noqa: BLE001
            st.warning(f"No pude traer el Excel del backup ({e}). Lo regenero:")
            st.download_button("⬇️ Descargar Excel (regenerado)", data=pedidos.generar_excel(p),
                               file_name=p["xlsx_filename"],
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.download_button("⬇️ Descargar Excel (regenerado)", data=pedidos.generar_excel(p),
                           file_name=p["xlsx_filename"],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# Compra rápida (SPECS §7)
# ---------------------------------------------------------------------------
def _agregar_items(items_nuevos: list[dict]) -> int:
    items = st.session_state.cart
    total = 0
    for it in items_nuevos:
        items = pedidos.agregar_al_carrito(items, it)
        total += int(it["cantidad"])
    guardar_cart(items)
    return total


def page_compra_rapida() -> None:
    st.markdown("## ⚡ Compra rápida")
    if not puede_pedir():
        st.info("Tu usuario no tiene cliente asociado; no podés pedir.")
        return
    df = df_catalogo()
    df = df[df["precio"].notna()]
    tab_tabla, tab_pegar = st.tabs(["📋 Tabla con miniaturas", "📄 Pegar códigos"])

    with tab_tabla:
        c1, c2, c3 = st.columns([2, 1.2, 1.2])
        busq = c1.text_input("Buscar", key="cr_busq", placeholder="código, nombre, EAN, color")
        marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="cr_marca")
        rubro = c3.multiselect("Rubro", sorted(df["rubro"].dropna().unique()), key="cr_rubro")
        sub = catalog.filtrar_variantes(df, {"marca": marca, "rubro": rubro}, busq).copy()
        por_pag = 25
        n_pag = max(1, -(-len(sub) // por_pag))
        cpag, cinfo = st.columns([1, 3])
        pag = int(cpag.number_input("Página", 1, n_pag, 1, key="cr_pag"))
        cinfo.caption(f"{len(sub)} variantes con stock y precio · página {pag}/{n_pag} · "
                      "cargá cantidades y tocá Agregar")
        page_df = sub.iloc[(pag - 1) * por_pag: pag * por_pag].copy()
        page_df["foto"] = page_df["producto_cod"].map(
            lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
        page_df["cantidad"] = 0
        ver = st.session_state.get("cr_ver", 0)
        edited = st.data_editor(
            page_df[["foto", "producto_cod", "producto_nombre", "color", "talle", "stock", "precio", "cantidad"]],
            hide_index=True, use_container_width=True, key=f"cr_editor_{pag}_{ver}",
            disabled=["foto", "producto_cod", "producto_nombre", "color", "talle", "stock", "precio"],
            column_config={
                "foto": st.column_config.ImageColumn("", width="small"),
                "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color", "talle": "Talle",
                "stock": st.column_config.NumberColumn("Stock", format="%d"),
                "precio": st.column_config.NumberColumn("Precio lista", format="$ %.0f"),
                "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, format="%d"),
            })
        seleccion = [(v, int(q)) for (_, v), q in zip(page_df.iterrows(), edited["cantidad"])
                     if int(q or 0) > 0]
        if st.button("🛒 Agregar al carrito", type="primary", disabled=not seleccion, key="cr_add"):
            items, ajustes = [], []
            for v, q in seleccion:
                q = min(q, int(v["stock"]))
                ub = int(v["ub"]) if ("ub" in v and pd.notna(v["ub"]) and v["ub"]) else 0
                if ub > 1 and q % ub:
                    q = (q // ub) * ub   # múltiplo U.B. (como el Woo)
                    ajustes.append(f"{v['sku']}: ajustado a múltiplo de {ub} → {q}")
                if q > 0:
                    items.append(cr.item_desde_variante(v, q))
            for a in ajustes:
                st.warning(a)
            if not items:
                st.warning("Las cantidades quedaron en 0 tras aplicar los múltiplos.")
                st.stop()
            total = _agregar_items(items)
            st.session_state.cr_ver = ver + 1
            st.toast(f"{total} unidades agregadas al carrito", icon="✅")
            st.rerun()

    with tab_pegar:
        st.caption("Una línea por variante: `SKU,cantidad` o `EAN,cantidad` (coma, punto y coma, "
                   "tab o espacio). Podés pegar directo desde Excel.")
        # Resultado del procesamiento anterior (post-rerun, así el contador del carrito ya está al día)
        if st.session_state.get("cr_resultado"):
            n, total, avisos = st.session_state.pop("cr_resultado")
            for a in avisos:
                st.warning(a)
            if n:
                st.success(f"{n} línea(s) · {total} unidades agregadas al carrito.")
            elif not avisos:
                st.info("No se reconoció ninguna línea.")
        with st.form("cr_pegar", border=False):
            texto = st.text_area("Códigos", height=180, placeholder="M211_U_2059,3\n7798218194446,2")
            ok = st.form_submit_button("Procesar y agregar", type="primary")
        if ok and texto.strip():
            items, avisos = cr.resolver_pegado(texto, df)
            total = _agregar_items(items) if items else 0
            st.session_state.cr_resultado = (len(items), total, avisos)
            st.rerun()


def page_admin() -> None:
    if st.session_state.user.get("rol") != "admin":
        st.error("Solo para administradores.")
        return
    admin_ui.page_admin()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def main() -> None:
    topbar()
    if usuario_actual() is None:
        header(con_marcas=False)
        page_login()
        footer()
        return
    tok = st.session_state.pop("pending_cookie", None)
    if tok:
        set_cookie(tok)
    sidebar()
    header()
    page = st.session_state.get("page", "catalogo")
    {"catalogo": page_catalogo, "producto": page_producto, "carrito": page_carrito,
     "pedidos": page_pedidos, "compra_rapida": page_compra_rapida,
     "admin": page_admin}.get(page, page_catalogo)()
    footer()


main()
