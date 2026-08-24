"""Sección Administración (solo rol admin) — rediseño handoff Broadsheet.

Inicio (KPIs accionables) · Catálogo (click abre el editor; checkbox solo para
lote) · Editor de producto como PANTALLA (no modal) con override vs Aleph
explícito · Clientes · Pedidos (click en fila, tags de color) · Config.
SPECS.md §3-§6. Acá se editan SOLO overrides de Firestore; BQ es readonly.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import zoneinfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import auth
import catalog
import config as appconfig
import db
import email_notif
import fotos
import overrides
import pedidos

log = logging.getLogger(__name__)
TZ = zoneinfo.ZoneInfo(appconfig.TZ)

PUB_LABELS = {None: "Auto", True: "Publicado", False: "Oculto"}
PUB_OPCIONES = ["Automático", "Publicado", "Oculto"]
PUB_CAPTIONS = ["Visible si tiene stock (lo decide Aleph)",
                "Visible — igual exige stock > 0, nunca se vende sin stock",
                "Nunca visible para clientes"]
PUB_VALOR = {"Automático": None, "Publicado": True, "Oculto": False}
TAG_CLS = {"confirmado": "tag-conf", "procesado": "tag-proc", "cancelado": "tag-canc"}
SECCIONES = ["inicio", "catalogo", "clientes", "pedidos", "config"]


def _admin_email() -> str:
    return st.session_state.user["email"]


def _fmt(n) -> str:
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return f"$ {float(n):,.0f}".replace(",", ".")


def _tag(estado: str) -> str:
    return f"<span class='tag {TAG_CLS.get(estado, 'tag-proc')}'>{estado}</span>"


def page_admin() -> None:
    if st.session_state.get("adm_prod"):
        _editar_producto(st.session_state.adm_prod)
        return
    if st.session_state.get("adm_cliente"):
        _ficha_cliente(st.session_state.adm_cliente)
        return
    t1, t2 = st.columns([1, 2], vertical_alignment="bottom")
    t1.markdown("## Administración")
    t2.markdown("<p class='muted' style='text-align:right'>BigQuery es de solo lectura · "
                "lo que edites vive en Firestore y pisa a Aleph</p>", unsafe_allow_html=True)
    # Volver del editor debe caer en Catálogo (adm_nav es widget: si no se
    # renderizó en el run anterior, Streamlit lo resetea → lo fijamos acá).
    if "adm_nav_forzar" in st.session_state:
        st.session_state.adm_nav = st.session_state.pop("adm_nav_forzar")
    conteo = pedidos.contar_por_estado()
    sin_procesar = conteo.get("confirmado", 0)
    labels = {"inicio": "Inicio", "catalogo": "Catálogo", "clientes": "Clientes",
              "pedidos": "Pedidos" + (f" · {sin_procesar} sin procesar" if sin_procesar else ""),
              "config": "Config"}
    if "adm_nav" not in st.session_state:
        st.session_state.adm_nav = "inicio"
    sec = st.segmented_control("Sección", SECCIONES, format_func=lambda s: labels[s],
                               key="adm_nav", label_visibility="collapsed")
    st.markdown("")
    {"inicio": _sec_inicio, "catalogo": _sec_catalogo, "clientes": _sec_clientes,
     "pedidos": _sec_pedidos, "config": _sec_config}.get(sec or "inicio", _sec_inicio)()


# ---------------------------------------------------------------------------
# Inicio — KPIs
# ---------------------------------------------------------------------------
def _kpis(lista: list[dict], ahora: dt.datetime) -> dict:
    """KPIs puros a partir de la lista de pedidos (testeable sin GCP)."""
    mes = [p for p in lista if p.get("confirmed_at")
           and p["confirmed_at"].astimezone(TZ).strftime("%Y-%m") == ahora.astimezone(TZ).strftime("%Y-%m")
           and p.get("estado") != "cancelado"]
    top: dict[str, dict] = {}
    for p in mes:
        for it in p.get("items", []):
            t = top.setdefault(it["producto_cod"], {"nombre": it["producto_nombre"], "unidades": 0})
            t["unidades"] += int(it["cantidad"])
    return {
        "sin_procesar": sum(1 for p in lista if p.get("estado") == "confirmado"),
        "pedidos_mes": len(mes),
        "monto_mes": round(sum(float(p.get("total") or 0) for p in mes), 2),
        "unidades_mes": sum(int(p.get("unidades") or 0) for p in mes),
        "clientes_mes": len({p["cliente_cod"] for p in mes}),
        "top": sorted(([c, d["nombre"], d["unidades"]] for c, d in top.items()),
                      key=lambda x: -x[2])[:5],
    }


def _ir_catalogo_con_pill(pill: str) -> None:
    st.session_state.adm_nav = "catalogo"
    st.session_state.adm_pill = pill


def _sec_inicio() -> None:
    with st.spinner("Calculando..."):
        lista = pedidos.listar_pedidos(None)
        k = _kpis(lista, dt.datetime.now(dt.timezone.utc))
        df = catalog.variantes_admin()
    c = st.columns(5)
    c[0].metric("Sin procesar", k["sin_procesar"])
    c[1].metric("Pedidos del mes", k["pedidos_mes"])
    c[2].metric("Ventas del mes (sin IVA)", _fmt(k["monto_mes"]))
    c[3].metric("Unidades del mes", f"{k['unidades_mes']:,}".replace(",", "."))
    c[4].metric("Clientes que pidieron", k["clientes_mes"])
    if k["sin_procesar"]:
        c[0].button("Ver pedidos", key="kpi_ped", on_click=lambda: st.session_state.update(adm_nav="pedidos"))

    st.markdown("#### Salud del catálogo")
    prods = df.groupby("producto_cod").agg(publicado=("publicado", "first"), precio1=("precio1", "first")).reset_index()
    sin_foto = int((~prods["producto_cod"].map(fotos.tiene_fotos)).sum())
    ocultos = int(prods["publicado"].map(lambda v: v is False).sum())
    n_ov = len(overrides.get_catalogo_overrides())
    c = st.columns(5)
    c[0].metric("Productos con stock", len(prods))
    c[1].metric("Ocultos", ocultos)
    c[1].button("Ver", key="kpi_oc", on_click=_ir_catalogo_con_pill, args=("Ocultos",))
    c[2].metric("Sin foto", sin_foto)
    c[2].button("Ver", key="kpi_sf", on_click=_ir_catalogo_con_pill, args=("Sin foto",))
    c[3].metric("Sin precio L1", int((prods["precio1"] <= 0).sum()))
    c[4].metric("Con overrides", n_ov)
    c[4].button("Ver", key="kpi_ov", on_click=_ir_catalogo_con_pill, args=("Con override",))

    if k["top"]:
        st.markdown("#### Top productos del mes")
        st.dataframe(pd.DataFrame(k["top"], columns=["Código", "Producto", "Unidades"]),
                     hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Catálogo — click abre el editor; checkbox solo para lote (handoff 9 y 13)
# ---------------------------------------------------------------------------
def _sec_catalogo() -> None:
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()
    st.markdown("<p class='muted'>Abrí un producto con <b>Editar →</b> (o seleccionando la fila con el "
                "círculo de la izquierda). Activá «Selección múltiple» para las acciones en lote.</p>",
                unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns([2, 1.1, 1.1, 1.1, 1])
    busq = c1.text_input("Buscar", key="adm_busq", placeholder="código o nombre")
    marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="adm_marca", placeholder="Todas")
    temporada = c3.multiselect("Temporada", sorted(df["temporada"].dropna().unique()), key="adm_temp",
                               placeholder="Todas")
    rubro = c4.multiselect("Rubro", sorted(df["rubro"].dropna().unique()), key="adm_rubro", placeholder="Todos")
    multi = c5.toggle("Selección múltiple", key="adm_multi")
    sub = catalog.filtrar_variantes(df, {"marca": marca, "temporada": temporada, "rubro": rubro}, busq)

    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), marca=("marca", "first"), temporada=("temporada", "first"),
        rubro=("rubro", "first"), stock=("stock", "sum"), variantes=("sku", "count"),
        precio1=("precio1", "first"), publicado=("publicado", "first"), destacado=("destacado", "first"),
    ).reset_index()
    prods["sin_foto"] = ~prods["producto_cod"].map(fotos.tiene_fotos)
    prods["editado"] = prods["producto_cod"].map(lambda c: c in ov)

    counts = {
        "Todos": len(prods),
        "Publicados": int(prods["publicado"].map(lambda v: v is not False).sum()),
        "Ocultos": int(prods["publicado"].map(lambda v: v is False).sum()),
        "Destacados": int(prods["destacado"].sum()),
        "Sin foto": int(prods["sin_foto"].sum()),
        "Con override": int(prods["editado"].sum()),
    }
    if "adm_pill" not in st.session_state:
        st.session_state.adm_pill = "Todos"
    pill = st.pills("Filtro rápido", list(counts), key="adm_pill", label_visibility="collapsed",
                    format_func=lambda p: f"{p} ({counts[p]})") or "Todos"
    if pill == "Publicados":
        prods = prods[prods["publicado"].map(lambda v: v is not False)]
    elif pill == "Ocultos":
        prods = prods[prods["publicado"].map(lambda v: v is False)]
    elif pill == "Destacados":
        prods = prods[prods["destacado"]]
    elif pill == "Sin foto":
        prods = prods[prods["sin_foto"]]
    elif pill == "Con override":
        prods = prods[prods["editado"]]

    por_pag = 50
    n_pag = max(1, -(-len(prods) // por_pag))
    pag = min(st.session_state.get("adm_pag", 1), n_pag)
    page_df = prods.iloc[(pag - 1) * por_pag: pag * por_pag].copy()
    page_df["foto"] = page_df["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    page_df["pub"] = page_df["publicado"].map(PUB_LABELS.get)
    page_df["dest"] = page_df["destacado"].map(lambda v: "★" if v else "")
    page_df["ovr"] = page_df["editado"].map(lambda v: "editado" if v else "")
    page_df["editar"] = "?prod=" + page_df["producto_cod"]   # deep-link al editor (abre en otra pestaña)

    ver = st.session_state.get("adm_tabla_ver", 0)
    ev = st.dataframe(
        page_df[["foto", "producto_cod", "nombre", "marca", "temporada", "pub", "dest", "stock",
                 "variantes", "precio1", "ovr", "editar"]],
        hide_index=True, use_container_width=True, key=f"adm_tabla_{'m' if multi else 's'}_{ver}",
        on_select="rerun", selection_mode="multi-row" if multi else "single-row",
        column_config={
            "foto": st.column_config.ImageColumn("", width="small"),
            "producto_cod": "Código", "nombre": "Producto", "marca": "Marca", "temporada": "Temp.",
            "pub": "Publicación", "dest": "★", "ovr": "Override",
            "stock": st.column_config.NumberColumn("Stock", format="%d"),
            "variantes": st.column_config.NumberColumn("Var.", format="%d"),
            "precio1": st.column_config.NumberColumn("Precio L1", format="$ %.0f"),
            "editar": st.column_config.LinkColumn("", display_text="Editar →", width="small"),
        })
    sel_cods = [page_df.iloc[i]["producto_cod"] for i in ev.selection.rows]

    if not multi and sel_cods:
        # Click en el producto abre el editor (handoff 9)
        st.session_state.adm_prod = sel_cods[0]
        st.session_state.adm_tabla_ver = ver + 1
        st.rerun()

    if multi and sel_cods:
        with st.container(border=True, key="adm_lote"):
            b = st.columns([1.6, 0.9, 1, 1.2, 1, 1.4, 1.2])
            b[0].markdown(f"<b style='color:#006786'>{len(sel_cods)} producto(s) seleccionados</b>",
                          unsafe_allow_html=True)
            if b[1].button("Editar", disabled=len(sel_cods) != 1, use_container_width=True):
                st.session_state.adm_prod = sel_cods[0]
                st.session_state.adm_tabla_ver = ver + 1
                st.rerun()
            if b[2].button("Ocultar", use_container_width=True):
                _aplicar_lote(sel_cods, {"publicado": False})
            if b[3].button("Volver a automático", use_container_width=True):
                _aplicar_lote(sel_cods, {"publicado": None})
            if b[4].button("Destacar", use_container_width=True):
                _aplicar_lote(sel_cods, {"destacado": True})
            if b[5].button("Quitar destacado", use_container_width=True):
                _aplicar_lote(sel_cods, {"destacado": False})
            if b[6].button("Deseleccionar", use_container_width=True):
                st.session_state.adm_tabla_ver = ver + 1
                st.rerun()

    n1, n2, n3 = st.columns([4.4, 0.4, 0.4])
    n1.markdown(f"<div class='muted'>{len(prods)} productos · página {pag} de {n_pag}</div>",
                unsafe_allow_html=True)
    if n2.button("‹", key="adm_prev", disabled=pag <= 1):
        st.session_state.adm_pag = pag - 1
        st.rerun()
    if n3.button("›", key="adm_next", disabled=pag >= n_pag):
        st.session_state.adm_pag = pag + 1
        st.rerun()

    if multi:
        with st.expander("Acciones sobre TODO lo filtrado"):
            st.markdown(f"<p class='muted'>Afecta a los {len(prods)} productos del filtro actual "
                        "(todas las páginas).</p>", unsafe_allow_html=True)
            f1, f2 = st.columns(2)
            if f1.button("Ocultar todo lo filtrado", disabled=prods.empty):
                _aplicar_lote(list(prods["producto_cod"]), {"publicado": False})
            if f2.button("Todo lo filtrado a automático", disabled=prods.empty):
                _aplicar_lote(list(prods["producto_cod"]), {"publicado": None})


def _aplicar_lote(cods: list[str], campos: dict) -> None:
    if len(cods) > 10:
        _confirmar_lote(cods, campos)
        return
    for cod in cods:
        overrides.set_catalogo_override(cod, campos, _admin_email())
    st.toast(f"{len(cods)} producto(s) actualizados")
    st.session_state.adm_tabla_ver = st.session_state.get("adm_tabla_ver", 0) + 1
    st.rerun()


@st.dialog("Confirmar acción masiva")
def _confirmar_lote(cods: list[str], campos: dict) -> None:
    st.warning(f"Vas a aplicar **{campos}** a **{len(cods)} productos**. ¿Seguro?")
    c1, c2 = st.columns(2)
    if c1.button("Sí, aplicar", type="primary", use_container_width=True):
        for cod in cods:
            overrides.set_catalogo_override(cod, campos, _admin_email())
        st.toast(f"{len(cods)} producto(s) actualizados")
        st.session_state.adm_tabla_ver = st.session_state.get("adm_tabla_ver", 0) + 1
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------------------------
# Editor de producto como PANTALLA (handoff 10, 11, 12, 14)
# ---------------------------------------------------------------------------
def _editar_producto(cod: str) -> None:
    """Ficha de producto: modo VISTA (default) ↔ modo EDICIÓN (handoff fase 6, E2)."""
    if st.button("← Catálogo"):
        st.session_state.adm_prod = None
        st.session_state.adm_prod_edit = False
        st.session_state.adm_nav_forzar = "catalogo"
        st.rerun()
    # Al cambiar de producto siempre se entra en modo vista
    if st.session_state.get("adm_prod_edit_cod") != cod:
        st.session_state.adm_prod_edit = False
        st.session_state.adm_prod_edit_cod = cod
    editando = st.session_state.get("adm_prod_edit", False)

    df = catalog.variantes_admin()
    filas = df[df["producto_cod"] == cod].sort_values(["color", "talle"])
    if filas.empty:
        st.error("Producto sin stock neto hoy (no está en el catálogo actual).")
        return
    f0 = filas.iloc[0]
    o = overrides.get_catalogo_overrides().get(cod, {})
    raw = catalog.load_variantes()
    raw_p = raw[raw["producto_cod"] == cod]
    stock_bq = {r["sku"]: int(r["stock"]) for _, r in raw_p.iterrows()}

    t1, t2 = st.columns([3, 1], vertical_alignment="center")
    t1.markdown(f"## {f0['producto_nombre']}")
    if not editando and t2.button("Editar", type="primary", use_container_width=True):
        st.session_state.adm_prod_edit = True
        st.rerun()
    n_fotos = len(fotos.indice_fotos().get(cod.upper(), []))
    st.markdown(f"<div class='card-sub'>{cod} · {f0['marca'] or ''} · {f0['temporada'] or ''} · "
                f"{f0['rubro'] or ''} · {n_fotos} foto(s)"
                + (f" · overrides por {o.get('updated_by')}" if o.get("updated_by") else "")
                + "</div>", unsafe_allow_html=True)
    st.markdown("")

    if not editando:
        _producto_vista(cod, f0, filas, o, raw_p, stock_bq)
        return
    _producto_edicion(cod, f0, filas, o, raw_p, stock_bq)


def _producto_vista(cod, f0, filas, o, raw_p, stock_bq) -> None:
    """Solo lectura: qué trae Aleph, qué está pisado y cómo queda efectivo."""
    manual = "<span style='color:#006786'>(manual)</span>"
    ci, cd = st.columns([1, 2.6], gap="large")
    with ci:
        st.image(fotos.foto_principal(cod), use_container_width=True)
        pub = o.get("publicado") if o.get("publicado") in (True, False) else None
        regla = {None: "Automático — visible si tiene stock", True: "Publicado — visible, exige stock > 0",
                 False: "Oculto — nunca visible"}[pub]
        st.markdown(f"<div class='kicker'>Publicación</div>{regla} "
                    + (manual if pub is not None else "") + "<br>"
                    f"<div class='kicker' style='margin-top:.5rem'>Destacado</div>{'Sí' if o.get('destacado') else 'No'}<br>"
                    f"<div class='kicker' style='margin-top:.5rem'>Múltiplo (U.B.)</div>"
                    f"{o.get('ub') or 'Libre'}", unsafe_allow_html=True)
    with cd:
        st.markdown(f"<div class='kicker'>Nombre</div>{f0['producto_nombre']} "
                    + (manual if o.get("nombre") else "") + "<br>"
                    f"<div class='kicker' style='margin-top:.5rem'>Descripción</div>"
                    f"{(o.get('descripcion') or (raw_p.iloc[0].get('descripcion') if not raw_p.empty else '') or '—')} "
                    + (manual if o.get("descripcion") else ""), unsafe_allow_html=True)
        st.markdown("<div class='kicker' style='margin:.6rem 0 .2rem'>Precios por lista</div>", unsafe_allow_html=True)
        ov_p = o.get("precios") or {}
        pcols = st.columns(4)
        for i, n in enumerate((1, 2, 3, 4)):
            aleph = float(raw_p.iloc[0][f"precio{n}"]) if not raw_p.empty else 0
            efectivo = float(ov_p.get(str(n)) or aleph)
            origen = manual if ov_p.get(str(n)) else "<span class='muted'>Aleph</span>"
            pcols[i].markdown(f"<b>L{n}</b><br>{_fmt(efectivo) if efectivo > 0 else '—'}<br>{origen}",
                              unsafe_allow_html=True)

    st.markdown("<div class='kicker' style='margin:.8rem 0 .2rem'>Variantes (efectivo hoy)</div>",
                unsafe_allow_html=True)
    vov = o.get("variantes") or {}
    vdf = pd.DataFrame([{
        "SKU": r["sku"], "Color": r["color"], "Talle": r["talle"], "EAN": r["ean"],
        "Stock": int(r["stock"]), "Stock Aleph": stock_bq.get(r["sku"], 0),
        "Precio L1": float(r["precio1"]),
        "Overrides": " · ".join(filter(None, [
            "VARIANTE MANUAL" if r.get("es_manual") else "",
            "stock manual" if vov.get(r["sku"], {}).get("stock") is not None else "",
            "oculta" if vov.get(r["sku"], {}).get("oculta") else "",
            "precio manual" if vov.get(r["sku"], {}).get("precios") else "",
        ])),
    } for _, r in filas.iterrows()])
    st.dataframe(vdf, hide_index=True, use_container_width=True,
                 column_config={"Stock": st.column_config.NumberColumn(format="%d"),
                                "Stock Aleph": st.column_config.NumberColumn(format="%d"),
                                "Precio L1": st.column_config.NumberColumn(format="$ %.0f")})
    for sku, vo in vov.items():
        if vo.get("stock") is not None:
            st.markdown(f"<div class='aviso-stock'>{sku} tiene stock manual ({vo['stock']} u.) sobre un stock "
                        f"real de {stock_bq.get(sku, 0)} — el sitio no valida contra Aleph mientras dure.</div>",
                        unsafe_allow_html=True)


def _producto_edicion(cod, f0, filas, o, raw_p, stock_bq) -> None:
    ci, cd = st.columns([1, 2.6], gap="large")
    with ci:
        st.image(fotos.foto_principal(cod), use_container_width=True)
        pub_idx = {None: 0, True: 1, False: 2}[o.get("publicado") if o.get("publicado") in (True, False) else None]
        pub = st.radio("Publicación", PUB_OPCIONES, index=pub_idx, captions=PUB_CAPTIONS)
        dest = st.checkbox("Destacado (primero en el catálogo)", value=bool(o.get("destacado")))
        ub = st.number_input("Múltiplo de compra (U.B.)", min_value=0, step=1, value=int(o.get("ub") or 0),
                             help="Cantidad mínima y múltiplo por variante, como el u.b del Woo. 0 = libre")
    with cd:
        nombre = st.text_input("Nombre", value=o.get("nombre") or "", placeholder=str(f0["producto_nombre"]))
        st.markdown(f"<p class='muted' style='margin-top:-0.6rem'>Aleph: {raw_p.iloc[0]['producto_nombre']}"
                    " · vacío = usa Aleph</p>", unsafe_allow_html=True)
        descr = st.text_area("Descripción", value=o.get("descripcion") or "", height=70,
                             placeholder=str(raw_p.iloc[0].get("descripcion") or "—"))
        st.markdown("<div class='kicker' style='margin:.4rem 0 .2rem'>Precios por lista — "
                    "manual pisa a Aleph solo en esa lista</div>", unsafe_allow_html=True)
        precios = {}
        for n in (1, 2, 3, 4):
            aleph = float(raw_p.iloc[0][f"precio{n}"]) if not raw_p.empty else 0
            pc = st.columns([0.9, 1.1, 2], vertical_alignment="center")
            pc[0].markdown(f"<b>Lista {n}</b><br><span class='muted'>Aleph: {_fmt(aleph) if aleph > 0 else '—'}</span>",
                           unsafe_allow_html=True)
            actual = (o.get("precios") or {}).get(str(n))
            val = pc[1].number_input(f"Manual L{n}", min_value=0.0, step=100.0,
                                     value=float(actual) if actual else None,
                                     placeholder="usa Aleph", key=f"pe_{cod}_{n}",
                                     label_visibility="collapsed")
            precios[str(n)] = val
            if val and val > 0:
                pc[2].markdown(f"<span style='color:#006786'>Manual — pisa a Aleph para la lista {n}</span>",
                               unsafe_allow_html=True)
            else:
                pc[2].markdown("<span class='muted'>Usa Aleph</span>", unsafe_allow_html=True)

    st.markdown("<div class='kicker' style='margin:.8rem 0 .2rem'>Variantes — stock y precio manual "
                "pisan a Aleph (vacío = automático)</div>", unsafe_allow_html=True)
    vov = o.get("variantes") or {}
    vdf = pd.DataFrame([{
        "sku": r["sku"], "color": r["color"], "talle": r["talle"], "ean": r["ean"],
        "stock_aleph": stock_bq.get(r["sku"], 0),
        "stock_manual": (vov.get(r["sku"], {}).get("stock") if vov.get(r["sku"], {}).get("stock") is not None else None),
        "oculta": bool(vov.get(r["sku"], {}).get("oculta")),
        "precio_manual_l1": (vov.get(r["sku"], {}).get("precios", {}) or {}).get("1"),
    } for _, r in filas.iterrows()])
    ed = st.data_editor(
        vdf, hide_index=True, use_container_width=True, key=f"adm_var_{cod}",
        disabled=["sku", "color", "talle", "ean", "stock_aleph"],
        column_config={
            "sku": "SKU", "color": "Color", "talle": "Talle", "ean": "EAN",
            "stock_aleph": st.column_config.NumberColumn("Stock Aleph", format="%d"),
            "stock_manual": st.column_config.NumberColumn("Stock manual", min_value=0, step=1),
            "oculta": st.column_config.CheckboxColumn("Oculta"),
            "precio_manual_l1": st.column_config.NumberColumn("Precio manual L1", min_value=0.0, step=100.0,
                                                              format="$ %.0f"),
        })
    for _, r in ed.iterrows():
        if pd.notna(r["stock_manual"]):
            real = stock_bq.get(r["sku"], 0)
            st.markdown(f"<div class='aviso-stock'>{r['sku']} tiene stock manual "
                        f"({int(r['stock_manual'])} u.) sobre un stock real de {real}. Mientras esté en "
                        "manual, el sitio deja de validar contra Aleph y puede vender de más.</div>",
                        unsafe_allow_html=True)

    # --- Variantes MANUALES fuera de Aleph (fase 6, E4) ---
    extras = o.get("variantes_extra") or {}
    st.markdown("<div class='kicker' style='margin:.8rem 0 .2rem'>Variantes manuales — no existen en "
                "Aleph; stock y precio son 100% tuyos y el Excel las marca</div>", unsafe_allow_html=True)
    if extras:
        xdf = pd.DataFrame([{"sku": sku, "color": vo.get("color", ""), "talle": vo.get("talle", ""),
                             "stock": int(vo.get("stock") or 0),
                             "precio_l1": float((vo.get("precios") or {}).get("1") or 0),
                             "ean": vo.get("ean", ""), "eliminar": False}
                            for sku, vo in sorted(extras.items())])
        xed = st.data_editor(xdf, hide_index=True, use_container_width=True, key=f"adm_extra_{cod}",
                             disabled=["sku", "color", "talle"],
                             column_config={
                                 "sku": "SKU", "color": "Color", "talle": "Talle",
                                 "stock": st.column_config.NumberColumn("Stock", min_value=0, step=1),
                                 "precio_l1": st.column_config.NumberColumn("Precio L1", min_value=0.0,
                                                                            step=100.0, format="$ %.0f"),
                                 "ean": "EAN", "eliminar": st.column_config.CheckboxColumn("Eliminar"),
                             })
    else:
        xed = None
        st.markdown("<p class='muted'>Este producto no tiene variantes manuales.</p>", unsafe_allow_html=True)
    with st.form(f"extra_{cod}", border=False):
        a = st.columns([1.2, 0.8, 0.8, 1, 1.2, 1.2])
        x_color = a[0].text_input("Color nuevo")
        x_talle = a[1].text_input("Talle", value="U")
        x_stock = a[2].number_input("Stock", min_value=0, step=1, value=0)
        x_precio = a[3].number_input("Precio L1", min_value=0.0, step=100.0, value=0.0)
        x_ean = a[4].text_input("EAN (opcional)")
        if a[5].form_submit_button("Agregar variante manual", use_container_width=True):
            if not x_color.strip() or x_stock <= 0 or x_precio <= 0:
                st.error("Color, stock > 0 y precio L1 > 0 son obligatorios para una variante manual.")
            else:
                import re as _re
                talle_n = x_talle.strip().upper().replace(" ", "") or "U"
                slug = _re.sub(r"[^A-Z0-9]", "", x_color.strip().upper())[:12] or "MANUAL"
                sku_n = f"{cod}_{talle_n}_X{slug}"
                nuevos = dict(extras)
                nuevos[sku_n] = {"color": x_color.strip().upper(), "talle": talle_n,
                                 "stock": int(x_stock), "precios": {"1": float(x_precio)},
                                 "ean": x_ean.strip()}
                overrides.set_catalogo_override(cod, {"variantes_extra": nuevos}, _admin_email())
                st.toast(f"Variante manual {sku_n} agregada")
                st.rerun()

    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:1rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    g1, g2, g3, _ = st.columns([1, 1, 1.3, 2])
    if g1.button("Guardar", type="primary", use_container_width=True):
        variantes = {}
        for _, r in ed.iterrows():
            v = {}
            if pd.notna(r["stock_manual"]):
                v["stock"] = int(r["stock_manual"])
            if bool(r["oculta"]):
                v["oculta"] = True
            if pd.notna(r["precio_manual_l1"]) and float(r["precio_manual_l1"]) > 0:
                v["precios"] = {"1": float(r["precio_manual_l1"])}
            if v:
                variantes[r["sku"]] = v
        campos = {
            "nombre": nombre.strip() or None, "descripcion": descr.strip() or None,
            "precios": {k: float(v) for k, v in precios.items() if v and v > 0},
            "publicado": PUB_VALOR[pub], "destacado": bool(dest),
            "ub": int(ub) or None, "variantes": variantes,
        }
        if xed is not None:   # ediciones/bajas de variantes manuales
            campos["variantes_extra"] = {
                r["sku"]: {"color": r["color"], "talle": r["talle"], "stock": int(r["stock"] or 0),
                           "precios": {"1": float(r["precio_l1"] or 0)}, "ean": str(r["ean"] or "")}
                for _, r in xed.iterrows() if not bool(r["eliminar"])}
        overrides.set_catalogo_override(cod, campos, _admin_email())
        st.session_state.adm_prod_edit = False   # guardar vuelve a modo vista
        st.toast(f"{cod} guardado")
        st.rerun()
    if g2.button("Descartar", use_container_width=True):
        st.session_state.adm_prod_edit = False
        st.rerun()
    if g3.button("Quitar TODOS los overrides", use_container_width=True):
        overrides.quitar_catalogo_override(cod)
        st.session_state.adm_prod_edit = False
        st.toast(f"{cod} volvió 100% a Aleph")
        st.rerun()


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
def _listar_usuarios() -> list[dict]:
    out = []
    for snap in db.client().collection(db.COL_USUARIOS).stream():
        d = snap.to_dict() or {}
        d["email"] = snap.id
        out.append(d)
    return sorted(out, key=lambda u: u["email"])


def _metricas_cliente(lista: list[dict]) -> dict:
    """Métricas puras del historial de UN cliente (testeable sin GCP)."""
    activos = [p for p in lista if p.get("estado") != "cancelado"]
    total = round(sum(float(p.get("total") or 0) for p in activos), 2)
    top: dict[str, dict] = {}
    for p in activos:
        for it in p.get("items", []):
            t = top.setdefault(it["producto_cod"], {"nombre": it["producto_nombre"], "unidades": 0})
            t["unidades"] += int(it["cantidad"])
    ultimo = max(activos, key=lambda p: p.get("confirmed_at"), default=None)
    return {
        "pedidos": len(activos),
        "cancelados": sum(1 for p in lista if p.get("estado") == "cancelado"),
        "sin_procesar": sum(1 for p in lista if p.get("estado") == "confirmado"),
        "unidades": sum(int(p.get("unidades") or 0) for p in activos),
        "total": total,
        "ticket": round(total / len(activos), 2) if activos else 0.0,
        "ultimo": ultimo.get("fecha_str") if ultimo else "—",
        "top": sorted(([c, d["nombre"], d["unidades"]] for c, d in top.items()),
                      key=lambda x: -x[2])[:5],
    }


def _sec_clientes() -> None:
    usuarios = _listar_usuarios()
    cods = sorted({int(u["cliente_cod"]) for u in usuarios if u.get("cliente_cod") is not None})
    with st.spinner("Leyendo clientes..."):
        efectivos = catalog.get_clientes(cods)
    st.markdown("<p class='muted'>Click en un cliente para ver su ficha (pedidos, métricas y edición).</p>",
                unsafe_allow_html=True)
    rows = []
    for u in usuarios:
        cod = u.get("cliente_cod")
        e = efectivos.get(int(cod)) if cod is not None else None
        rows.append({
            "Email": u["email"], "Rol": u.get("rol", "cliente"),
            "Activo": "sí" if u.get("activo", True) else "no",
            "Cliente": cod, "Nombre": (e or {}).get("nombre_display", u.get("nombre_display", "")),
            "Lista": f"{e['lista_precios']} ({e['lista_origen']})" if e else "—",
            "Desc %": f"{e['descuento']:g} ({e['descuento_origen']})" if e else "—",
            "Último login": (u.get("last_login_at").astimezone(TZ).strftime("%d/%m %H:%M")
                             if u.get("last_login_at") else "—"),
        })
    ver = st.session_state.get("adm_cli_ver", 0)
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                      key=f"adm_cli_tabla_{ver}", on_select="rerun", selection_mode="single-row")
    if ev.selection.rows:
        st.session_state.adm_cliente = usuarios[ev.selection.rows[0]]["email"]
        st.session_state.adm_cli_ver = ver + 1
        st.rerun()
    if st.button("Nuevo usuario"):
        _alta_usuario()
    if st.session_state.get("adm_pwd_msg"):
        e, p = st.session_state.pop("adm_pwd_msg")
        st.success(f"Password de **{e}**: `{p}` — guardala ahora (también quedó en el secret "
                   "`mayorista-seed-passwords`).")


def _ficha_cliente(email: str) -> None:
    """Ficha de cliente: VISTA (datos + métricas + pedidos) ↔ EDICIÓN (fase 6, E1)."""
    if st.button("← Clientes"):
        st.session_state.adm_cliente = None
        st.session_state.adm_cli_edit = False
        st.session_state.adm_nav_forzar = "clientes"
        st.rerun()
    if st.session_state.get("adm_cli_edit_for") != email:
        st.session_state.adm_cli_edit = False
        st.session_state.adm_cli_edit_for = email
    editando = st.session_state.get("adm_cli_edit", False)

    u = auth.get_usuario(email)
    if not u:
        st.error("Usuario no encontrado")
        return
    cod = u.get("cliente_cod")
    e = catalog.get_cliente(int(cod)) if cod is not None else None

    t1, t2 = st.columns([3, 1], vertical_alignment="center")
    t1.markdown(f"## {(e or {}).get('nombre_display', u.get('nombre_display', email))}")
    if not editando and t2.button("Editar", type="primary", use_container_width=True):
        st.session_state.adm_cli_edit = True
        st.rerun()
    st.markdown(f"<div class='card-sub'>{email} · rol {u.get('rol', 'cliente')} · "
                f"{'activo' if u.get('activo', True) else 'DESACTIVADO'}"
                + (f" · cliente {cod}" if cod is not None else " · sin cliente asociado")
                + "</div>", unsafe_allow_html=True)
    st.markdown("")

    if st.session_state.get("adm_pwd_msg"):
        em, pw = st.session_state.pop("adm_pwd_msg")
        st.success(f"Password de **{em}**: `{pw}` — guardala ahora (también quedó en el secret "
                   "`mayorista-seed-passwords`).")

    if editando:
        _cliente_edicion(email, u, cod, e)
        return

    # ---- VISTA ----
    if e:
        d = st.columns(4)
        d[0].markdown(f"<div class='kicker'>Lista de precios</div>{e['lista_precios']} "
                      f"<span class='muted'>({e['lista_origen']})</span>", unsafe_allow_html=True)
        d[1].markdown(f"<div class='kicker'>Descuento cabecera</div>{e['descuento']:g}% "
                      f"<span class='muted'>({e['descuento_origen']})</span>", unsafe_allow_html=True)
        d[2].markdown(f"<div class='kicker'>CUIT</div>{e.get('cuit') or '—'}", unsafe_allow_html=True)
        d[3].markdown(f"<div class='kicker'>Ubicación</div>{e.get('localidad') or '—'} · "
                      f"{e.get('provincia_desc') or ''}", unsafe_allow_html=True)
        if e.get("notas"):
            st.markdown(f"<p class='muted'>Notas: {e['notas']}</p>", unsafe_allow_html=True)

    if cod is None:
        st.markdown("<p class='muted'>Usuario administrador, sin historial de pedidos.</p>",
                    unsafe_allow_html=True)
        return

    with st.spinner("Buscando pedidos del cliente..."):
        lista = pedidos.listar_pedidos(int(cod))
    m = _metricas_cliente(lista)
    st.markdown("<div class='kicker' style='margin:.8rem 0 .2rem'>Métricas</div>", unsafe_allow_html=True)
    c = st.columns(6)
    c[0].metric("Pedidos", m["pedidos"])
    c[1].metric("Unidades", f"{m['unidades']:,}".replace(",", "."))
    c[2].metric("Total histórico", _fmt(m["total"]))
    c[3].metric("Ticket promedio", _fmt(m["ticket"]))
    c[4].metric("Último pedido", m["ultimo"])
    c[5].metric("Cancelados", m["cancelados"])
    if m["top"]:
        st.markdown("<div class='kicker' style='margin:.6rem 0 .2rem'>Top productos</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(m["top"], columns=["Código", "Producto", "Unidades"]),
                     hide_index=True, use_container_width=True)

    st.markdown("<div class='kicker' style='margin:.8rem 0 .2rem'>Pedidos</div>", unsafe_allow_html=True)
    if not lista:
        st.markdown("<p class='muted'>Sin pedidos todavía.</p>", unsafe_allow_html=True)
        return
    tabla = pd.DataFrame([{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""), "Unidades": p["unidades"],
        "Total": p["total"], "Estado": p["estado"],
    } for p in lista])
    ev = st.dataframe(tabla, hide_index=True, use_container_width=True, key=f"cli_ped_{cod}",
                      on_select="rerun", selection_mode="single-row",
                      column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})
    if ev.selection.rows:
        _detalle_pedido(lista[ev.selection.rows[0]])
    else:
        st.markdown("<p class='muted'>Click en un pedido para ver el detalle.</p>", unsafe_allow_html=True)


def _cliente_edicion(email: str, u: dict, cod, e) -> None:
    if cod is not None:
        o = overrides.get_clientes_overrides().get(int(cod), {})
        with st.form(f"cli_{cod}"):
            usar_desc = st.checkbox("Override de descuento", value=o.get("descuento_pct") is not None)
            desc = st.number_input("Descuento %", 0.0, 100.0,
                                   float(o.get("descuento_pct") or (e or {}).get("descuento") or 0), step=0.5)
            usar_lista = st.checkbox("Override de lista", value=bool(o.get("lista_precios")))
            lista = st.number_input("Lista de precios", 1, 10,
                                    int(o.get("lista_precios") or (e or {}).get("lista_precios") or 1))
            notas = st.text_input("Notas", value=o.get("notas") or "")
            g1, g2 = st.columns(2)
            if g1.form_submit_button("Guardar", type="primary", use_container_width=True):
                overrides.set_cliente_override(int(cod), {
                    "descuento_pct": float(desc) if usar_desc else None,
                    "lista_precios": int(lista) if usar_lista else None,
                    "notas": notas.strip(),
                }, _admin_email())
                st.session_state.adm_cli_edit = False
                st.toast("Cliente guardado")
                st.rerun()
            if g2.form_submit_button("Descartar", use_container_width=True):
                st.session_state.adm_cli_edit = False
                st.rerun()
    else:
        st.markdown("<p class='muted'>Usuario sin cliente asociado: solo cuenta.</p>", unsafe_allow_html=True)
        if st.button("Volver a la vista"):
            st.session_state.adm_cli_edit = False
            st.rerun()
    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:.8rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    b1, b2, _ = st.columns([1.1, 1.1, 2])
    if b1.button("Resetear password", use_container_width=True):
        pwd = auth.generar_password()
        auth.cambiar_password(email, pwd)
        auth.guardar_password_en_secret(email, pwd)
        st.session_state.adm_pwd_msg = (email, pwd)
        st.session_state.adm_cli_edit = False
        st.rerun()
    if b2.button("Desactivar usuario" if u.get("activo", True) else "Activar usuario", use_container_width=True):
        db.usuario_ref(email).update({"activo": not u.get("activo", True)})
        st.rerun()


@st.dialog("Nuevo usuario")
def _alta_usuario() -> None:
    with st.form("alta_usuario", clear_on_submit=True):
        email = st.text_input("Email")
        cod = st.number_input("cliente_cod (0 = sin cliente, admin)", min_value=0, step=1, value=0)
        nombre = st.text_input("Nombre para mostrar (vacío = razón social de Aleph)")
        rol = st.selectbox("Rol", ["cliente", "admin"])
        if st.form_submit_button("Crear usuario", type="primary", use_container_width=True):
            try:
                if cod:
                    cli = catalog.get_cliente(int(cod))
                    if cli is None:
                        raise ValueError(f"cliente_cod {cod} no existe en dim_cliente")
                    nombre = nombre or cli["nombre_display"]
                pwd = auth.generar_password()
                auth.crear_usuario(email, pwd, int(cod) or None, nombre or email, rol=rol)
                auth.guardar_password_en_secret(email, pwd)
                st.session_state.adm_pwd_msg = (email.strip().lower(), pwd)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(str(e))


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
def _sec_pedidos() -> None:
    with st.spinner("Buscando pedidos..."):
        lista = pedidos.listar_pedidos(None)
    if not lista:
        st.markdown("<p class='muted'>No hay pedidos todavía.</p>", unsafe_allow_html=True)
        return
    counts = {"Todos": len(lista)}
    for e in ("confirmado", "procesado", "cancelado"):
        n = sum(1 for p in lista if p["estado"] == e)
        if n:
            counts[e.capitalize()] = n
    pill = st.pills("Estado", list(counts), key="adm_ped_pill", label_visibility="collapsed",
                    format_func=lambda p: f"{p} ({counts[p]})", default="Todos") or "Todos"
    c1, c2 = st.columns([2, 1])
    clientes = c1.multiselect("Cliente", sorted({f"{p['cliente_cod']} · {p['cliente_nombre']}" for p in lista}),
                              key="adm_ped_cli", placeholder="Todos")
    desde = c2.date_input("Desde", value=None, key="adm_ped_desde")
    filt = [p for p in lista
            if (pill == "Todos" or p["estado"] == pill.lower())
            and (not clientes or f"{p['cliente_cod']} · {p['cliente_nombre']}" in clientes)
            and (not desde or p["confirmed_at"].astimezone(TZ).date() >= desde)]
    tabla = pd.DataFrame([{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""),
        "Cliente": f"{p['cliente_cod']} · {p['cliente_nombre'][:40]}",
        "Unidades": p["unidades"], "Total": p["total"], "Estado": p["estado"],
        "Email": "sí" if (p.get("email") or {}).get("enviado") else "—",
    } for p in filt])
    ev = st.dataframe(tabla, hide_index=True, use_container_width=True, key="adm_ped_tabla",
                      on_select="rerun", selection_mode="single-row",
                      column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})
    if not ev.selection.rows:
        st.markdown("<p class='muted'>Click en una fila para ver el detalle.</p>", unsafe_allow_html=True)
        return
    p = filt[ev.selection.rows[0]]
    _detalle_pedido(p)


def _detalle_pedido(p: dict) -> None:
    """Detalle + acciones de un pedido (usado en Pedidos y en la ficha de cliente)."""
    st.markdown(f"### Pedido N° {p['numero']} &nbsp; {_tag(p['estado'])}", unsafe_allow_html=True)
    st.markdown(f"<p class='muted'>{p['fecha_str']} · <b>{p['cliente_nombre']}</b> (cliente {p['cliente_cod']}) · "
                f"{p['usuario_email']} · {p['unidades']} u. · <b>{_fmt(p['total'])}</b> "
                f"(desc. {p['descuento_pct']:g}%)</p>", unsafe_allow_html=True)
    if p.get("observaciones"):
        st.markdown(f"<p class='muted'>Obs: {p['observaciones']}</p>", unsafe_allow_html=True)
    for h in p.get("historial", []):
        st.markdown(f"<p class='muted'>{h['en'].astimezone(TZ):%d/%m %H:%M} — <b>{h['estado']}</b> "
                    f"por {h['por']}</p>", unsafe_allow_html=True)

    items = pd.DataFrame(p["items"])
    items["foto"] = items["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    st.dataframe(items[["foto", "producto_cod", "producto_nombre", "color", "talle", "cantidad",
                        "precio_unit", "subtotal"]],
                 hide_index=True, use_container_width=True,
                 column_config={"foto": st.column_config.ImageColumn("", width="small"),
                                "precio_unit": st.column_config.NumberColumn("Precio", format="$ %.0f"),
                                "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.0f")})
    cols = st.columns(4)
    for i, nuevo in enumerate(pedidos.ESTADOS_SIGUIENTES.get(p["estado"], [])):
        if cols[i].button(f"Marcar {nuevo}", key=f"est_{p['numero']}_{nuevo}",
                          type="primary" if nuevo == "procesado" else "secondary", use_container_width=True):
            pedidos.cambiar_estado(p["numero"], nuevo, _admin_email())
            st.toast(f"Pedido {p['numero']} → {nuevo}")
            st.rerun()
    if cols[2].button("Reenviar email", key=f"mail_{p['numero']}", use_container_width=True):
        try:
            data = pedidos.descargar_backup(p["xlsx_gcs_path"]) if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)
            res = email_notif.enviar_confirmacion(p, data, p["xlsx_filename"])
            st.success(f"Reenviado a {', '.join(res['destinatarios'])}") if res["enviado"] else st.error(res["error"])
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    cols[3].download_button("Excel", data=(pedidos.descargar_backup(p["xlsx_gcs_path"])
                                           if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)),
                            file_name=p["xlsx_filename"], key=f"dl_{p['numero']}", use_container_width=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _sec_config() -> None:
    cfg = overrides.get_config()
    with st.form("config_global"):
        email_to = st.text_input("Email(s) de Lautin que reciben pedidos (coma; vacío = default del deploy)",
                                 value=cfg.get("pedidos_email_to") or "")
        banner = st.text_area("Banner para clientes (vacío = no se muestra)", value=cfg.get("banner_texto") or "",
                              height=80)
        c1, c2, c3 = st.columns(3)
        descvta = c1.checkbox("Aplicar descvta de Aleph (como el Woo)", value=bool(cfg.get("aplicar_descvta")))
        notificar = c1.checkbox("Email al cliente y a Lautin al cambiar el estado de un pedido",
                                value=bool(cfg.get("notificar_estados", True)))
        minimo = c2.number_input("Mínimo de unidades por pedido (0 = sin mínimo)", min_value=0, step=1,
                                 value=int(cfg.get("minimo_pedido_unidades") or 0))
        iva = c3.number_input("IVA % informativo (0 = ocultar)", min_value=0.0, max_value=30.0, step=0.5,
                              value=float(cfg.get("iva_pct") or 0),
                              help="Las listas de Aleph son sin IVA. Se muestra como línea aparte.")
        if st.form_submit_button("Guardar configuración", type="primary"):
            overrides.set_config({
                "pedidos_email_to": email_to.strip() or None,
                "banner_texto": banner.strip(),
                "aplicar_descvta": bool(descvta),
                "minimo_pedido_unidades": int(minimo) or None,
                "iva_pct": float(iva),
                "notificar_estados": bool(notificar),
            }, _admin_email())
            st.toast("Configuración guardada")
            st.rerun()
    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:.8rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    if st.button("Actualizar catálogo ahora (BQ + fotos)"):
        with st.spinner("Refrescando catálogo e índice de fotos..."):
            catalog.load_variantes(force=True)
            fotos.indice_fotos(force=True)
            overrides.invalidar()
        st.toast("Catálogo actualizado")
    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:1rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    st.markdown("#### Emails")
    _config_emails()
    if appconfig.EMAIL_OVERRIDE_TO:
        st.markdown(f"<p class='muted'>DEV: todos los emails se redirigen a {appconfig.EMAIL_OVERRIDE_TO}.</p>",
                    unsafe_allow_html=True)


def _pedido_ejemplo() -> dict:
    """Un pedido real para el preview (el último), o uno sintético."""
    try:
        lista = pedidos.listar_pedidos(None, limit=1)
        if lista:
            return lista[0]
    except Exception:  # noqa: BLE001
        pass
    return {"numero": 999, "cliente_nombre": "CLIENTE DE EJEMPLO S.A.", "cliente_cod": 1234,
            "usuario_email": "cliente@ejemplo.com", "fecha_str": "24/08/2026", "unidades": 12,
            "lista_precios": 1, "subtotal": 120000.0, "descuento_pct": 20.0, "descuento_monto": 24000.0,
            "total": 96000.0, "iva_pct": 21.0, "iva_monto": 20160.0, "total_con_iva": 116160.0,
            "observaciones": "Pedido de ejemplo", "estado": "confirmado",
            "items": [{"producto_cod": "M211", "producto_nombre": "Mochila Soft Rainbow", "color": "AQUA",
                       "talle": "U", "cantidad": 12, "precio_unit": 10000.0, "subtotal": 120000.0}]}


EVENTO_LABEL = {"confirmacion": "Pedido realizado (lleva el Excel adjunto)",
                "procesado": "Pedido procesado por Lautin",
                "cancelado": "Pedido cancelado"}


def _config_emails() -> None:
    evento = st.selectbox("Evento", list(email_notif.EVENTOS), format_func=EVENTO_LABEL.get, key="em_evento")
    tpl = email_notif.template_de(evento)
    c1, c2 = st.columns([1, 3])
    formato = c1.radio("Formato", ["texto", "html"], index=0 if tpl.get("formato") != "html" else 1,
                       key=f"em_fmt_{evento}", horizontal=True)
    asunto = c2.text_input("Asunto", value=tpl["asunto"], key=f"em_asu_{evento}")
    cuerpo = st.text_area("Cuerpo", value=tpl["cuerpo"], height=220, key=f"em_cue_{evento}")
    st.markdown("<p class='muted'>Variables: {numero} {cliente} {cliente_cod} {usuario} {fecha} {unidades} "
                "{subtotal} {descuento_pct} {descuento_monto} {total} {iva_pct} {iva_monto} {total_con_iva} "
                "{lineas_iva} {lista_precios} {observaciones} {detalle} {quien} {estado} — una variable "
                "desconocida queda escrita tal cual, no rompe el envío.</p>", unsafe_allow_html=True)

    ejemplo = _pedido_ejemplo()
    vs = email_notif._SafeDict(email_notif.variables_pedido(ejemplo, _admin_email()))
    st.markdown(f"<div class='kicker' style='margin:.4rem 0 .2rem'>Preview — con el pedido "
                f"N° {ejemplo['numero']} de {ejemplo['cliente_nombre']}</div>", unsafe_allow_html=True)
    st.markdown(f"<b>Asunto:</b> {asunto.format_map(vs)}", unsafe_allow_html=True)
    if formato == "html":
        components.html(cuerpo.format_map(vs), height=320, scrolling=True)
    else:
        st.code(cuerpo.format_map(vs), language=None)

    b1, b2, b3, _ = st.columns([1, 1.6, 1.3, 1.4])
    if b1.button("Guardar template", type="primary", use_container_width=True):
        overrides.set_email_template(evento, {"formato": formato, "asunto": asunto.strip(),
                                              "cuerpo": cuerpo}, _admin_email())
        st.toast(f"Template '{EVENTO_LABEL[evento]}' guardado")
        st.rerun()
    if b2.button("Guardar y enviarme una prueba", use_container_width=True):
        overrides.set_email_template(evento, {"formato": formato, "asunto": asunto.strip(),
                                              "cuerpo": cuerpo}, _admin_email())
        res = email_notif.enviar_prueba(evento, ejemplo, _admin_email())
        if res["enviado"]:
            st.success(f"Prueba enviada a {', '.join(res['destinatarios'])}")
        else:
            st.error(f"No se pudo enviar: {res['error']}")
    if b3.button("Restaurar default", use_container_width=True):
        overrides.reset_email_template(evento, _admin_email())
        for k in (f"em_fmt_{evento}", f"em_asu_{evento}", f"em_cue_{evento}"):
            st.session_state.pop(k, None)
        st.toast("Template restaurado al default")
        st.rerun()
