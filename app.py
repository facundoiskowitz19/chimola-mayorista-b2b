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
  .card-title { font-weight:600; font-size:1.12rem; margin-top:.45rem; line-height:1.15; color:var(--text);
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .card-sub { color:var(--faint); font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; margin-top:.1rem; }
  .card-price { font-weight:600; font-size:1.15rem; margin-top:.2rem; }
  .tag { display:inline-block; padding:.12rem .55rem; border-radius:2px; font-size:.72rem; font-weight:600;
    letter-spacing:.08em; text-transform:uppercase; }
  .tag-conf { background:var(--accent-tint); color:var(--accent-press); }
  .tag-proc { background:var(--n200); color:#444141; }
  .tag-canc { background:var(--alert-tint); color:var(--alert-text); }
  .aviso-stock { color:var(--alert-text); font-size:.86rem; }
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
    items.append(("carrito", f"Carrito · {n_items} u."))
    items.append(("pedidos", "Mis pedidos"))
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
    elif campo == "todos":
        for f in catalog.FILTROS:
            st.session_state[f"f_{f}"] = []
        st.session_state.f_busqueda = ""
        st.session_state.f_fotos = False
    else:
        st.session_state[f"f_{campo}"] = [v for v in st.session_state.get(f"f_{campo}", []) if v != valor]


def _abrir_card(cod: str) -> None:
    st.session_state.card_abierta = None if st.session_state.get("card_abierta") == cod else cod


def matriz_variantes(prod: dict, key: str) -> list:
    """Matriz color x talle (handoff cambio 3): stock read-only arriba,
    cantidades editables abajo. Devuelve items de carrito."""
    vs = prod["variantes"]
    colores = list(dict.fromkeys(v["color"] for v in vs))
    talles = sorted({v["talle"] for v in vs}, key=catalog.talle_key)
    cols_t = [f"T {t}" for t in talles]
    by_ct = {(v["color"], v["talle"]): v for v in vs}
    ub = int(prod.get("ub") or 0)

    stock_df = pd.DataFrame([[by_ct.get((c, t), {}).get("stock") for t in talles] for c in colores],
                            index=colores, columns=cols_t)
    st.markdown("<div class='kicker'>Stock disponible</div>", unsafe_allow_html=True)
    st.dataframe(stock_df, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(c, format="%d") for c in cols_t})
    st.markdown("<div class='kicker'>Cantidades a pedir"
                + (f" — múltiplos de {ub}" if ub > 1 else "") + "</div>", unsafe_allow_html=True)
    qty0 = pd.DataFrame([[0 if (c, t) in by_ct else None for t in talles] for c in colores],
                        index=colores, columns=cols_t)
    ed = st.data_editor(qty0, key=key, use_container_width=True,
                        column_config={c: st.column_config.NumberColumn(c, min_value=0, step=ub or 1, format="%d")
                                       for c in cols_t})
    items = []
    for c in colores:
        for t in talles:
            v = by_ct.get((c, t))
            q = ed.loc[c, f"T {t}"]
            if v is None or pd.isna(q) or int(q) <= 0 or pd.isna(v["precio"]):
                continue
            q = min(int(q), int(v["stock"]))
            if ub > 1:
                q = (q // ub) * ub
            if q > 0:
                items.append(cr.item_desde_variante(v, q))
    return items


def _totales_seleccion(items: list) -> None:
    cli = cliente_efectivo()
    unidades = sum(i["cantidad"] for i in items)
    monto = sum(i["cantidad"] * i["precio_unit"] for i in items)
    if unidades:
        st.markdown(f"Seleccionadas <b>{unidades} u.</b> · {fmt_money(monto)} precio lista · "
                    f"<span style='color:#006786'>{fmt_money(catalog.aplicar_descuento(monto, cli.get('descuento', 0)))} "
                    f"con tu {cli.get('descuento', 0):g}%</span>", unsafe_allow_html=True)


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

    # Barra de facetas (handoff cambio 1)
    sel_prev = {f: st.session_state.get(f"f_{f}", []) for f in catalog.FILTROS}
    opciones = catalog.opciones_filtros(df, sel_prev)
    labels = {"marca": "Marca", "temporada": "Temporada", "rubro": "Rubro", "subrubro": "Subrubro"}
    fc = st.columns([2.4, 1, 1, 1, 1])
    busqueda = fc[0].text_input("Buscar", key="f_busqueda", placeholder="código, nombre, EAN, color")
    sel = {}
    for f, col in zip(catalog.FILTROS, fc[1:]):
        if not opciones[f] and not sel_prev[f]:
            sel[f] = []
            continue
        sel[f] = col.multiselect(labels[f], opciones[f], key=f"f_{f}", placeholder="Todos")
    solo_fotos = st.session_state.get("f_fotos", True)

    variantes = catalog.filtrar_variantes(df, sel, busqueda)
    prods = catalog.productos(variantes)
    if solo_fotos and not prods.empty:
        prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]
    if not prods.empty and "destacado" in variantes.columns:
        dest = variantes.groupby("producto_cod")["destacado"].first()
        prods = prods.assign(_d=prods["producto_cod"].map(dest).fillna(False))
        prods = prods.sort_values(["_d", "producto_cod"], ascending=[False, True]).drop(columns="_d")

    # Chips de filtros activos (handoff cambio 2)
    chips = []
    if busqueda:
        chips.append(("busq", None, f"“{busqueda}”"))
    for f in catalog.FILTROS:
        for v in sel.get(f, []):
            chips.append((f, v, str(v)))
    if solo_fotos:
        chips.append(("fotos", None, "Solo con foto"))
    anchos = [max(len(c[2]) * 0.058 + 0.3, 0.6) for c in chips] + ([0.62] if chips else []) + [2.2, 0.8]
    ccols = st.columns(anchos, vertical_alignment="center")
    for (campo, valor, label), col in zip(chips, ccols):
        col.button(f"{label} ×", key=f"chip_{campo}_{valor}", on_click=_quitar_filtro, args=(campo, valor))
    if chips:
        ccols[len(chips)].button("Limpiar", key="chip_todos_x", on_click=_quitar_filtro, args=("todos", None))
    ccols[-2].markdown(f"<div class='muted' style='text-align:right'>{len(prods)} productos · "
                       f"{len(variantes)} variantes con stock</div>", unsafe_allow_html=True)
    with ccols[-1]:
        st.checkbox("Con foto", value=True, key="f_fotos")

    firma = (busqueda, tuple(tuple(v) for v in sel.values()), solo_fotos)
    if st.session_state.get("cat_firma") != firma:
        st.session_state.cat_firma, st.session_state.cat_pagina = firma, 1
        st.session_state.card_abierta = None
    por_pag = config.ITEMS_POR_PAGINA
    n_pag = max(1, math.ceil(len(prods) / por_pag))
    pag = min(st.session_state.get("cat_pagina", 1), n_pag)
    if len(prods) == 0:
        st.markdown("<p class='muted'>No hay productos con stock para esos filtros.</p>", unsafe_allow_html=True)
        return

    sub = prods.iloc[(pag - 1) * por_pag: pag * por_pag]
    abierta = st.session_state.get("card_abierta")
    for k in range(0, len(sub), 4):
        fila = sub.iloc[k:k + 4]
        cols = st.columns(4)
        for i, (_, p) in enumerate(fila.iterrows()):
            with cols[i]:
                with st.container(key=f"card_{p['producto_cod']}"):
                    st.image(fotos.foto_principal(p["producto_cod"]), use_container_width=True)
                    st.markdown(
                        f"<div class='card-title' title='{p['producto_nombre']}'>{p['producto_nombre']}</div>"
                        f"<div class='card-sub'>{p['producto_cod']} · {p['marca'] or ''} · {p['rubro'] or ''}</div>"
                        f"<div class='card-price'>{fmt_money(p['precio'])}</div>"
                        f"<div class='muted'>{int(p['stock'])} u. · {len(p['colores'])} color(es)</div>",
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
                    pi, pdet = st.columns([1, 3.1], gap="medium")
                    with pi:
                        st.image(fotos.foto_principal(abierta), use_container_width=True)
                    with pdet:
                        st.markdown(f"### {prod['producto_nombre']}")
                        st.markdown(f"<div class='card-sub'>{abierta} · {prod['marca'] or ''} · "
                                    f"{prod['temporada'] or ''} · {prod['rubro'] or ''}</div>",
                                    unsafe_allow_html=True)
                        ver = st.session_state.get("mx_ver", 0)
                        items = matriz_variantes(prod, key=f"mx_{abierta}_{ver}")
                        _totales_seleccion(items)
                        b1, b2, b3 = st.columns([1.3, 1.3, 2.2])
                        if b1.button("Agregar al carrito", type="primary", key=f"padd_{abierta}",
                                     disabled=not items, use_container_width=True):
                            total = _agregar_items(items)
                            st.session_state.mx_ver = ver + 1
                            st.session_state.card_abierta = None
                            st.toast(f"{total} unidades agregadas al carrito")
                            st.rerun()
                        if b2.button("Ver ficha completa", key=f"pfull_{abierta}", use_container_width=True):
                            ir("producto", producto_sel=abierta)
                        if b3.button("Cerrar", key=f"pcls_{abierta}"):
                            st.session_state.card_abierta = None
                            st.rerun()

    n1, n2, n3 = st.columns([4.4, 0.4, 0.4])
    n1.markdown(f"<div class='muted'>{len(prods)} productos · página {pag} de {n_pag}</div>", unsafe_allow_html=True)
    if n2.button("‹", key="cat_prev", disabled=pag <= 1):
        st.session_state.cat_pagina = pag - 1
        st.rerun()
    if n3.button("›", key="cat_next", disabled=pag >= n_pag):
        st.session_state.cat_pagina = pag + 1
        st.rerun()


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
        st.markdown(f"<div class='card-sub'>{prod['producto_cod']} · {prod['marca'] or ''} · "
                    f"{prod['temporada'] or ''} · {prod['rubro'] or ''}"
                    f"{(' / ' + prod['subrubro']) if prod.get('subrubro') else ''}</div>", unsafe_allow_html=True)
        if prod["precio"] is None:
            st.error(f"Este producto no tiene precio cargado en la lista {cli['lista_precios']}. "
                     "No se puede pedir — consultá a Lautin.")
        else:
            st.markdown(f"### {fmt_money(prod['precio'])} <span class='muted'>precio lista "
                        f"{cli['lista_precios']}{iva_tag}</span>", unsafe_allow_html=True)
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
def _quitar_item(sku: str) -> None:
    items = [i for i in st.session_state.cart if i["sku"] != sku]
    st.session_state.cart = items
    pedidos.guardar_carrito(st.session_state.user["email"], items)
    st.session_state.cart_ver = st.session_state.get("cart_ver", 0) + 1


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
        st.error(f"Cambió el stock de {len(avisos)} variante(s): ajustamos el carrito. "
                 "Revisá las filas marcadas y volvé a confirmar.")
        en_carrito = {i["sku"] for i in items}
        for sku, msg in avisos.items():
            if sku not in en_carrito:
                st.markdown(f"<div class='aviso-stock'>{sku}: {msg}</div>", unsafe_allow_html=True)

    ver = st.session_state.get("cart_ver", 0)
    left, right = st.columns([2.55, 1.25], gap="large")
    with left:
        h = st.columns([0.5, 2.3, 0.95, 0.85, 0.85, 0.3])
        for col, txt in zip(h, ["", "Producto", "Cantidad", "Precio lista", "Subtotal", ""]):
            col.markdown(f"<div class='kicker'>{txt}</div>", unsafe_allow_html=True)
        nuevos, cambio = [], False
        for it in items:
            c = st.columns([0.5, 2.3, 0.95, 0.85, 0.85, 0.3], vertical_alignment="center")
            with c[0]:
                if fotos.tiene_fotos(it["producto_cod"]):
                    st.image(fotos.foto_principal(it["producto_cod"]), width=52)
            c[1].markdown(f"<b>{it['producto_nombre']}</b><br><span class='card-sub'>"
                          f"{it['producto_cod']} · {it['color']} · T {it['talle']}</span>", unsafe_allow_html=True)
            q = c[2].number_input("Cantidad", min_value=0, max_value=int(it.get("stock") or 99999),
                                  value=int(it["cantidad"]), step=1, key=f"cq_{ver}_{it['sku']}",
                                  label_visibility="collapsed")
            c[3].markdown(fmt_money(it["precio_unit"]))
            c[4].markdown(f"<b>{fmt_money(int(q) * it['precio_unit'])}</b>", unsafe_allow_html=True)
            c[5].button("×", key=f"del_{it['sku']}", on_click=_quitar_item, args=(it["sku"],))
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
        if cambio:
            guardar_cart(nuevos)
            st.rerun()

    with right:
        iva_pct = float(overrides.get_config().get("iva_pct") or 0)
        tot = pedidos.calcular_totales([dict(i) for i in items], cli.get("descuento", 0), iva_pct=iva_pct)
        iva_html = ""
        if iva_pct > 0:
            iva_html = (f"<div class='muted'>IVA {tot['iva_pct']:g}%: {fmt_money(tot['iva_monto'])}</div>"
                        f"<div class='muted'>Total c/IVA: <b>{fmt_money(tot['total_con_iva'])}</b></div>")
        st.markdown(f"""<div class='total-box'>
          <div class='kicker'>Resumen</div>
          <div>Unidades: <b>{tot['unidades']}</b></div>
          <div>Subtotal (lista {cli['lista_precios']}{', sin IVA' if iva_pct > 0 else ''}): <b>{fmt_money(tot['subtotal'])}</b></div>
          <div>Descuento cabecera {tot['descuento_pct']:g}%: <b>-{fmt_money(tot['descuento_monto'])}</b></div>
          <div style='font-size:1.35rem;margin-top:.4rem'>TOTAL: <b>{fmt_money(tot['total'])}</b></div>
          {iva_html}
          </div>""", unsafe_allow_html=True)
        if not puede_pedir():
            st.warning("Tu usuario no tiene cliente asociado; no podés confirmar pedidos.")
        with st.form("confirmar_form", border=False):
            obs = st.text_area("Observaciones para Lautin (opcional)", height=90)
            confirmar = st.form_submit_button("Confirmar pedido", type="primary", use_container_width=True,
                                              disabled=not puede_pedir())
        if confirmar and not st.session_state.get("confirmando"):
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
                            avisos_n[it["sku"]] = "Sin stock disponible — se quitó del carrito"
                            continue
                        avisos_n[it["sku"]] = (f"Ajustado de {it['cantidad']} a {d} u. — "
                                               "es todo el stock disponible")
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
            except Exception as e:  # noqa: BLE001
                st.session_state.confirmando = False
                log.exception("Error confirmando pedido")
                st.error(f"No se pudo confirmar el pedido: {e}")
        if st.button("Vaciar carrito"):
            guardar_cart([])
            st.session_state.pop("stock_avisos", None)
            st.rerun()


# ---------------------------------------------------------------------------
# Mis pedidos
# ---------------------------------------------------------------------------
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
    items_df["foto"] = items_df["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    st.dataframe(items_df[["foto", "producto_cod", "producto_nombre", "color", "talle", "cantidad",
                           "precio_unit", "subtotal"]], hide_index=True, use_container_width=True,
                 column_config={"foto": st.column_config.ImageColumn("", width="small"),
                                "producto_cod": "Código", "producto_nombre": "Producto", "color": "Color",
                                "talle": "Talle", "cantidad": "Cant.",
                                "precio_unit": st.column_config.NumberColumn("Precio lista", format="$ %.0f"),
                                "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.0f")})
    b1, b2, _ = st.columns([1.1, 1.1, 2.6])
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
            if not avisos_rep:
                ir("carrito")
        else:
            st.error("Ninguna variante de ese pedido está disponible hoy.")
    try:
        data = pedidos.descargar_backup(p["xlsx_gcs_path"]) if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)
    except Exception:  # noqa: BLE001
        data = pedidos.generar_excel(p)
    b2.download_button("Descargar Excel", data=data, file_name=p["xlsx_filename"], use_container_width=True,
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


TIPO_INCIDENCIA = {"ok": "Agregada", "ajustada": "Ajustada", "no_encontrada": "No encontrada",
                   "sin_precio": "Sin precio", "ilegible": "Ilegible"}


def page_compra_rapida() -> None:
    st.markdown("## Compra rápida")
    if not puede_pedir():
        st.markdown("<p class='muted'>Tu usuario no tiene cliente asociado; no podés pedir.</p>",
                    unsafe_allow_html=True)
        return
    df = df_catalogo()
    df = df[df["precio"].notna()]
    tab_tabla, tab_pegar = st.tabs(["Tabla con miniaturas", "Pegar códigos"])

    with tab_tabla:
        c1, c2, c3 = st.columns([2, 1.2, 1.2])
        busq = c1.text_input("Buscar", key="cr_busq", placeholder="código, nombre, EAN, color")
        marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="cr_marca", placeholder="Todas")
        rubro = c3.multiselect("Rubro", sorted(df["rubro"].dropna().unique()), key="cr_rubro", placeholder="Todos")
        sub = catalog.filtrar_variantes(df, {"marca": marca, "rubro": rubro}, busq).copy()
        por_pag = 25
        n_pag = max(1, -(-len(sub) // por_pag))
        cpag, cinfo = st.columns([1, 3])
        pag = int(cpag.number_input("Página", 1, n_pag, 1, key="cr_pag"))
        cinfo.markdown(f"<p class='muted'>{len(sub)} variantes con stock y precio · página {pag}/{n_pag} · "
                       "cargá cantidades y tocá Agregar</p>", unsafe_allow_html=True)
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
        if st.button("Agregar al carrito", type="primary", disabled=not seleccion, key="cr_add"):
            items, ajustes = [], []
            for v, q in seleccion:
                q = min(q, int(v["stock"]))
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
            st.toast(f"{total} unidades agregadas al carrito")
            st.rerun()

    with tab_pegar:
        st.markdown("<p class='muted'>Una línea por variante: <code>SKU,cantidad</code> o "
                    "<code>EAN,cantidad</code> (coma, punto y coma, tab o espacio). "
                    "Podés pegar directo desde Excel.</p>", unsafe_allow_html=True)
        # Resultado del procesamiento anterior (post-rerun: contadores + reconciliación)
        if st.session_state.get("cr_resultado"):
            resumen, incidencias, total_u = st.session_state.pop("cr_resultado")
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
        with st.form("cr_pegar", border=False):
            texto = st.text_area("Códigos", height=170, placeholder="M211_U_2059,3\n7798218194446,2")
            ok = st.form_submit_button("Procesar y agregar", type="primary")
        if ok and texto.strip():
            items, incidencias = cr.resolver_pegado(texto, df)
            total = _agregar_items(items) if items else 0
            st.session_state.cr_resultado = (cr.resumen_incidencias(incidencias), incidencias, total)
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
    header()
    nav()
    page = st.session_state.get("page", "catalogo")
    {"catalogo": page_catalogo, "producto": page_producto, "carrito": page_carrito,
     "pedidos": page_pedidos, "compra_rapida": page_compra_rapida,
     "admin": page_admin}.get(page, page_catalogo)()
    footer()


main()
