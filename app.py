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
import hashlib

import streamlit.components.v1 as components

import admin_ui
import auth
import catalog
import compra_rapida as cr
import config
import fotos
import overrides
import pedidos
import reposicion
import odoo_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

st.set_page_config(page_title="Lautin Mayorista", page_icon="static/logo_lautin.png", layout="wide",
                   initial_sidebar_state="collapsed")


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

# Identidad Broadsheet (handoff design_handoff_mayorista_ux: Source Serif 4,
# papel #f3f2f2, cian interactivo #0088b0, magenta solo errores, radio 2px)
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');
  :root { --bg:#f3f2f2; --text:#201e1d; --muted:#605d5d; --faint:#9b9797;
    --accent:#0088b0; --accent-h:#1186ac; --accent-press:#006786; --accent-tint:#e9f8ff;
    --alert:#d6006c; --alert-text:#aa0b56; --alert-tint:#fff1f4;
    --n200:#eae7e7; --divider:rgba(32,30,29,.16); }
  html, body, .stApp, [data-testid="stAppViewContainer"], .stMarkdown, .stButton, .stTextInput,
  .stSelectbox, .stMultiSelect, .stNumberInput, .stDataFrame,
  [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] div,
  [data-testid="stAppViewContainer"] span, [data-testid="stAppViewContainer"] label,
  [data-testid="stAppViewContainer"] button, [data-testid="stAppViewContainer"] input,
  [data-testid="stAppViewContainer"] textarea,
  h1, h2, h3, h4, h5 { font-family:'Source Serif 4', Georgia, serif !important; }
  .stApp { background: var(--bg); }
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"] { display:none !important; }
  header[data-testid="stHeader"] { background: transparent; }
  .block-container { padding-top:.5rem; padding-bottom:1rem; max-width:1240px; }
  h1, h2, h3 { font-weight:600 !important; letter-spacing:-.01em; }
  h2 { font-size:2.7rem !important; line-height:.95 !important; }
  h3 { font-size:1.5rem !important; }
  .kicker { font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
  .muted { color:var(--muted); font-size:.9rem; }
  [data-testid="stAppViewContainer"] a { color:var(--accent) !important; }
  .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    border-radius:2px !important; font-weight:600 !important; font-size:.95rem !important;
    letter-spacing:0; text-transform:none; padding:.35rem .9rem; white-space:nowrap; box-shadow:none; }
  .stButton > button[kind="secondary"], .stDownloadButton > button {
    border:1px solid var(--accent) !important; color:var(--accent-press) !important; background:transparent !important; }
  .stButton > button[kind="secondary"]:hover { background:var(--accent-tint) !important; }
  .stButton > button[kind="primary"]:hover { background:var(--accent-h) !important; }
  button:focus-visible { outline:2px solid var(--accent) !important; outline-offset:2px; }
  .lt-topbar { display:flex; justify-content:space-between; align-items:center; padding:.5rem .1rem;
    border-bottom:1px solid var(--divider); font-size:.72rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--muted); }
  .lt-topbar a { color:var(--accent) !important; text-decoration:none; }
  .lt-header img { height:38px; }
  .lt-user { text-align:right; font-size:.84rem; color:var(--muted); line-height:1.35; }
  .lt-user b { color:var(--text); font-size:1.02rem; }
  .st-key-lt_nav { border-bottom:1px solid var(--divider); margin-bottom:.6rem; }
  .st-key-lt_nav .stButton > button { border:none !important; background:transparent !important;
    color:var(--text) !important; font-size:1.05rem !important; font-weight:400 !important;
    padding:.1rem .05rem !important; border-radius:0 !important; }
  .st-key-lt_nav .stButton > button:hover { color:var(--accent-press) !important; }
  div[class*="st-key-chip_"] .stButton > button { background:var(--accent-tint) !important;
    color:var(--accent-press) !important; border:none !important; font-size:.85rem !important;
    font-weight:400 !important; padding:.05rem .6rem !important; border-radius:2px !important; }
  div[data-testid="stSegmentedControl"] button { font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; font-size:.78rem; }
  div[class*="st-key-card_"] > div { border:none !important; border-radius:2px !important;
    background:transparent; }
  div[data-testid="stImage"] img { border-radius:2px; }
  div[class*="st-key-card_"] div[data-testid="stImage"] img { object-fit:cover; aspect-ratio:1/1; background:#e9e7e6; }
  /* Rail de filtros pegajoso: la COLUMNA es el sticky (flex item dentro de la
     fila, que es alta como el grid → tiene recorrido para acompañar el scroll) */
  div[data-testid="stColumn"]:has(div[class*="st-key-cat_rail"]) {
    position: sticky; top: .75rem; align-self: flex-start;
    max-height: calc(100vh - 1.5rem); overflow-y: auto; overflow-x: hidden; }
  .card-title { font-weight:600; font-size:1.12rem; margin-top:.45rem; line-height:1.15; color:var(--text);
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .card-sub { color:var(--faint); font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; margin-top:.1rem; }
  .card-price { font-weight:600; font-size:1.15rem; margin-top:.2rem; }
  .card-price-old { color:var(--faint); text-decoration:line-through; font-weight:400;
    font-size:.92rem; margin-right:.4rem; }
  .card-price-off { color:#d6006c; }
  .badge-desc { display:inline-block; background:#d6006c; color:#fff; font-weight:700;
    font-size:.7rem; letter-spacing:.04em; padding:.08rem .4rem; border-radius:2px;
    margin-left:.4rem; vertical-align:.08rem; }
  .ficha-precio { font-size:1.5rem; font-weight:700; margin:.2rem 0 .3rem; }
  .ficha-precio .card-price-old { font-size:1.15rem; }
  .cart-price-old { color:var(--faint); text-decoration:line-through; font-size:.8rem; display:block; }
  .cart-price-off { color:#d6006c; font-weight:600; }
  .tag { display:inline-block; padding:.12rem .55rem; border-radius:2px; font-size:.72rem; font-weight:600;
    letter-spacing:.08em; text-transform:uppercase; }
  .tag-conf { background:var(--accent-tint); color:var(--accent-press); }
  .tag-proc { background:var(--n200); color:#444141; }
  .tag-canc { background:var(--alert-tint); color:var(--alert-text); }
  .aviso-stock { color:var(--alert-text); font-size:.86rem; }
  .aviso-bloque { background:#fff1f4; border-left:3px solid #d6006c; color:#aa0b56;
                  padding:.7rem .9rem; font-size:.9rem; margin:.4rem 0; }
  .nota-acento { background:#e9f8ff; border-left:3px solid #0088b0; color:#201e1d;
                 padding:.7rem .9rem; font-size:.9rem; margin:.4rem 0; }
  /* Galería: la miniatura ES un botón con la foto de fondo (por producto se
     inyecta un <style> con el background de cada uno) — el área clickeable es
     el 100% de la miniatura, sin capas superpuestas frágiles. */
  div[class*="st-key-galb_"] button { width:100%; height:76px; min-height:76px;
    padding:0; border-radius:2px; cursor:pointer; background-color:#fff; }
  div[class*="st-key-galb_"] button p { visibility:hidden; }
  .stApp div[class*="st-key-cli_desactivar"] button,
  .stApp div[class*="st-key-cli_desactivar"] button p { color:#aa0b56 !important; border-color:#d6006c !important; }
  .total-box { background:transparent; border-top:2px solid var(--text); padding:.9rem .1rem 0; }
  .lt-footer { border-top:2px solid var(--text); margin-top:2.5rem; padding:1.3rem .1rem 0;
    display:grid; grid-template-columns:repeat(3, 1fr); gap:1rem; font-size:.9rem; color:var(--text); }
  .lt-footer h5 { font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
    margin:0 0 .5rem; font-weight:600; }
  .lt-footer a { color:var(--accent) !important; text-decoration:none; }
  .lt-copy { grid-column:1 / -1; color:var(--faint); font-size:.78rem; padding:.6rem 0 .2rem; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_money(n) -> str:
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return f"$ {float(n):,.0f}".replace(",", ".")


def precio_html(precio, precio_lista=None, pct_desc=0, *, clase_final="card-price", inline=False) -> str:
    """HTML del precio. Si pct_desc>0: precio de lista tachado + precio final en
    magenta + badge «−N%». Si no, solo el precio. `inline` usa <span> (para la ficha)."""
    pct = float(pct_desc or 0)
    final = fmt_money(precio)
    if pct <= 0 or precio_lista in (None, "") or (isinstance(precio_lista, float) and math.isnan(precio_lista)):
        if inline:
            return final
        return f"<div class='{clase_final}'>{final}</div>"
    lista = fmt_money(precio_lista)
    badge = f"<span class='badge-desc'>−{pct:g}%</span>"
    cuerpo = (f"<span class='card-price-old'>{lista}</span>"
              f"<span class='card-price-off'>{final}</span>{badge}")
    return cuerpo if inline else f"<div class='{clase_final}'>{cuerpo}</div>"


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
    st.markdown("<div class='lt-topbar'><span>Venta exclusiva mayorista</span>"
                "<span>WhatsApp <a href='https://wa.me/" + WHATSAPP.replace(" ", "").replace("+", "")
                + "' target='_blank'>" + WHATSAPP + "</a></span></div>", unsafe_allow_html=True)


def _sync_marca_from_header() -> None:
    v = st.session_state.get("hdr_marca")
    st.session_state.f_marca = [v] if v in MARCAS else []
    st.session_state.page = "catalogo"   # elegir marca desde el header siempre lleva al catálogo


def header(con_marcas: bool = True) -> None:
    """Logo + selector de marca (TODO/CHIMOLA/LIMA) + datos del cliente."""
    user = st.session_state.get("user")
    cli = cliente_efectivo() if user else None
    c1, c2, c3 = st.columns([1, 2.2, 1.9], vertical_alignment="center")
    with c1:
        st.markdown("<div class='lt-header'><img src='" + static_b64("logo_lautin.png")
                    + "' alt='Lautin'></div>", unsafe_allow_html=True)
    with c2:
        if con_marcas and user:
            actual = st.session_state.get("f_marca", [])
            st.session_state.hdr_marca = actual[0] if len(actual) == 1 and actual[0] in MARCAS else "Todo"
            st.segmented_control("Marca", ["Todo"] + MARCAS, key="hdr_marca", label_visibility="collapsed",
                                 on_change=_sync_marca_from_header)
    with c3:
        if user:
            if puede_pedir():
                sub = (f"Cliente {cli['cliente_cod']} · lista {cli['lista_precios']} · "
                       f"descuento cabecera {cli['descuento']:g}%")
            else:
                sub = "Rol admin · sin cliente"
            st.markdown(f"<div class='lt-user'><b>{cli['nombre_display']}</b><br>{sub}</div>",
                        unsafe_allow_html=True)


def nav() -> None:
    """Fila de navegación horizontal (reemplaza al sidebar)."""
    user = st.session_state.user
    page = st.session_state.get("page", "catalogo")
    activo = "catalogo" if page == "producto" else page
    n_items = sum(int(i["cantidad"]) for i in st.session_state.get("cart", []))
    items = [("catalogo", "Catálogo")]
    if puede_pedir():
        items.append(("compra_rapida", "Compra rápida"))
        try:   # Reposición: solo franquicias (clientes titulares de un PV)
            if reposicion.pv_de_cliente(user.get("cliente_cod") or 0):
                items.append(("reposicion", "Reposición"))
        except Exception:  # noqa: BLE001 — sin BQ no rompemos la nav
            pass
    items.append(("carrito", f"Carrito · {n_items} u."))
    items.append(("pedidos", "Mis pedidos"))
    items.append(("cuenta", "Mis datos"))
    if user.get("rol") == "admin":
        try:
            sp = pedidos.contar_por_estado().get("confirmado", 0)
        except Exception:  # noqa: BLE001
            sp = 0
        items.append(("admin", "Administración" + (f" · {sp} sin procesar" if sp else "")))
    with st.container(key="lt_nav"):
        anchos = [max(len(lbl) * .075, .8) for _, lbl in items] + [2.4, .5]
        cols = st.columns(anchos, vertical_alignment="center")
        for (key, label), col in zip(items, cols):
            if col.button(label, key=f"nav_{key}"):
                if key == "admin":
                    # Entrar a Administración aterriza SIEMPRE en Inicio (fase 6.1)
                    st.session_state.adm_nav_forzar = "inicio"
                    st.session_state.adm_prod = None
                    st.session_state.adm_cliente = None
                ir(key)
        hace = catalog.catalogo_actualizado_hace()
        info = f"Catálogo actualizado hace {hace // 60} min" if hace >= 0 else ""
        cols[-2].markdown(f"<div class='muted' style='text-align:right'>{info}</div>", unsafe_allow_html=True)
        if cols[-1].button("Salir", key="nav_salir"):
            logout()
            st.rerun()
    st.markdown(f"<style>.st-key-lt_nav .st-key-nav_{activo} button "
                "{box-shadow: inset 0 -2px 0 #0088b0 !important; color:#006786 !important;}</style>",
                unsafe_allow_html=True)


def footer() -> None:
    env = " · Ambiente " + config.APP_ENV.upper() if config.APP_ENV != "prod" else ""
    st.markdown(f"""<div class='lt-footer'>
      <div><h5>Nuestras marcas</h5>Chimola<br>Lima</div>
      <div><h5>Contacto</h5>{WHATSAPP}<br><a href='https://instagram.com/chimolaoficial' target='_blank'>@chimolaoficial</a>
           · <a href='https://instagram.com/lima.oficial' target='_blank'>@lima.oficial</a></div>
      <div><h5>Información</h5>Los pedidos se confirman por email con el Excel adjunto.
           Sin pago online: Lautin coordina entrega y facturación.</div>
      <div class='lt-copy'>© 2026 Lautin Accesorios. Todos los derechos reservados.{env}</div>
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


def es_franquicia(cliente_cod) -> bool:
    """Cliente titular de un punto de venta (dim_pv) → funciones de franquicia."""
    try:
        return bool(cliente_cod) and reposicion.pv_de_cliente(int(cliente_cod)) is not None
    except Exception:  # noqa: BLE001
        return False


def boton_odoo(p: dict, key: str, col=None) -> None:
    """Descarga del pedido en formato Odoo (dos hojas). Solo franquicias."""
    if p.get("estado") == "cancelado" or not es_franquicia(p.get("cliente_cod")):
        return
    ov = overrides.get_clientes_overrides().get(int(p["cliente_cod"]), {})
    cliente_odoo = ov.get("odoo_cliente") or p.get("cliente_nombre") or ""
    (col or st).download_button("Exportar formato Odoo", key=key,
                                data=odoo_export.generar_excel_odoo(p, cliente_odoo),
                                file_name=odoo_export.nombre_archivo(p),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=col is not None,
                                help="Dos hojas: 'Sin talle' (talle único) e 'Indu' (con talle), "
                                     "listas para la importación masiva de Odoo.")


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
    st.markdown("<p class='kicker' style='text-align:center;margin:.5rem 0'>Logueate y descubrí todo nuestro catálogo</p>", unsafe_allow_html=True)
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
# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def _quitar_filtro(campo, valor=None) -> None:
    """Callback de chips: corre ANTES del script, puede mutar keys de widgets."""
    if campo == "busq":
        st.session_state.f_busqueda = ""
    elif campo == "fotos":
        st.session_state.f_fotos = False
    elif campo == "claros":
        st.session_state.f_claros = False
    elif campo == "desc":
        st.session_state.f_desc = False
    elif campo == "todos":
        for f in catalog.FILTROS:
            st.session_state[f"f_{f}"] = []
        st.session_state.f_busqueda = ""
        st.session_state.f_fotos = False
        st.session_state.f_claros = False
        st.session_state.f_desc = False
    else:
        st.session_state[f"f_{campo}"] = [v for v in st.session_state.get(f"f_{campo}", []) if v != valor]


def _elegir_foto(idx_key: str, j: int) -> None:
    st.session_state[idx_key] = j


def _abrir_card(cod: str) -> None:
    st.session_state.card_abierta = None if st.session_state.get("card_abierta") == cod else cod


def es_admin() -> bool:
    return (st.session_state.get("user") or {}).get("rol") == "admin"


def toast_pendiente(msg: str) -> None:
    """Encola un toast que se muestra al inicio del próximo run (sobrevive a
    st.rerun; el cliente lo ve unos segundos y desaparece)."""
    st.session_state.setdefault("_toasts", []).append(msg)


def matriz_variantes(prod: dict, key: str) -> list:
    """Matriz color x talle (handoff cambio 3): cantidades editables.
    El stock por variante SOLO lo ve el admin — al cliente nunca se le
    muestra; si pide de más se acota con un toast. Devuelve items de carrito."""
    vs = prod["variantes"]
    colores = list(dict.fromkeys(v["color"] for v in vs))
    talles = sorted({v["talle"] for v in vs}, key=catalog.talle_key)
    cols_t = [f"Talle {t}" for t in talles]
    by_ct = {(v["color"], v["talle"]): v for v in vs}
    ub = int(prod.get("ub") or 0)

    if es_admin():
        stock_df = pd.DataFrame([[by_ct.get((c, t), {}).get("stock") for t in talles] for c in colores],
                                index=colores, columns=cols_t)
        st.markdown("<div class='kicker'>Stock disponible (solo lo ves como admin)</div>",
                    unsafe_allow_html=True)
        st.dataframe(stock_df, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(c, format="%d") for c in cols_t})
    st.markdown("<div class='kicker'>Cantidades a pedir"
                + (f" — múltiplos de {ub}" if ub > 1 else "") + "</div>", unsafe_allow_html=True)
    qty0 = pd.DataFrame([[0 if (c, t) in by_ct else None for t in talles] for c in colores],
                        index=colores, columns=cols_t)
    ed = st.data_editor(qty0, key=key, use_container_width=True,
                        column_config={c: st.column_config.NumberColumn(c, min_value=0, step=ub or 1, format="%d")
                                       for c in cols_t})
    items, recortes = [], []
    for c in colores:
        for t in talles:
            v = by_ct.get((c, t))
            q = ed.loc[c, f"Talle {t}"]
            if v is None or pd.isna(q) or int(q) <= 0 or pd.isna(v["precio"]):
                continue
            pedido = int(q)
            q = min(pedido, int(v["stock"]))
            if ub > 1:
                q = (q // ub) * ub
            if q < pedido:
                recortes.append((c, t, pedido, q))
            if q > 0:
                items.append(cr.item_desde_variante(v, q))
    if recortes:
        # Aviso PERSISTENTE mientras el valor tipeado exceda lo disponible
        # (pedido del usuario 2026-08-25): dice qué se va a cargar, sin
        # mencionar el stock. El toast avisa además al momento del cambio.
        for c, t, pedido, q in recortes:
            st.markdown(f"<div class='aviso-stock'>{c} · Talle {t}: pediste <b>{pedido}</b> y supera "
                        f"la cantidad disponible — se van a cargar <b>{q}</b>.</div>",
                        unsafe_allow_html=True)
        firma = (key, tuple(r[:2] for r in recortes))
        if st.session_state.get("mx_recorte_firma") != firma:
            st.session_state.mx_recorte_firma = firma
            st.toast("Estás superando la cantidad disponible en "
                     + ", ".join(f"{c} Talle {t}" for c, t, _, _ in recortes)
                     + " — lo ajustamos al máximo posible.")
    return items


def _totales_seleccion(items: list) -> None:
    cli = cliente_efectivo()
    unidades = sum(i["cantidad"] for i in items)
    monto = sum(i["cantidad"] * i["precio_unit"] for i in items)
    ahorro = sum(i["cantidad"] * (float(i.get("precio_lista") or i["precio_unit"]) - i["precio_unit"])
                 for i in items)
    if unidades:
        # OJO: envuelto en <div> — con DOS "$" en markdown plano, Streamlit
        # los interpreta como fórmula matemática (LaTeX) y rompe el HTML.
        ahorro_html = (f" · <span style='color:#d6006c'>ahorrás {fmt_money(ahorro)} por ofertas</span>"
                       if ahorro > 0 else "")
        st.markdown(f"<div>Seleccionadas <b>{unidades} u.</b> · {fmt_money(monto)} subtotal · "
                    f"<span style='color:#006786'>{fmt_money(catalog.aplicar_descuento(monto, cli.get('descuento', 0)))} "
                    f"con tu {cli.get('descuento', 0):g}%</span>{ahorro_html}</div>", unsafe_allow_html=True)


def page_catalogo() -> None:
    df = df_catalogo()
    cli = cliente_efectivo()
    banner_texto = overrides.get_config().get("banner_texto")
    if banner_texto:
        st.info(banner_texto)
    t1, t2 = st.columns([1, 1.7], vertical_alignment="bottom")
    t1.markdown("## Catálogo")
    t2.markdown(f"<p class='muted'>Precios de lista {cli['lista_precios']}, sin descuento cabecera. "
                "Solo variantes con stock neto en Ezeiza.</p>", unsafe_allow_html=True)

    # Fase 8: rail izquierdo de filtros (Categoría/Tipo/Marca/Temporada/Color/Talle)
    LABELS_F = {"categoria": "Categoría", "rubro": "Tipo de producto", "marca": "Marca",
                "temporada": "Temporada", "color": "Color", "talle": "Talle"}
    sel_prev = {f: st.session_state.get(f"f_{f}", []) for f in catalog.FILTROS}
    opciones = catalog.opciones_filtros(df, sel_prev)
    rail, main = st.columns([1, 3.4], gap="large")
    sel = {}
    with rail, st.container(key="cat_rail"):
        busqueda = st.text_input("Buscar", key="f_busqueda", placeholder="código, nombre, EAN, color")
        for f in catalog.FILTROS:
            if not opciones[f] and not sel_prev[f]:
                sel[f] = []
                continue
            # saneo: una selección que quedó sin match se despega sola
            st.session_state[f"f_{f}"] = [v for v in st.session_state.get(f"f_{f}", [])
                                          if v in opciones[f]]
            st.markdown(f"<div class='kicker' style='margin:.7rem 0 .1rem'>{LABELS_F[f]}</div>",
                        unsafe_allow_html=True)
            sel[f] = st.multiselect(LABELS_F[f], opciones[f], key=f"f_{f}", placeholder="Todos",
                                    label_visibility="collapsed")
        st.markdown("")
        st.checkbox("Solo con foto", value=True, key="f_fotos")
        st.checkbox("Solo con descuento", value=False, key="f_desc",
                    help="Muestra solo los productos con oferta (descuento por artículo).")
        st.toggle("Encender el sitio", key="f_claros",
                  help="Muestra cada producto con la foto de su color más claro "
                       "(blanco, beige, nude, rosa, celeste...). Apagado: foto principal.")
    solo_fotos = st.session_state.get("f_fotos", True)
    solo_desc = bool(st.session_state.get("f_desc", False))
    claros = bool(st.session_state.get("f_claros", False))

    variantes = catalog.filtrar_variantes(df, sel, busqueda)
    if solo_desc and "descvta" in variantes.columns:
        variantes = variantes[variantes["descvta"] > 0]
    prods = catalog.productos(variantes)
    if solo_fotos and not prods.empty:
        prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]
    if not prods.empty:
        # Orden: destacados → (SOLO sin filtros ni búsqueda) productos con foto de
        # la variante del modo (encendido = color claro, apagado = negro) → resto
        # por código. Con filtros activos el switch solo cambia las fotos de lo
        # que ya se ve, sin reordenar.
        modo = "claro" if claros else "negro"
        hay_filtros = bool(busqueda) or any(sel.get(f) for f in catalog.FILTROS)
        dest = (variantes.groupby("producto_cod")["destacado"].first()
                if "destacado" in variantes.columns else None)
        prods = prods.assign(
            _d=prods["producto_cod"].map(dest).fillna(False) if dest is not None else False,
            _m=False if hay_filtros else [fotos.foto_card_filename(c, cols, modo)[1]
                                          for c, cols in zip(prods["producto_cod"], prods["colores"])])
        prods = prods.sort_values(["_d", "_m", "producto_cod"],
                                  ascending=[False, False, True]).drop(columns=["_d", "_m"])

    with main:
        _grid_catalogo(df, prods, variantes, busqueda, sel, solo_fotos, claros, solo_desc)


def _grid_catalogo(df, prods, variantes, busqueda: str, sel: dict, solo_fotos: bool,
                   claros: bool = False, solo_desc: bool = False) -> None:
    # Chips de filtros activos (handoff cambio 2)
    chips = []
    if busqueda:
        chips.append(("busq", None, f"“{busqueda}”"))
    for f in catalog.FILTROS:
        for v in sel.get(f, []):
            chips.append((f, v, str(v)))
    if solo_fotos:
        chips.append(("fotos", None, "Solo con foto"))
    if solo_desc:
        chips.append(("desc", None, "Solo con descuento"))
    if claros:
        chips.append(("claros", None, "Sitio encendido"))
    anchos = [max(len(c[2]) * 0.058 + 0.3, 0.6) for c in chips] + ([0.62] if chips else []) + [2.2]
    ccols = st.columns(anchos, vertical_alignment="center")
    for (campo, valor, label), col in zip(chips, ccols):
        col.button(f"{label} ×", key=f"chip_{campo}_{valor}", on_click=_quitar_filtro, args=(campo, valor))
    if chips:
        ccols[len(chips)].button("Limpiar", key="chip_todos_x", on_click=_quitar_filtro, args=("todos", None))
    ccols[-1].markdown(f"<div class='muted' style='text-align:right'>{len(prods)} productos · "
                       f"{len(variantes)} variantes con stock</div>", unsafe_allow_html=True)

    # Fase 8: sin paginado — el grid acumula de a tandas («Mostrar más»)
    firma = (busqueda, tuple(tuple(v) for v in sel.values()), solo_fotos, solo_desc)
    if st.session_state.get("cat_firma") != firma:
        st.session_state.cat_firma = firma
        st.session_state.cat_n = config.ITEMS_POR_PAGINA
        st.session_state.card_abierta = None
    if len(prods) == 0:
        st.markdown("<p class='muted'>No hay productos con stock para esos filtros.</p>", unsafe_allow_html=True)
        return

    n = st.session_state.get("cat_n", config.ITEMS_POR_PAGINA)
    sub = prods.iloc[:n]
    abierta = st.session_state.get("card_abierta")
    for k in range(0, len(sub), 3):
        fila = sub.iloc[k:k + 3]
        cols = st.columns(3)
        for i, (_, p) in enumerate(fila.iterrows()):
            with cols[i]:
                with st.container(key=f"card_{p['producto_cod']}"):
                    # La imagen es un link a la ficha del producto (fase 8, T3)
                    src = fotos.foto_card(p["producto_cod"], p["colores"], "claro" if claros else "negro")
                    st.markdown(f"<a href='?p={p['producto_cod']}' target='_self'>"
                                f"<img src='{src}' "
                                "style='width:100%; display:block; border-radius:2px'></a>",
                                unsafe_allow_html=True)
                    st.markdown(
                        f"<div class='card-title' title='{p['producto_nombre']}'>{p['producto_nombre']}</div>"
                        f"<div class='card-sub'>{p['producto_cod']} · {p['marca'] or ''} · {p['rubro'] or ''}</div>"
                        f"{precio_html(p['precio'], p.get('precio_lista'), p.get('pct_desc', 0))}"
                        f"<div class='muted'>{(str(int(p['stock'])) + ' u. · ') if es_admin() else ''}"
                        f"{len(p['colores'])} color(es)</div>",
                        unsafe_allow_html=True)
                    if puede_pedir():
                        st.button("Cargar cantidades", key=f"abrir_{p['producto_cod']}",
                                  on_click=_abrir_card, args=(p["producto_cod"],), use_container_width=True)
                    elif st.button("Ver ficha", key=f"abrir_{p['producto_cod']}", use_container_width=True):
                        ir("producto", producto_sel=p["producto_cod"])
        if abierta in set(fila["producto_cod"]):
            prod = catalog.get_producto(df, abierta)
            if prod and prod["precio"] is not None:
                with st.container(border=True, key=f"panel_{abierta}"):
                    # OJO nesting: el grid ya vive dentro de la columna `main`
                    # (rail de filtros, fase 8) → acá solo se permite UN nivel
                    # más de columnas. Los botones van al nivel del container,
                    # nunca adentro de pdet (StreamlitAPIException).
                    pi, pdet = st.columns([1, 3.1], gap="medium")
                    with pi:
                        st.image(fotos.foto_principal(abierta), use_container_width=True)
                    with pdet:
                        st.markdown(f"### {prod['producto_nombre']}")
                        st.markdown(f"<div class='card-sub'>{abierta} · {prod['marca'] or ''} · "
                                    f"{prod['temporada'] or ''} · {prod['rubro'] or ''}</div>",
                                    unsafe_allow_html=True)
                        if float(prod.get("pct_desc") or 0) > 0:
                            st.markdown(precio_html(prod["precio"], prod.get("precio_lista"),
                                                    prod["pct_desc"]), unsafe_allow_html=True)
                        ver = st.session_state.get("mx_ver", 0)
                        items = matriz_variantes(prod, key=f"mx_{abierta}_{ver}")
                        _totales_seleccion(items)
                    b1, b2, b3 = st.columns([1.3, 1.3, 2.2])
                    if b1.button("Agregar al carrito", type="primary", key=f"padd_{abierta}",
                                 disabled=not items, use_container_width=True):
                        total = _agregar_items(items)
                        st.session_state.mx_ver = ver + 1
                        st.session_state.card_abierta = None
                        toast_pendiente(f"Agregaste {total} unidades al carrito.")
                        st.rerun()
                    if b2.button("Ver ficha completa", key=f"pfull_{abierta}", use_container_width=True):
                        ir("producto", producto_sel=abierta)
                    if b3.button("Cerrar", key=f"pcls_{abierta}"):
                        st.session_state.card_abierta = None
                        st.rerun()

    if len(prods) > len(sub):
        m1, m2, m3 = st.columns([1, 2, 1])
        if m2.button(f"Cargando más… — viste {len(sub)} de {len(prods)} productos",
                     key="cat_mas", use_container_width=True):
            st.session_state.cat_n = n + config.ITEMS_POR_PAGINA
            st.rerun()
        # Scroll infinito: cuando el botón entra en pantalla (600px antes), se
        # auto-clickea. Queda visible como indicador y fallback manual. El
        # observer se re-arma en cada rerun (este iframe se re-renderiza).
        components.html("""<script>
          const doc = window.parent.document;
          const btn = doc.querySelector('.st-key-cat_mas button');
          if (btn) {
            const obs = new IntersectionObserver((entradas) => {
              entradas.forEach(e => {
                if (e.isIntersecting) { obs.disconnect(); btn.click(); }
              });
            }, { root: null, rootMargin: '600px' });
            obs.observe(btn);
          }
        </script>""", height=0)
    else:
        st.markdown(f"<p class='muted' style='text-align:center'>Esos son los {len(prods)} productos "
                    "del filtro.</p>", unsafe_allow_html=True)


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
    iva_tag = " + IVA" if float(overrides.get_config().get("iva_pct") or 0) > 0 else ""

    col_img, col_info = st.columns([1, 1.1], gap="large")
    with col_img:
        galeria = fotos.fotos_producto(cod, prod["colores"])
        if galeria:
            color_foto = st.selectbox("Ver fotos del color", ["Todas"] + prod["colores"], key="foto_color")
            visibles = galeria if color_foto == "Todas" else fotos.fotos_por_color(galeria, color_foto)
            # Click en una miniatura → esa foto al visor principal (sin numeritos)
            idx_key = f"foto_idx_{cod}_{color_foto}"
            idx = min(int(st.session_state.get(idx_key, 0) or 0), len(visibles) - 1)
            st.image(visibles[idx]["url"], use_container_width=True)
            if len(visibles) > 1:
                thumbs = st.columns(min(len(visibles), 8))
                css = []
                for j, f in enumerate(visibles[:16]):
                    with thumbs[j % 8]:
                        bkey = f"galb_{cod}_{j}"
                        st.button(" ", key=bkey, on_click=_elegir_foto, args=(idx_key, j),
                                  use_container_width=True)
                        borde = "2px solid #0088b0" if j == idx else "1px solid rgba(32,30,29,.15)"
                        # OJO: el CSS global pone `background:transparent !important` y
                        # `border ... !important` en los botones secundarios → estas
                        # reglas necesitan MÁS especificidad y longhands !important.
                        css.append(
                            f'.st-key-{bkey} .stButton > button[kind="secondary"] {{ '
                            f'background-image:url("{f["url"]}") !important; '
                            "background-size:contain !important; background-position:center !important; "
                            "background-repeat:no-repeat !important; background-color:#fff !important; "
                            f"border:{borde} !important; }}")
                # st.html (no st.markdown): el parser de markdown rompería los
                # `&` de las signed URLs dentro del url(...) del CSS.
                st.html("<style>" + "".join(css) + "</style>")
        else:
            st.image(fotos.PLACEHOLDER, use_container_width=True)
            st.caption("Este producto todavía no tiene fotos cargadas.")

    with col_info:
        st.markdown(f"## {prod['producto_nombre']}")
        st.markdown(f"<div class='card-sub'>{prod['producto_cod']} · {prod['marca'] or ''} · "
                    f"{prod['temporada'] or ''} · {prod['rubro'] or ''}"
                    f"{(' · ' + prod['categoria']) if prod.get('categoria') else ''}</div>", unsafe_allow_html=True)
        if prod["precio"] is None:
            st.error(f"Este producto no tiene precio cargado en la lista {cli['lista_precios']}. "
                     "No se puede pedir — consultá a Lautin.")
        else:
            pdesc = float(prod.get("pct_desc") or 0)
            precio_ficha = precio_html(prod["precio"], prod.get("precio_lista"), pdesc, inline=True)
            etiqueta = "precio con oferta" if pdesc > 0 else "precio lista"
            # Bloque <div> (NO markdown `###`): con dos "$" el markdown los toma
            # como fórmula LaTeX y rompe el HTML de los <span> (gotcha del proyecto).
            st.markdown(f"<div class='ficha-precio'>{precio_ficha} "
                        f"<span class='muted' style='font-size:1rem;font-weight:400'>{etiqueta} "
                        f"{cli['lista_precios']}{iva_tag}</span></div>", unsafe_allow_html=True)
            if cli.get("descuento"):
                st.markdown(f"<p class='muted'>Con tu descuento cabecera ({cli['descuento']:g}%): "
                            f"<b style='color:#006786'>{fmt_money(catalog.aplicar_descuento(prod['precio'], cli['descuento']))}</b> "
                            "por unidad</p>", unsafe_allow_html=True)
        if prod.get("descripcion"):
            st.markdown(f"<p class='muted'>{prod['descripcion']}</p>", unsafe_allow_html=True)
        if int(prod.get("ub") or 0) > 1:
            st.markdown(f"<p class='muted'>Se vende en múltiplos de <b>{prod['ub']} unidades</b> por variante.</p>",
                        unsafe_allow_html=True)

    st.markdown("### Variantes y cantidades")
    if prod["precio"] is None or not puede_pedir():
        st.markdown("<p class='muted'>Tu usuario no puede pedir con esta cuenta.</p>", unsafe_allow_html=True)
        return
    ver = st.session_state.get("mx_ver", 0)
    items = matriz_variantes(prod, key=f"mxp_{cod}_{ver}")
    _totales_seleccion(items)
    if st.button("Agregar al carrito", type="primary", disabled=not items):
        total = _agregar_items(items)
        st.session_state.mx_ver = ver + 1
        st.toast(f"{total} unidades agregadas al carrito")
        st.rerun()


# ---------------------------------------------------------------------------
# Carrito
# ---------------------------------------------------------------------------
def _quitar_item(sku: str, nombre: str = "") -> None:
    items = [i for i in st.session_state.cart if i["sku"] != sku]
    st.session_state.cart = items
    pedidos.guardar_carrito(st.session_state.user["email"], items)
    st.session_state.cart_ver = st.session_state.get("cart_ver", 0) + 1
    toast_pendiente(f"Quitaste {nombre or sku} del carrito.")


def page_carrito() -> None:
    st.markdown("## Carrito")
    cli = cliente_efectivo()
    items = st.session_state.get("cart", [])

    if st.session_state.get("pedido_ok"):
        p, xlsx = st.session_state.pedido_ok
        st.success(f"Pedido N° {p['numero']} confirmado · {p['unidades']} unidades · total {fmt_money(p['total'])}")
        em = p.get("email") or {}
        if em.get("enviado"):
            st.markdown(f"<p class='muted'>Te enviamos el Excel a: {', '.join(em['destinatarios'])}</p>",
                        unsafe_allow_html=True)
        else:
            st.warning(f"El pedido quedó registrado pero el email no salió ({em.get('error')}). "
                       "Descargá el Excel acá y avisá a Lautin.")
        st.download_button("Descargar Excel del pedido", data=xlsx, file_name=p["xlsx_filename"],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        boton_odoo(p, key="odoo_conf")
        if st.button("Hacer otro pedido"):
            st.session_state.pop("pedido_ok")
            ir("catalogo")
        return

    if not items:
        st.markdown("<p class='muted'>El carrito está vacío.</p>", unsafe_allow_html=True)
        if st.button("Ir al catálogo"):
            ir("catalogo")
        return

    avisos = st.session_state.get("stock_avisos", {})
    if avisos:
        st.error(f"Cambió la disponibilidad de {len(avisos)} producto(s): ajustamos el carrito. "
                 "Revisá las filas marcadas y volvé a confirmar.")
        en_carrito = {i["sku"] for i in items}
        for sku, msg in avisos.items():
            if sku not in en_carrito:
                st.markdown(f"<div class='aviso-stock'>{sku}: {msg}</div>", unsafe_allow_html=True)

    ver = st.session_state.get("cart_ver", 0)
    left, right = st.columns([2.55, 1.25], gap="large")
    with left:
        h = st.columns([0.5, 2.3, 0.95, 0.85, 0.85, 0.3])
        for col, txt in zip(h, ["", "Producto", "Cantidad", "Precio", "Subtotal", ""]):
            col.markdown(f"<div class='kicker'>{txt}</div>", unsafe_allow_html=True)
        nuevos, cambio, recortes = [], False, {}
        for it in items:
            c = st.columns([0.5, 2.3, 0.95, 0.85, 0.85, 0.3], vertical_alignment="center")
            with c[0]:
                if fotos.tiene_fotos(it["producto_cod"]):
                    st.image(fotos.miniatura(it["producto_cod"], it.get("color")), width=52)
            c[1].markdown(f"<b>{it['producto_nombre']}</b><br><span class='card-sub'>"
                          f"{it['producto_cod']} · {it['color']} · Talle {it['talle']}</span>", unsafe_allow_html=True)
            # La cantidad puede superar el stock actual (se sumó de a tandas o
            # el stock bajó): se acota SIN mostrar nunca el stock al cliente
            # (sin max_value, que delata el número) — aviso efímero por toast.
            tope = int(it.get("stock") or 99999)
            val = min(int(it["cantidad"]), tope)
            if val < int(it["cantidad"]):
                recortes[it["sku"]] = (f"{it['producto_nombre']} ({it['color']}): pediste "
                                       f"{int(it['cantidad'])} u. y estás superando la cantidad "
                                       "disponible — lo ajustamos al máximo posible.")
            q = c[2].number_input("Cantidad", min_value=0, step=1,
                                  value=val, key=f"cq_{ver}_{it['sku']}",
                                  label_visibility="collapsed")
            if int(q) > tope:   # tipeó de más recién ahora
                recortes[it["sku"]] = (f"{it['producto_nombre']} ({it['color']}): estás superando la "
                                       "cantidad disponible — lo ajustamos al máximo posible.")
                q = tope
            pd_it = float(it.get("pct_desc") or 0)
            lista_it = float(it.get("precio_lista") or it["precio_unit"])
            if pd_it > 0 and lista_it > it["precio_unit"]:
                c[3].markdown(f"<div><span class='cart-price-old'>{fmt_money(lista_it)}</span>"
                              f"<span class='cart-price-off'>{fmt_money(it['precio_unit'])}</span> "
                              f"<span class='badge-desc'>−{pd_it:g}%</span></div>", unsafe_allow_html=True)
            else:
                c[3].markdown(fmt_money(it["precio_unit"]))
            c[4].markdown(f"<b>{fmt_money(int(q) * it['precio_unit'])}</b>", unsafe_allow_html=True)
            c[5].button("×", key=f"del_{it['sku']}", on_click=_quitar_item,
                        args=(it["sku"], f"{it['producto_nombre']} ({it['color']})"))
            if it["sku"] in avisos:
                st.markdown(f"<div class='aviso-stock'>{avisos[it['sku']]}</div>", unsafe_allow_html=True)
            st.markdown("<div style='border-bottom:1px solid rgba(32,30,29,.16); margin:.1rem 0 .55rem'></div>",
                        unsafe_allow_html=True)
            if int(q) != int(it["cantidad"]):
                cambio = True
            if int(q) > 0:
                nuevos.append({**it, "cantidad": int(q)})
            else:
                cambio = True
        if cambio or recortes:
            for m in recortes.values():   # efímero: se ve unos segundos y listo
                toast_pendiente(m)
            if recortes:   # redibujar los inputs con el valor ya acotado
                st.session_state.cart_ver = ver + 1
            guardar_cart(nuevos)
            st.rerun()

    with right:
        iva_pct = float(overrides.get_config().get("iva_pct") or 0)
        tot = pedidos.calcular_totales([dict(i) for i in items], cli.get("descuento", 0), iva_pct=iva_pct)
        iva_html = ""
        if iva_pct > 0:
            iva_html = (f"<div class='muted'>IVA {tot['iva_pct']:g}%: {fmt_money(tot['iva_monto'])}</div>"
                        f"<div class='muted'>Total c/IVA: <b>{fmt_money(tot['total_con_iva'])}</b></div>")
        ahorro_html = ""
        if float(tot.get("ahorro_descvta") or 0) > 0:
            ahorro_html = (f"<div style='color:#d6006c'>Ahorro por ofertas: "
                           f"<b>-{fmt_money(tot['ahorro_descvta'])}</b></div>")
        st.markdown(f"""<div class='total-box'>
          <div class='kicker'>Resumen</div>
          <div>Unidades: <b>{tot['unidades']}</b></div>
          {ahorro_html}
          <div>Subtotal{', sin IVA' if iva_pct > 0 else ''}: <b>{fmt_money(tot['subtotal'])}</b></div>
          <div>Descuento cabecera {tot['descuento_pct']:g}%: <b>-{fmt_money(tot['descuento_monto'])}</b></div>
          <div style='font-size:1.35rem;margin-top:.4rem'>TOTAL: <b>{fmt_money(tot['total'])}</b></div>
          {iva_html}
          </div>""", unsafe_allow_html=True)
        minimo_m = float(overrides.get_config().get("minimo_pedido_monto") or 0)
        sub_lista = sum(int(i["cantidad"]) * float(i.get("precio_lista") or i["precio_unit"]) for i in items)
        if minimo_m and sub_lista < minimo_m:
            st.markdown(f"<div class='nota-acento'>El mínimo de compra es {fmt_money(minimo_m)} a "
                        f"precio de lista — te faltan {fmt_money(minimo_m - sub_lista)} para "
                        "poder confirmar.</div>", unsafe_allow_html=True)
        if not puede_pedir():
            st.warning("Tu usuario no tiene cliente asociado; no podés confirmar pedidos.")
        with st.form("confirmar_form", border=False):
            st.markdown("<div class='kicker'>Contacto para este pedido</div>"
                        "<p class='muted' style='margin:0 0 .3rem'>Con quién coordina Lautin la "
                        "entrega. Si lo cambiás, queda guardado para la próxima.</p>",
                        unsafe_allow_html=True)
            contacto_nombre = st.text_input("Persona de contacto",
                                            value=cli.get("contacto_nombre") or "",
                                            placeholder="Nombre y apellido")
            contacto_email = st.text_input("Email de contacto",
                                           value=cli.get("contacto_email")
                                           or st.session_state.user.get("email", ""))
            contacto_tel = st.text_input("Teléfono de contacto",
                                         value=cli.get("contacto_telefono") or "",
                                         placeholder="+54 9 ...")
            obs = st.text_area("Observaciones para Lautin (opcional)", height=90)
            confirmar = st.form_submit_button("Confirmar pedido", type="primary", use_container_width=True,
                                              disabled=not puede_pedir())
        if confirmar and not st.session_state.get("confirmando"):
            contacto_nombre = contacto_nombre.strip()
            contacto_email = contacto_email.strip().lower()
            contacto_tel = contacto_tel.strip()
            if contacto_email and ("@" not in contacto_email or " " in contacto_email):
                st.error("El email de contacto no parece válido.")
                st.stop()
            # Persistir el contacto para la próxima (merge: no toca descuento/lista)
            if (contacto_nombre != (cli.get("contacto_nombre") or "")
                    or contacto_email != (cli.get("contacto_email") or "")
                    or contacto_tel != (cli.get("contacto_telefono") or "")):
                overrides.set_cliente_override(int(cli["cliente_cod"]),
                                               {"contacto_nombre": contacto_nombre,
                                                "contacto_email": contacto_email,
                                                "contacto_telefono": contacto_tel},
                                               st.session_state.user.get("email", ""))
            cli = {**cli, "contacto_nombre": contacto_nombre, "contacto_email": contacto_email,
                   "contacto_telefono": contacto_tel}
            st.session_state.confirmando = True
            try:
                with st.spinner("Validando stock y generando el pedido..."):
                    p, xlsx = pedidos.confirmar_pedido(st.session_state.user, cli, items, obs)
                    st.session_state.cart = []
                    st.session_state.pedido_ok = (p, xlsx)
                    st.session_state.pop("stock_avisos", None)
                    st.session_state.confirmando = False
                st.rerun()
            except pedidos.StockInsuficiente as e:
                st.session_state.confirmando = False
                disp = {x["sku"]: x["disponible"] for x in e.problemas}
                ajust, avisos_n = [], {}
                for it in items:
                    if it["sku"] in disp:
                        d = disp[it["sku"]]
                        if d <= 0:
                            avisos_n[it["sku"]] = "Sin disponibilidad — se quitó del carrito"
                            continue
                        # Nunca revelar el stock: solo que superó lo disponible.
                        avisos_n[it["sku"]] = (f"Pediste {it['cantidad']} u. y supera la cantidad "
                                               "disponible — lo ajustamos al máximo posible")
                        it = {**it, "cantidad": d, "stock": d}
                    ajust.append(it)
                guardar_cart(ajust)
                st.session_state.stock_avisos = avisos_n
                st.session_state.cart_ver = st.session_state.get("cart_ver", 0) + 1
                catalog.load_variantes(force=True)
                st.rerun()
            except pedidos.MinimoNoAlcanzado as e:
                st.session_state.confirmando = False
                st.error(f"El pedido mínimo es de {e.minimo} unidades y tenés {e.unidades}. "
                         "Agregá más productos para confirmar.")
            except pedidos.MinimoMontoNoAlcanzado as e:
                st.session_state.confirmando = False
                st.error(f"El mínimo de compra es {fmt_money(e.minimo)} a precio de lista (sin IVA "
                         f"ni descuento) y tu subtotal es {fmt_money(e.subtotal)} — te faltan "
                         f"{fmt_money(e.minimo - e.subtotal)}.")
            except Exception as e:  # noqa: BLE001
                st.session_state.confirmando = False
                log.exception("Error confirmando pedido")
                st.error(f"No se pudo confirmar el pedido: {e}")
        if st.button("Vaciar carrito"):
            guardar_cart([])
            st.session_state.pop("stock_avisos", None)
            toast_pendiente("Vaciaste el carrito.")
            st.rerun()


# ---------------------------------------------------------------------------
# Mis pedidos
# ---------------------------------------------------------------------------
@st.dialog("Cancelar pedido")
def _confirmar_cancelacion(numero: int) -> None:
    st.warning(f"Vas a cancelar el pedido **N° {numero}**. Lautin recibe un aviso por email. ¿Seguro?")
    c1, c2 = st.columns(2)
    if c1.button("Sí, cancelar el pedido", type="primary", use_container_width=True):
        try:
            with st.spinner("Cancelando y avisando a Lautin..."):
                pedidos.cancelar_por_cliente(numero, st.session_state.user)
            st.toast(f"Pedido {numero} cancelado")
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    if c2.button("No, volver", use_container_width=True):
        st.rerun()


TAG_ESTADO = {"confirmado": "tag-conf", "procesado": "tag-proc", "cancelado": "tag-canc"}


def tag_estado(estado: str) -> str:
    return f"<span class='tag {TAG_ESTADO.get(estado, 'tag-proc')}'>{estado}</span>"


def page_pedidos() -> None:
    user = st.session_state.user
    es_admin = user.get("rol") == "admin"
    st.markdown("## Mis pedidos" if not es_admin else "## Pedidos (todos los clientes)")
    cliente_cod = None if es_admin else (st.session_state.get("cliente") or {}).get("cliente_cod")
    if not es_admin and cliente_cod is None:
        st.markdown("<p class='muted'>Tu usuario no tiene cliente asociado.</p>", unsafe_allow_html=True)
        return
    with st.spinner("Buscando pedidos..."):
        lista = pedidos.listar_pedidos(cliente_cod)
    if not lista:
        st.markdown("<p class='muted'>Todavía no hay pedidos.</p>", unsafe_allow_html=True)
        return
    tabla = pd.DataFrame([{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""),
        **({"Cliente": f"{p['cliente_cod']} · {p['cliente_nombre'][:36]}"} if es_admin else {}),
        "Unidades": p["unidades"], "Total": p["total"], "Estado": p["estado"],
    } for p in lista])
    ev = st.dataframe(tabla, hide_index=True, use_container_width=True, key="ped_tabla",
                      on_select="rerun", selection_mode="single-row",
                      column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})
    if not ev.selection.rows:
        st.markdown("<p class='muted'>Click en una fila para ver el detalle.</p>", unsafe_allow_html=True)
        return
    p = lista[ev.selection.rows[0]]

    st.markdown(f"### Pedido N° {p['numero']} &nbsp; {tag_estado(p['estado'])}", unsafe_allow_html=True)
    extra = f" · IVA {p['iva_pct']:g}%: {fmt_money(p.get('iva_monto', 0))}" if float(p.get("iva_pct") or 0) > 0 else ""
    st.markdown(f"<p class='muted'>{p['fecha_str']} · {p['unidades']} u. · total {fmt_money(p['total'])} "
                f"(desc. {p['descuento_pct']:g}%){extra}</p>", unsafe_allow_html=True)
    if p.get("observaciones"):
        st.markdown(f"<p class='muted'>Obs: {p['observaciones']}</p>", unsafe_allow_html=True)
    items_df = pd.DataFrame(p["items"])
    items_df["foto"] = items_df.apply(
        lambda r: fotos.miniatura(r["producto_cod"], r.get("color")) if fotos.tiene_fotos(r["producto_cod"]) else "",
        axis=1)
    st.dataframe(items_df[["foto", "producto_cod", "producto_nombre", "color", "talle", "cantidad",
                           "precio_unit", "subtotal"]], hide_index=True, use_container_width=True,
                 column_config={"foto": st.column_config.ImageColumn("", width="small"),
                                "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color",
                                "talle": "Talle", "cantidad": "Cant.",
                                "precio_unit": st.column_config.NumberColumn("Precio lista", format="$ %.0f"),
                                "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.0f")})
    b1, b2, b3, b4 = st.columns([1.1, 1.1, 1.1, 1.5])
    if pedidos.puede_cancelar(p, st.session_state.user) and \
            b3.button("Cancelar pedido", key=f"cx_{p['numero']}", use_container_width=True):
        _confirmar_cancelacion(p["numero"])
    if puede_pedir() and b1.button("Repetir pedido", type="primary", key=f"rep_{p['numero']}",
                                   use_container_width=True):
        with st.spinner("Cargando el pedido al carrito con stock y precios actuales..."):
            items, avisos_rep = pedidos.repetir_pedido(p, df_catalogo())
        for a in avisos_rep:
            st.warning(a)
        if items:
            nuevos = st.session_state.cart
            for it in items:
                nuevos = pedidos.agregar_al_carrito(nuevos, it)
            guardar_cart(nuevos)
            st.session_state.cart_ver = st.session_state.get("cart_ver", 0) + 1
            toast_pendiente(f"Pedido cargado al carrito: {sum(i['cantidad'] for i in items)} unidades.")
            if not avisos_rep:
                ir("carrito")
        else:
            st.error("Ninguna variante de ese pedido está disponible hoy.")
    data = pedidos.generar_excel(p)   # fresco: siempre con las fotos
    b2.download_button("Descargar Excel", data=data, file_name=p["xlsx_filename"], use_container_width=True,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    boton_odoo(p, key=f"odoo_{p['numero']}", col=b4)


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


TIPO_INCIDENCIA = {"ok": "Agregada", "ajustada": "Ajustada", "no_encontrada": "No encontrada",
                   "sin_precio": "Sin precio", "ilegible": "Ilegible"}


def page_reposicion() -> None:
    """Reposición sugerida (fase 11) — solo franquicias con PV asociado."""
    cli = cliente_efectivo()
    dias_default = int(overrides.get_config().get("repo_dias_objetivo") or 21)
    t1, t2 = st.columns([1, 1.9], vertical_alignment="bottom")
    t1.markdown("## Reposición")
    opciones_dias = sorted({7, 14, 21, 30, dias_default})
    if "repo_dias" not in st.session_state:
        st.session_state.repo_dias = dias_default
    dias = st.pills("Días de venta a cubrir", opciones_dias, key="repo_dias",
                    format_func=lambda d: f"{d} días") or dias_default
    df = df_catalogo()
    with st.spinner("Calculando la reposición sugerida..."):
        pv, sug = reposicion.sugerencias(int(cli["cliente_cod"]), df, dias)
    if pv is None:
        st.markdown("<p class='muted'>Tu cuenta no tiene un punto de venta asociado.</p>",
                    unsafe_allow_html=True)
        return
    t2.markdown(f"<p class='muted'>Según lo que vendió <b>{pv['pv_nombre']}</b> en los últimos "
                f"30 días, cantidades sugeridas para cubrir {dias} días. Lo más urgente primero. "
                "Ajustá lo que quieras y agregá al carrito.</p>", unsafe_allow_html=True)
    if sug.empty:
        st.markdown("<p class='muted'>Nada para reponer hoy: lo que vendés está cubierto o sin "
                    "disponibilidad para reposición.</p>", unsafe_allow_html=True)
        return
    # Mismos filtros que Compra rápida (facetado dependiente) + Temporada
    c1, c2, c3, c4, c5 = st.columns([1.5, 1, 1, 1.2, 1])
    busq_r = c1.text_input("Buscar", key="rp_busq", placeholder="código, nombre, EAN, color")
    sel_prev = {"marca": st.session_state.get("rp_marca", []),
                "categoria": st.session_state.get("rp_cat", []),
                "rubro": st.session_state.get("rp_rubro", []),
                "temporada": st.session_state.get("rp_temp", [])}
    ops = catalog.opciones_filtros(sug, sel_prev)
    for k, campo in (("rp_marca", "marca"), ("rp_cat", "categoria"),
                     ("rp_rubro", "rubro"), ("rp_temp", "temporada")):
        st.session_state[k] = [v for v in st.session_state.get(k, []) if v in ops[campo]]
    marca_r = c2.multiselect("Marca", ops["marca"], key="rp_marca", placeholder="Todas")
    cat_r = c3.multiselect("Categoría", ops["categoria"], key="rp_cat", placeholder="Todas")
    tipo_r = c4.multiselect("Tipo de producto", ops["rubro"], key="rp_rubro", placeholder="Todos")
    temp_r = c5.multiselect("Temporada", ops["temporada"], key="rp_temp", placeholder="Todas")
    solo_desc_r = st.checkbox("Solo con descuento", value=False, key="rp_desc",
                              help="Solo variantes con oferta (descuento por artículo).")
    sug = catalog.filtrar_variantes(sug, {"marca": marca_r, "categoria": cat_r,
                                          "rubro": tipo_r, "temporada": temp_r}, busq_r)
    if solo_desc_r and "descvta" in sug.columns:
        sug = sug[sug["descvta"] > 0]
    if sug.empty:
        st.markdown("<p class='muted'>Nada sugerido con esos filtros.</p>", unsafe_allow_html=True)
        return
    fkey = "".join(ch for ch in "-".join([busq_r, str(solo_desc_r)] + sorted(marca_r + cat_r + tipo_r + temp_r))
                   if ch.isalnum())[:48]
    ver = st.session_state.get("repo_ver", 0)
    tabla = sug[["foto", "producto_cod", "producto_nombre", "color", "talle", "vendidas_30d",
                 "stock_pv", "precio_lista", "pct_desc", "precio", "sugerido"]].copy()
    tabla["stock_pv"] = tabla["stock_pv"].clip(lower=0)
    tabla["precio_lista_disp"] = [fmt_money(pl) if pd_ > 0 else "" for pl, pd_ in zip(tabla["precio_lista"], tabla["pct_desc"])]
    tabla["desc_disp"] = [f"−{p:g}%" if p > 0 else "" for p in tabla["pct_desc"]]
    tabla = tabla.drop(columns=["precio_lista", "pct_desc"]).rename(columns={"sugerido": "cantidad"})
    edited = st.data_editor(
        tabla[["foto", "producto_cod", "producto_nombre", "color", "talle", "vendidas_30d",
               "stock_pv", "precio_lista_disp", "desc_disp", "precio", "cantidad"]],
        hide_index=True, use_container_width=True, key=f"repo_editor_{ver}_{dias}_{fkey}",
        disabled=["foto", "producto_cod", "producto_nombre", "color", "talle", "vendidas_30d",
                  "stock_pv", "precio_lista_disp", "desc_disp", "precio"],
        column_config={
            "foto": st.column_config.ImageColumn("", width="small"),
            "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color",
            "talle": "Talle",
            "vendidas_30d": st.column_config.NumberColumn("Vendiste 30d", format="%d"),
            "stock_pv": st.column_config.NumberColumn("Tenés", format="%d"),
            "precio_lista_disp": st.column_config.TextColumn("Precio lista"),
            "desc_disp": st.column_config.TextColumn("Desc."),
            "precio": st.column_config.NumberColumn("Precio", format="$ %.0f"),
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1),
        })
    seleccion = []
    for (_, v), (_, e) in zip(sug.iterrows(), edited.iterrows()):
        q = int(e["cantidad"] or 0)
        if q <= 0:
            continue
        q = min(q, int(v["stock"]))   # sin revelar stock: se acota en silencio
        ub = int(v["ub"]) if "ub" in sug.columns and pd.notna(v.get("ub")) and v.get("ub") else 0
        if ub > 1:
            q = (q // ub) * ub
        if q > 0:
            seleccion.append((v, q))
    items = [cr.item_desde_variante(v, q) for v, q in seleccion]
    _totales_seleccion(items)
    # Export/import Excel, igual que Compra rápida (Cantidad precargada con lo sugerido)
    iva_x = float(overrides.get_config().get("iva_pct") or 0)
    cants_r = {str(v["sku"]): int(e["cantidad"] or 0)
               for (_, v), (_, e) in zip(sug.iterrows(), edited.iterrows())}
    links_r = {str(r["sku"]): u for _, r in sug.iterrows()
               if (u := fotos.url_variante_publica(r["producto_cod"], r["color"],
                                                   solo_color=True))}
    ba, bx = st.columns([1, 1])
    firma_r = (dias, fkey)
    if bx.button("Exportar Excel del filtro actual", key="rp_xlsx_btn", use_container_width=True,
                 help="Con la miniatura de cada variante embebida (hasta 600 filas; con más, va sin "
                      "fotos) y la Cantidad precargada con lo sugerido. Editalo offline y subilo "
                      "de nuevo acá abajo."):
        con_fotos = len(sug) <= 600
        minis = None
        if con_fotos:
            with st.spinner(f"Armando el Excel con {len(sug)} miniaturas..."):
                minis = _miniaturas_excel(sug)
        else:
            st.warning(f"El filtro tiene {len(sug)} variantes y el máximo con fotos es 600 — "
                       "te lo doy sin fotos (afiná los filtros si las querés).")
        st.session_state.rp_xlsx = (firma_r, cr.excel_plantilla(
            sug, cants_r, cliente=cli, iva_pct=iva_x, links_foto=links_r,
            miniaturas=minis), con_fotos)
    listo_r = st.session_state.get("rp_xlsx")
    if listo_r and listo_r[0] == firma_r:
        bx.download_button("Descargar Excel (con fotos)" if listo_r[2] else "Descargar Excel (sin fotos)",
                           data=listo_r[1], key="rp_xlsx_dl", use_container_width=True,
                           file_name="reposicion.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if ba.button("Agregar reposición al carrito", type="primary", disabled=not items,
                 key="rp_add", use_container_width=True):
        total = _agregar_items(items)
        st.session_state.repo_ver = ver + 1
        toast_pendiente(f"Agregaste {total} unidades al carrito.")
        st.rerun()
    st.markdown("<div class='kicker' style='margin-top:.6rem'>Cargar el Excel que exportaste</div>",
                unsafe_allow_html=True)
    up = st.file_uploader("Subí el archivo con la columna Cantidad completa", type=["xlsx"],
                          key="rp_file", label_visibility="collapsed")
    if up is not None:
        data_up = up.getvalue()
        hash_up = hashlib.md5(data_up).hexdigest()
        ya_cargado = st.session_state.get("rp_file_hash") == hash_up
        texto_up, err = cr.texto_desde_excel(data_up)
        if err:
            st.error(err)
        elif not texto_up:
            st.warning("El archivo no tiene ninguna fila con Cantidad mayor a 0.")
        elif ya_cargado:
            st.markdown("<p class='muted'>Ese archivo ya se cargó al carrito — modificalo o subí "
                        "otro.</p>", unsafe_allow_html=True)
            procesar = st.button("Cargarlo al carrito de nuevo", key="rp_up_otra_vez")
        else:
            procesar = st.button(f"Cargar al carrito las {len(texto_up.splitlines())} líneas con cantidad",
                                 type="primary", key="rp_up_add")
        if up is not None and not err and texto_up and procesar:
            items_up, incidencias = cr.resolver_pegado(texto_up, df)
            total = _agregar_items(items_up) if items_up else 0
            toast_pendiente(f"Agregaste {total} unidades al carrito desde el archivo." if total
                            else "No se agregó nada — revisá el detalle de las líneas.")
            st.session_state.rp_resultado = (cr.resumen_incidencias(incidencias), incidencias, total)
            st.session_state.rp_file_hash = hash_up
            st.rerun()
    _mostrar_resultado_cr("rp_resultado")


def _miniaturas_excel(sub: pd.DataFrame) -> dict[str, bytes]:
    """{sku: JPEG chico} para el Excel con fotos (descarga en paralelo; cache en fotos)."""
    from concurrent.futures import ThreadPoolExecutor

    def una(r):
        fn = (fotos.foto_variante_filename(r["producto_cod"], r["color"], solo_color=True)
              if fotos.tiene_fotos(r["producto_cod"]) else None)
        return str(r["sku"]), (fotos.miniatura_jpeg(r["producto_cod"], fn) if fn else None)

    with ThreadPoolExecutor(max_workers=12) as ex:
        return {sku: img for sku, img in ex.map(una, (r for _, r in sub.iterrows())) if img}


def _mostrar_resultado_cr(key: str) -> None:
    """Contadores + reconciliación del último procesamiento (post-rerun)."""
    # Resultado del procesamiento anterior (post-rerun: contadores + reconciliación)
    if st.session_state.get(key):
        resumen, incidencias, total_u = st.session_state.pop(key)
        r1, r2, r3, _ = st.columns([1, 1, 1, 2])
        r1.markdown(f"<div class='kicker'>Agregadas</div><h3 style='color:#006786'>{resumen['agregadas']}</h3>",
                    unsafe_allow_html=True)
        r2.markdown(f"<div class='kicker'>Ajustadas</div><h3>{resumen['ajustadas']}</h3>",
                    unsafe_allow_html=True)
        r3.markdown(f"<div class='kicker'>Sin reconocer</div><h3 style='color:#aa0b56'>{resumen['sin_reconocer']}</h3>",
                    unsafe_allow_html=True)
        if total_u:
            st.success(f"{total_u} unidades agregadas al carrito.")
        if incidencias:
            inc_df = pd.DataFrame(incidencias)
            inc_df["tipo"] = inc_df["tipo"].map(TIPO_INCIDENCIA)
            st.dataframe(inc_df.rename(columns={"linea": "Línea", "codigo": "Código", "tipo": "Resultado",
                                                "pedido": "Pedido", "cargado": "Cargado", "detalle": "Detalle"}),
                         hide_index=True, use_container_width=True)


def page_cuenta() -> None:
    """Mis datos: datos del cliente (solo lectura) + contacto y password editables."""
    user = st.session_state.user
    cli = st.session_state.get("cliente")
    st.markdown("## Mis datos")
    c1, c2 = st.columns([1.25, 1], gap="large")
    with c1:
        st.markdown(f"<div class='kicker'>Tu usuario</div><p class='muted' style='margin:.2rem 0 1rem'>"
                    f"{user['email']} · rol {user.get('rol', 'cliente')}</p>", unsafe_allow_html=True)
        if cli:
            filas = [("Razón social", cli.get("nombre_display") or cli.get("nombre") or "—"),
                     ("Cliente", str(cli.get("cliente_cod") or "—")),
                     ("Lista de precios", str(cli.get("lista_precios") or "—")),
                     ("Descuento cabecera", f"{float(cli.get('descuento') or 0):g}%"),
                     ("CUIT", cli.get("cuit") or "—")]
            st.markdown("".join(f"<div style='padding:.35rem 0;border-bottom:1px solid #d8d5d2'>"
                                f"<span class='muted'>{k}</span> &nbsp; <b>{v}</b></div>"
                                for k, v in filas), unsafe_allow_html=True)
            st.markdown("<p class='muted' style='margin-top:.6rem'>Estos datos vienen de Lautin — "
                        "si algo está mal, avisá por WhatsApp.</p>", unsafe_allow_html=True)
            st.markdown("<div class='kicker' style='margin-top:1rem'>Contacto para pedidos</div>",
                        unsafe_allow_html=True)
            with st.form("cuenta_contacto", border=False):
                nom_c = st.text_input("Persona de contacto", value=cli.get("contacto_nombre") or "",
                                      placeholder="Nombre y apellido")
                mail_c = st.text_input("Email de contacto",
                                       value=cli.get("contacto_email") or user.get("email", ""))
                tel_c = st.text_input("Teléfono de contacto", value=cli.get("contacto_telefono") or "",
                                      placeholder="+54 9 ...")
                if st.form_submit_button("Guardar contacto", type="primary"):
                    nom_c, mail_c, tel_c = nom_c.strip(), mail_c.strip().lower(), tel_c.strip()
                    overrides.set_cliente_override(int(cli["cliente_cod"]),
                                                   {"contacto_nombre": nom_c, "contacto_email": mail_c,
                                                    "contacto_telefono": tel_c},
                                                   user["email"])
                    st.session_state.cliente = {**cli, "contacto_nombre": nom_c, "contacto_email": mail_c,
                                                "contacto_telefono": tel_c}
                    toast_pendiente("Contacto guardado.")
                    st.rerun()
        else:
            st.markdown("<p class='muted'>Tu usuario no tiene cliente asociado.</p>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='kicker'>Cambiar password</div>", unsafe_allow_html=True)
        with st.form("cuenta_pwd", border=False, clear_on_submit=True):
            actual = st.text_input("Password actual", type="password")
            n1 = st.text_input("Password nueva (mínimo 8 caracteres)", type="password")
            n2 = st.text_input("Repetir la password nueva", type="password")
            cambiar = st.form_submit_button("Cambiar password", use_container_width=True)
        if cambiar:
            u = auth.get_usuario(user["email"])
            if not auth.verify_password(actual, (u or {}).get("password_hash")):
                st.error("La password actual no es correcta.")
            elif len(n1) < 8:
                st.error("La password nueva debe tener al menos 8 caracteres.")
            elif n1 != n2:
                st.error("Las passwords nuevas no coinciden.")
            else:
                auth.cambiar_password(user["email"], n1)
                st.success("Password actualizada — usala en tu próximo ingreso.")


def page_compra_rapida() -> None:
    st.markdown("## Compra rápida")
    if not puede_pedir():
        st.markdown("<p class='muted'>Tu usuario no tiene cliente asociado; no podés pedir.</p>",
                    unsafe_allow_html=True)
        return
    df = df_catalogo()
    df = df[df["precio"].notna()]

    c1, c2, c3, c4, c5 = st.columns([1.5, 1, 1, 1.2, 1])
    busq = c1.text_input("Buscar", key="cr_busq", placeholder="código, nombre, EAN, color")
    # Facetado dependiente: cada filtro solo ofrece opciones con match en los otros.
    sel_prev = {"marca": st.session_state.get("cr_marca", []),
                "categoria": st.session_state.get("cr_cat", []),
                "rubro": st.session_state.get("cr_rubro", []),
                "temporada": st.session_state.get("cr_temp", [])}
    ops = catalog.opciones_filtros(df, sel_prev)
    for k, campo in (("cr_marca", "marca"), ("cr_cat", "categoria"),
                     ("cr_rubro", "rubro"), ("cr_temp", "temporada")):
        st.session_state[k] = [v for v in st.session_state.get(k, []) if v in ops[campo]]
    marca = c2.multiselect("Marca", ops["marca"], key="cr_marca", placeholder="Todas")
    categoria = c3.multiselect("Categoría", ops["categoria"], key="cr_cat", placeholder="Todas")
    tipo = c4.multiselect("Tipo de producto", ops["rubro"], key="cr_rubro", placeholder="Todos")
    temporada = c5.multiselect("Temporada", ops["temporada"], key="cr_temp", placeholder="Todas")
    solo_desc = st.checkbox("Solo con descuento", value=False, key="cr_desc",
                            help="Solo variantes con oferta (descuento por artículo).")
    sub = catalog.filtrar_variantes(df, {"marca": marca, "categoria": categoria, "rubro": tipo,
                                         "temporada": temporada}, busq).copy()
    if solo_desc and "descvta" in sub.columns:
        sub = sub[sub["descvta"] > 0]
    st.markdown(f"<p class='muted'>{len(sub)} variantes con stock y precio · scrolleá la tabla, "
                "cargá cantidades y tocá Agregar</p>", unsafe_allow_html=True)
    # Scroll infinito: una sola tabla con TODO el filtro (Streamlit la virtualiza).
    # Fotos con URL pública del bucket: firmar miles de URLs sería una llamada por foto.
    sub["foto"] = [fotos.url_variante_publica(pcod, c)
                   for pcod, c in zip(sub["producto_cod"], sub["color"])]
    # Las variantes CON miniatura primero (los códigos "A" sin foto iban
    # arriba por orden alfabético y la tabla arrancaba pelada).
    sub = sub.sort_values("foto", key=lambda c: c == "", kind="stable")
    sub["cantidad"] = 0
    # Detalle de oferta: precio de lista y % SOLO en las filas con descuento
    # (vacío en el resto → no ensucia). "precio" es el final que se paga.
    # Texto preformateado ("" = celda vacía; NumberColumn con NaN muestra "None" en Streamlit 1.41).
    sub["precio_lista_disp"] = [fmt_money(pl) if pd_ > 0 else "" for pl, pd_ in zip(sub["precio_lista"], sub["pct_desc"])]
    sub["desc_disp"] = [f"−{p:g}%" if p > 0 else "" for p in sub["pct_desc"]]
    ver = st.session_state.get("cr_ver", 0)
    # Sin columna de stock: el cliente nunca ve cuánto queda.
    edited = st.data_editor(
        sub[["foto", "producto_cod", "producto_nombre", "color", "talle",
             "precio_lista_disp", "desc_disp", "precio", "cantidad"]],
        hide_index=True, use_container_width=True, height=620, key=f"cr_editor_{ver}",
        disabled=["foto", "producto_cod", "producto_nombre", "color", "talle",
                  "precio_lista_disp", "desc_disp", "precio"],
        column_config={
            "foto": st.column_config.ImageColumn("", width="small"),
            "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color", "talle": "Talle",
            "precio_lista_disp": st.column_config.TextColumn("Precio lista"),
            "desc_disp": st.column_config.TextColumn("Desc."),
            "precio": st.column_config.NumberColumn("Precio", format="$ %.0f"),
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, format="%d"),
        })
    seleccion = [(v, int(q)) for (_, v), q in zip(sub.iterrows(), edited["cantidad"])
                 if int(q or 0) > 0]
    cli_x = cliente_efectivo()
    iva_x = float(overrides.get_config().get("iva_pct") or 0)
    cants_x = {str(v["sku"]): q for v, q in seleccion}
    links_x = {str(r["sku"]): u for _, r in sub.iterrows()
               if (u := fotos.url_variante_publica(r["producto_cod"], r["color"],
                                                   solo_color=True))}
    ba, bx = st.columns([1, 1])
    firma_f = (busq, tuple(marca), tuple(categoria), tuple(tipo), tuple(temporada), solo_desc)
    if bx.button("Exportar Excel del filtro actual", key="cr_xlsx_btn", use_container_width=True,
                 help="Con la miniatura de cada variante embebida (hasta 600 filas; con más, va "
                      "sin fotos). Cantidad editable, totales con tu descuento, link a cada foto. "
                      "Completalo offline y subilo de nuevo acá abajo."):
        con_fotos = len(sub) <= 600
        minis = None
        if con_fotos:
            with st.spinner(f"Armando el Excel con {len(sub)} miniaturas..."):
                minis = _miniaturas_excel(sub)
        else:
            st.warning(f"El filtro tiene {len(sub)} variantes y el máximo con fotos es 600 — "
                       "te lo doy sin fotos (afiná los filtros si las querés).")
        st.session_state.cr_xlsx = (firma_f, cr.excel_plantilla(
            sub, cants_x, cliente=cli_x, iva_pct=iva_x, links_foto=links_x,
            miniaturas=minis), con_fotos)
    listo = st.session_state.get("cr_xlsx")
    if listo and listo[0] == firma_f:
        bx.download_button("Descargar Excel (con fotos)" if listo[2] else "Descargar Excel (sin fotos)",
                           data=listo[1], key="cr_xlsx_dl", use_container_width=True,
                           file_name="compra_rapida.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if ba.button("Agregar al carrito", type="primary", disabled=not seleccion, key="cr_add",
                 use_container_width=True):
        items, ajustes = [], []
        for v, q in seleccion:
            pedido = int(q)
            q = min(pedido, int(v["stock"]))
            if q < pedido:   # sin revelar el stock — aviso efímero
                toast_pendiente(f"{v['sku']}: estás superando la cantidad disponible — "
                                f"se cargó {q} de {pedido}.")
            ub = int(v["ub"]) if ("ub" in v and pd.notna(v["ub"]) and v["ub"]) else 0
            if ub > 1 and q % ub:
                q = (q // ub) * ub
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
        toast_pendiente(f"Agregaste {total} unidades al carrito.")
        st.rerun()

    st.markdown("<div class='kicker' style='margin-top:.6rem'>Cargar el Excel que exportaste</div>",
                unsafe_allow_html=True)
    up = st.file_uploader("Subí el archivo con la columna Cantidad completa", type=["xlsx"],
                          key="cr_tabla_file", label_visibility="collapsed")
    if up is not None:
        data_up = up.getvalue()
        hash_up = hashlib.md5(data_up).hexdigest()
        ya_cargado = st.session_state.get("cr_tabla_file_hash") == hash_up
        texto_up, err = cr.texto_desde_excel(data_up)
        if err:
            st.error(err)
        elif not texto_up:
            st.warning("El archivo no tiene ninguna fila con Cantidad mayor a 0.")
        elif ya_cargado:
            st.markdown("<p class='muted'>Ese archivo ya se cargó al carrito — modificalo o subí "
                        "otro.</p>", unsafe_allow_html=True)
            procesar = st.button("Cargarlo al carrito de nuevo", key="cr_tabla_up_otra_vez")
        else:
            procesar = st.button(f"Cargar al carrito las {len(texto_up.splitlines())} líneas con cantidad",
                                 type="primary", key="cr_tabla_up_add")
        if up is not None and not err and texto_up and procesar:
            items_up, incidencias = cr.resolver_pegado(texto_up, df)
            total = _agregar_items(items_up) if items_up else 0
            toast_pendiente(f"Agregaste {total} unidades al carrito desde el archivo." if total
                            else "No se agregó nada — revisá el detalle de las líneas.")
            st.session_state.cr_resultado_tabla = (cr.resumen_incidencias(incidencias), incidencias, total)
            st.session_state.cr_tabla_file_hash = hash_up
            st.rerun()
    _mostrar_resultado_cr("cr_resultado_tabla")


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
    for m in st.session_state.pop("_toasts", []):
        st.toast(m)
    if usuario_actual() is None:
        header(con_marcas=False)
        page_login()
        footer()
        return
    tok = st.session_state.pop("pending_cookie", None)
    if tok:
        set_cookie(tok)
    # Deep-link al editor de producto del admin (columna "Editar →" / URL compartible)
    if "prod" in st.query_params and st.session_state.user.get("rol") == "admin":
        st.session_state.adm_prod = st.query_params["prod"]
        st.session_state.page = "admin"
        st.query_params.clear()
    # Deep-link a la ficha de producto (click en la imagen de una card, fase 8)
    if "p" in st.query_params:
        st.session_state.producto_sel = st.query_params["p"]
        st.session_state.page = "producto"
        st.query_params.clear()
    header()
    nav()
    page = st.session_state.get("page", "catalogo")
    {"catalogo": page_catalogo, "producto": page_producto, "carrito": page_carrito,
     "pedidos": page_pedidos, "compra_rapida": page_compra_rapida, "cuenta": page_cuenta,
     "reposicion": page_reposicion, "admin": page_admin}.get(page, page_catalogo)()
    footer()


main()
