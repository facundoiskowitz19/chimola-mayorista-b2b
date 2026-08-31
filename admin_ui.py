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

import aleph_import
import auth
import catalog
import reposicion
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


def _fmt_compacto(n) -> str:
    """$ abreviado para métricas (handoff v2 §D): $ 18,4 M en vez de $ 18.400.000."""
    n = float(n or 0)
    if abs(n) >= 1_000_000:
        return f"$ {n / 1_000_000:.1f} M".replace(".", ",")
    return _fmt(n)


def _tag(estado: str) -> str:
    return f"<span class='tag {TAG_CLS.get(estado, 'tag-proc')}'>{estado}</span>"


def _adm_nav_click() -> None:
    """Cambiar de pestaña sale de una ficha abierta (handoff v2 A2). Click en
    la pestaña ya activa la deselecciona → volvemos a esa misma sección."""
    if st.session_state.get("adm_nav") is None:
        st.session_state.adm_nav = st.session_state.get("adm_nav_ultima") or "inicio"
    st.session_state.adm_prod = None
    st.session_state.adm_cliente = None
    st.session_state.pop("adm_prod_edit", None)
    st.session_state.pop("adm_cli_edit", None)


def page_admin() -> None:
    # El nav se renderiza SIEMPRE (handoff v2 A2): en una ficha de producto
    # marca Catálogo; en una de cliente, Clientes. Volver del editor debe caer
    # en Catálogo (adm_nav es widget: si no se renderizó en el run anterior,
    # Streamlit lo resetea → lo fijamos acá con adm_nav_forzar).
    if "adm_nav_forzar" in st.session_state:
        st.session_state.adm_nav = st.session_state.pop("adm_nav_forzar")
    prod = st.session_state.get("adm_prod")
    cli = st.session_state.get("adm_cliente")
    if prod:
        st.session_state.adm_nav = "catalogo"
    elif cli:
        st.session_state.adm_nav = "clientes"
    if "adm_nav" not in st.session_state:
        st.session_state.adm_nav = "inicio"
    if not (prod or cli):
        t1, t2 = st.columns([1, 2], vertical_alignment="bottom")
        t1.markdown("## Administración")
        t2.markdown("<p class='muted' style='text-align:right'>BigQuery es de solo lectura · "
                    "lo que edites vive en Firestore y pisa a Aleph</p>", unsafe_allow_html=True)
    conteo = pedidos.contar_por_estado()
    sin_procesar = conteo.get("confirmado", 0)
    labels = {"inicio": "Inicio", "catalogo": "Catálogo", "clientes": "Clientes",
              "pedidos": "Pedidos" + (f" · {sin_procesar} sin procesar" if sin_procesar else ""),
              "config": "Config"}
    sec = st.segmented_control("Sección", SECCIONES, format_func=lambda s: labels[s],
                               key="adm_nav", label_visibility="collapsed",
                               on_change=_adm_nav_click)
    st.session_state.adm_nav_ultima = sec or "inicio"
    st.markdown("")
    if prod and sec == "catalogo":
        _editar_producto(prod)
        return
    if cli and sec == "clientes":
        _ficha_cliente(cli)
        return
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

    c1, c2, c3, c4, c5, c6 = st.columns([1.8, 0.9, 1, 1.1, 1.2, 1])
    busq = c1.text_input("Buscar", key="adm_busq", placeholder="código o nombre")
    marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="adm_marca", placeholder="Todas")
    temporada = c3.multiselect("Temporada", sorted(df["temporada"].dropna().unique()), key="adm_temp",
                               placeholder="Todas")
    categoria = c4.multiselect("Categoría", sorted(df["categoria"].dropna().unique()), key="adm_cat",
                               placeholder="Todas")
    rubro = c5.multiselect("Tipo de producto", sorted(df["rubro"].dropna().unique()), key="adm_rubro",
                           placeholder="Todos")
    multi = c6.toggle("Selección múltiple", key="adm_multi")
    sub = catalog.filtrar_variantes(df, {"marca": marca, "temporada": temporada,
                                         "categoria": categoria, "rubro": rubro}, busq)

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
            b[0].markdown(f"<b style='color:#006786'>{len(sel_cods)} producto(s) seleccionados</b><br>"
                          "<span class='muted'>las acciones de lote se aplican al instante</span>",
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

    # Fase 8 (T5): acciones masivas por alcance — el filtro de arriba (marca /
    # temporada / categoría / tipo de producto / búsqueda / pill) define el conjunto.
    filtros_desc = " · ".join(filter(None, [
        f"búsqueda «{busq}»" if busq else "",
        ("marca " + "/".join(marca)) if marca else "",
        ("temporada " + "/".join(temporada)) if temporada else "",
        ("categoría " + "/".join(categoria)) if categoria else "",
        ("tipo " + "/".join(rubro)) if rubro else "",
        f"pill «{pill}»" if pill != "Todos" else "",
    ])) or "sin filtros: el catálogo COMPLETO"
    with st.expander("Acciones masivas sobre todo lo filtrado"):
        st.markdown(f"<p class='muted'>Afecta a los <b>{len(prods)} productos</b> del filtro actual "
                    f"({filtros_desc}). Con más de 10 productos pide confirmación.</p>",
                    unsafe_allow_html=True)
        f1, f2, f3, f4 = st.columns(4)
        if f1.button("Ocultar todo", key="masivo_ocultar", disabled=prods.empty, use_container_width=True):
            _aplicar_lote(list(prods["producto_cod"]), {"publicado": False})
        if f2.button("Volver a automático", key="masivo_auto", disabled=prods.empty, use_container_width=True):
            _aplicar_lote(list(prods["producto_cod"]), {"publicado": None})
        if f3.button("Destacar todo", key="masivo_dest", disabled=prods.empty, use_container_width=True):
            _aplicar_lote(list(prods["producto_cod"]), {"destacado": True})
        if f4.button("Quitar destacados", key="masivo_nodest", disabled=prods.empty, use_container_width=True):
            _aplicar_lote(list(prods["producto_cod"]), {"destacado": False})

    with st.expander("Fotos ↔ variantes (auditoría)"):
        st.markdown("<p class='muted'>Genera el mapa de qué foto usa cada variante (equivalente al "
                    "imagenes.csv del Woo), sobre lo FILTRADO arriba. Origen: <b>color</b> = matching "
                    "automático · <b>manual</b> = asignada en la ficha · <b>portada</b> = sin foto "
                    "propia del color · <b>sin_foto</b>.</p>", unsafe_allow_html=True)
        if st.button("Generar mapeo", key="fotomap_gen"):
            with st.spinner("Cruzando fotos y variantes..."):
                rows = fotos.mapeo_variantes(
                    sub[["producto_cod", "sku", "color", "talle"]].to_dict("records"),
                    overrides_por_prod=ov)
            st.session_state.adm_fotomap = pd.DataFrame(rows)
        fm = st.session_state.get("adm_fotomap")
        if fm is not None and len(fm):
            cnt = fm["origen"].value_counts().to_dict()
            st.markdown("<p class='muted'>" + " · ".join(f"{k}: <b>{v}</b>" for k, v in sorted(cnt.items()))
                        + f" · {len(fm)} variantes</p>", unsafe_allow_html=True)
            st.download_button("Descargar CSV", data=fm.to_csv(index=False).encode("utf-8"),
                               file_name="fotos_variantes.csv", mime="text/csv", key="fotomap_dl")
            sin = fm[fm["origen"].isin(["portada", "sin_foto"])]
            if len(sin):
                st.dataframe(sin.head(50), hide_index=True, use_container_width=True)


LOTE_LABEL = {("publicado", False): "OCULTAR", ("publicado", None): "volver a publicación AUTOMÁTICA",
              ("destacado", True): "DESTACAR", ("destacado", False): "quitar el destacado a"}


def _lote_desc(campos: dict) -> str:
    k, v = next(iter(campos.items()))
    return LOTE_LABEL.get((k, v), str(campos))


def _aplicar_lote(cods: list[str], campos: dict) -> None:
    if len(cods) > 10:
        _confirmar_lote(cods, campos)
        return
    overrides.set_masivo(cods, campos, _admin_email())
    st.toast(f"{len(cods)} producto(s) actualizados")
    st.session_state.adm_tabla_ver = st.session_state.get("adm_tabla_ver", 0) + 1
    st.rerun()


@st.dialog("Confirmar acción masiva")
def _confirmar_lote(cods: list[str], campos: dict) -> None:
    st.warning(f"Vas a **{_lote_desc(campos)}** **{len(cods)} productos**. "
               "Se aplica al instante (sin Guardar). ¿Seguro?")
    c1, c2 = st.columns(2)
    if c1.button("Sí, aplicar", type="primary", use_container_width=True):
        with st.spinner(f"Aplicando a {len(cods)} productos..."):
            overrides.set_masivo(cods, campos, _admin_email())
        st.toast(f"{len(cods)} producto(s) actualizados")
        st.session_state.adm_tabla_ver = st.session_state.get("adm_tabla_ver", 0) + 1
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------------------------
# Editor de producto como PANTALLA (handoff 10, 11, 12, 14)
# ---------------------------------------------------------------------------
def _limpiar_edicion_producto(cod: str) -> None:
    """Borra el estado de los widgets de edición para que siempre arranquen
    desde lo GUARDADO (fase 6.1: editar sin guardar no deja rastro)."""
    for k in [f"pe_{cod}_{n}" for n in (1, 2, 3, 4)] + [f"adm_var_{cod}", f"adm_extra_{cod}",
                                                        f"adm_fc_{cod}", f"adm_port_{cod}"]:
        st.session_state.pop(k, None)


def _editar_producto(cod: str) -> None:
    """Ficha de producto: modo VISTA (default) ↔ modo EDICIÓN (handoff fase 6, E2)."""
    if st.button("← Catálogo"):
        st.session_state.adm_prod = None
        st.session_state.adm_prod_edit = False
        st.session_state.adm_nav_forzar = "catalogo"
        _limpiar_edicion_producto(cod)
        st.rerun()
    # Al cambiar de producto siempre se entra en modo vista, sin estado viejo
    if st.session_state.get("adm_prod_edit_cod") != cod:
        st.session_state.adm_prod_edit = False
        st.session_state.adm_prod_edit_cod = cod
        _limpiar_edicion_producto(cod)
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
        _limpiar_edicion_producto(cod)   # arrancar la edición desde lo guardado
        st.rerun()
    rubros = " / ".join(filter(None, [str(f0.get("categoria") or ""), str(f0["rubro"] or "")]))
    st.markdown(f"<div class='card-sub'>{cod} · {f0['marca'] or ''} · {f0['temporada'] or ''} · "
                f"{rubros}"
                + (f" · overrides por {o.get('updated_by')}" if o.get("updated_by") else "")
                + "</div>", unsafe_allow_html=True)
    st.markdown("")

    if not editando:
        _producto_vista(cod, f0, filas, o, raw_p, stock_bq)
        return
    _producto_edicion(cod, f0, filas, o, raw_p, stock_bq)


def _producto_vista(cod, f0, filas, o, raw_p, stock_bq) -> None:
    """Solo lectura (handoff v2 §B): qué ve el cliente hoy y de dónde sale cada valor."""
    manual = "<span style='color:#006786'>manual</span>"

    def _attr(kicker: str, valor: str, es_manual: bool, top: str = ".6rem") -> str:
        return (f"<div class='kicker' style='margin-top:{top}'>{kicker}</div>{valor}"
                + (f"<br>{manual}" if es_manual else ""))

    ci, cd = st.columns([1, 2.6], gap="large")
    with ci:
        st.image(fotos.foto_principal(cod), use_container_width=True)
        pub = o.get("publicado") if o.get("publicado") in (True, False) else None
        regla = {None: "Automático — visible si tiene stock", True: "Publicado — visible, exige stock > 0",
                 False: "Oculto — nunca visible"}[pub]
        n_fotos = len(fotos.indice_fotos().get(cod.upper(), []))
        st.markdown(
            _attr("Publicación", regla, pub is not None, top=".2rem")
            + _attr("Destacado", "Sí" if o.get("destacado") else "No", bool(o.get("destacado")))
            + _attr("Múltiplo (U.B.)", f"{o.get('ub')} unidades" if o.get("ub") else "Libre", bool(o.get("ub")))
            + _attr("Fotos", f"{n_fotos} cargada(s)" if n_fotos else "Sin foto", False),
            unsafe_allow_html=True)
    with cd:
        aleph_nombre = str(raw_p.iloc[0]["producto_nombre"]) if not raw_p.empty else ""
        aleph_descr = str(raw_p.iloc[0].get("descripcion") or "") if not raw_p.empty else ""
        n1, n2 = st.columns(2)
        n1.markdown(f"<div class='kicker'>Nombre</div>{f0['producto_nombre']} "
                    + (manual if o.get("nombre") else "")
                    + (f"<br><span class='muted'>Aleph: {aleph_nombre}</span>" if o.get("nombre") else ""),
                    unsafe_allow_html=True)
        n2.markdown(f"<div class='kicker'>Descripción</div>{o.get('descripcion') or aleph_descr or '—'} "
                    + (manual if o.get("descripcion") else "")
                    + (f"<br><span class='muted'>Aleph: {aleph_descr}</span>"
                       if o.get("descripcion") and aleph_descr else ""),
                    unsafe_allow_html=True)
        st.markdown("<div class='kicker' style='margin:1rem 0 .3rem'>Precio efectivo por lista</div>",
                    unsafe_allow_html=True)
        ov_p = o.get("precios") or {}
        pcols = st.columns(4)
        for i, n in enumerate((1, 2, 3, 4)):
            aleph = float(raw_p.iloc[0][f"precio{n}"]) if not raw_p.empty else 0
            efectivo = float(ov_p.get(str(n)) or aleph)
            origen = ("<span style='color:#006786'>Manual</span>" if ov_p.get(str(n))
                      else "<span class='muted'>Aleph</span>")
            pcols[i].markdown(
                "<div style='border-top:1px solid rgba(32,30,29,.35); padding-top:.35rem'>"
                f"Lista {n}<br><span style='font-size:1.35rem; font-weight:600'>"
                f"{_fmt(efectivo) if efectivo > 0 else '—'}</span><br>{origen}</div>",
                unsafe_allow_html=True)

    st.markdown("<div class='kicker' style='margin:1rem 0 .3rem'>Variantes · efectivo hoy — "
                "<span style='text-transform:none; letter-spacing:0'>lo que el cliente ve ahora, "
                "con el origen de cada valor</span></div>", unsafe_allow_html=True)
    vov = o.get("variantes") or {}

    def _origenes(r) -> str:
        if r.get("es_manual"):
            return "VARIANTE MANUAL"
        vo = vov.get(r["sku"], {})
        return " · ".join(filter(None, [
            "stock manual" if vo.get("stock") is not None else "",
            "oculta" if vo.get("oculta") else "",
            "precio manual" if vo.get("precios") else "",
        ]))

    vdf = pd.DataFrame([{
        "SKU": r["sku"], "Color": r["color"], "Talle": r["talle"],
        "EAN": (str(r["ean"]) if r["ean"] else "—"),
        "Stock": 0 if vov.get(r["sku"], {}).get("oculta") else int(r["stock"]),
        "Aleph": "—" if r.get("es_manual") else str(stock_bq.get(r["sku"], 0)),
        "Precio L1": _fmt(float(r["precio1"])),
        "Overrides": _origenes(r),
    } for _, r in filas.iterrows()])

    def _color_origen(v):
        if v == "VARIANTE MANUAL":
            return "color:#aa0b56; font-weight:600"
        return "color:#006786" if v else ""

    sty = (vdf.style.map(_color_origen, subset=["Overrides"]) if hasattr(vdf.style, "map")
           else vdf.style.applymap(_color_origen, subset=["Overrides"]))
    st.dataframe(sty, hide_index=True, use_container_width=True)

    avisos = []
    for sku, vo in sorted(vov.items()):
        if vo.get("stock") is not None:
            avisos.append(f"{sku} tiene stock manual ({vo['stock']} u.) sobre un stock real de "
                          f"{stock_bq.get(sku, 0)} — el sitio no valida contra Aleph mientras dure.")
    for sku in sorted(o.get("variantes_extra") or {}):
        avisos.append(f"{sku} es una variante manual: no existe en Aleph y el Excel del pedido la marca.")
    if avisos:
        st.markdown("<div class='aviso-bloque'>" + " ".join(avisos) + "</div>", unsafe_allow_html=True)


def _producto_edicion(cod, f0, filas, o, raw_p, stock_bq) -> None:
    st.markdown("<p class='muted'><b style='color:#201e1d'>Nada se aplica hasta tocar Guardar</b> — "
                "Descartar vuelve a la vista sin cambios. Única excepción: «Agregar variante manual», "
                "que se aplica al instante.</p>", unsafe_allow_html=True)
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
    st.markdown("<div class='kicker' style='margin:.8rem 0 0'>Variantes manuales</div>"
                "<p class='muted' style='margin:0 0 .4rem'>No existen en Aleph: stock y precio son "
                "100% tuyos y el Excel las marca. <span style='color:#006786'>«Agregar» se aplica al "
                "instante</span>; las ediciones de la tabla van con Guardar.</p>",
                unsafe_allow_html=True)
    if extras:
        xdf = pd.DataFrame([{"sku": sku, "color": vo.get("color", ""), "talle": vo.get("talle", ""),
                             "stock": int(vo.get("stock") or 0),
                             "precio_l1": float((vo.get("precios") or {}).get("1") or 0),
                             "ean": vo.get("ean", ""), "quitar": False}
                            for sku, vo in sorted(extras.items())])
        xed = st.data_editor(xdf, hide_index=True, use_container_width=True, key=f"adm_extra_{cod}",
                             disabled=["sku", "color", "talle"],
                             column_config={
                                 "sku": "SKU", "color": "Color", "talle": "Talle",
                                 "stock": st.column_config.NumberColumn("Stock", min_value=0, step=1),
                                 "precio_l1": st.column_config.NumberColumn("Precio L1", min_value=0.0,
                                                                            step=100.0, format="$ %.0f"),
                                 "ean": "EAN", "quitar": st.column_config.CheckboxColumn("Quitar ×"),
                             })
    else:
        xed = None
        st.markdown("<p class='muted'>Este producto no tiene variantes manuales.</p>", unsafe_allow_html=True)
    with st.form(f"extra_{cod}", border=False):
        a = st.columns([1.2, 0.8, 0.8, 1, 1.2, 1.2])
        x_color = a[0].text_input("Color nuevo", placeholder="obligatorio")
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

    # --- Fotos por color (fase 9): asociar variante ↔ foto ---
    files_prod = fotos.indice_fotos().get(cod.upper(), [])
    fed = None
    if files_prod:
        st.markdown("<div class='kicker' style='margin:.8rem 0 0'>Fotos por color</div>"
                    "<p class='muted' style='margin:0 0 .4rem'>La miniatura de cada variante usa la "
                    "foto de SU color (detección por nombre de archivo, como el Woo). Si un color no "
                    "matchea, asignale el archivo a mano — va con Guardar.</p>", unsafe_allow_html=True)
        colores_prod = list(dict.fromkeys(filas["color"]))
        ov_fc = o.get("fotos_color") or {}
        mapa_auto = fotos.foto_por_color(cod, colores_prod, files_prod, None)
        fdf = pd.DataFrame([{
            "color": c,
            "auto": mapa_auto.get(fotos.norm(c)) or "— (usa portada)",
            "manual": ov_fc.get(fotos.norm(c)) or "(automática)",
        } for c in colores_prod])
        fed = st.data_editor(fdf, key=f"adm_fc_{cod}", hide_index=True, use_container_width=True,
                             disabled=["color", "auto"],
                             column_config={
                                 "color": "Color", "auto": "Foto detectada",
                                 "manual": st.column_config.SelectboxColumn(
                                     "Asignación manual", options=["(automática)"] + sorted(files_prod)),
                             })

    # --- Foto de portada elegible (pisa la automática) ---
    portada_sel = None
    if files_prod:
        st.markdown("<div class='kicker' style='margin:.8rem 0 0'>Foto de portada</div>"
                    "<p class='muted' style='margin:0 0 .4rem'>Con la que el producto aparece en el "
                    "catálogo. «Automática» = la detectada por nombre. Va con Guardar.</p>",
                    unsafe_allow_html=True)
        pc1, pc2 = st.columns([2.2, 1])
        op_port = ["Automática"] + sorted(files_prod)
        actual_p = o.get("portada") if o.get("portada") in files_prod else "Automática"
        portada_sel = pc1.selectbox("Foto de portada", op_port, index=op_port.index(actual_p),
                                    key=f"adm_port_{cod}", label_visibility="collapsed")
        if portada_sel != "Automática":
            pc2.image(fotos.url_foto(cod.upper(), portada_sel), width=110)

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
        if portada_sel is not None:
            campos["portada"] = portada_sel if portada_sel != "Automática" else ""
        if fed is not None:   # asignación manual foto↔color (reemplazo completo)
            campos["fotos_color"] = {fotos.norm(r["color"]): r["manual"] for _, r in fed.iterrows()
                                     if r["manual"] and r["manual"] != "(automática)"}
        if xed is not None:   # ediciones/bajas de variantes manuales
            campos["variantes_extra"] = {
                r["sku"]: {"color": r["color"], "talle": r["talle"], "stock": int(r["stock"] or 0),
                           "precios": {"1": float(r["precio_l1"] or 0)}, "ean": str(r["ean"] or "")}
                for _, r in xed.iterrows() if not bool(r["quitar"])}
        overrides.set_catalogo_override(cod, campos, _admin_email())
        st.session_state.adm_prod_edit = False   # guardar vuelve a modo vista
        _limpiar_edicion_producto(cod)
        st.toast(f"{cod} guardado")
        st.rerun()
    if g2.button("Descartar", use_container_width=True):
        st.session_state.adm_prod_edit = False
        _limpiar_edicion_producto(cod)
        st.rerun()
    if g3.button("Quitar TODOS los overrides", use_container_width=True):
        overrides.quitar_catalogo_override(cod)
        st.session_state.adm_prod_edit = False
        _limpiar_edicion_producto(cod)
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
        warn = st.session_state.pop("adm_pwd_warn", None)
        st.success(f"Password de **{e}**: `{p}` — guardala ahora"
                   + ("." if warn else " (también quedó en el secret `mayorista-seed-passwords`)."))
        if warn:
            st.warning(warn)


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
        warn = st.session_state.pop("adm_pwd_warn", None)
        st.success(f"Password de **{em}**: `{pw}` — guardala ahora"
                   + ("." if warn else " (también quedó en el secret `mayorista-seed-passwords`)."))
        if warn:
            st.warning(warn)

    if editando:
        _cliente_edicion(email, u, cod, e)
        return

    # ---- VISTA (handoff v2 §D) ----
    def _dato(col, kicker: str, valor, origen: str | None = None) -> None:
        html = f"<div class='kicker'>{kicker}</div><span style='font-size:1.25rem'>{valor}</span>"
        if origen:
            color = "#006786" if origen.lower() == "override" else "var(--muted)"
            html += f"<br><span style='color:{color}'>{origen.capitalize()}</span>"
        col.markdown(html, unsafe_allow_html=True)

    if e:
        d = st.columns(4)
        _dato(d[0], "Lista de precios", e["lista_precios"], e["lista_origen"])
        _dato(d[1], "Descuento cabecera", f"{e['descuento']:g}%", e["descuento_origen"])
        _dato(d[2], "CUIT", e.get("cuit") or "—", e.get("cuit_origen"))
        _dato(d[3], "Ubicación", f"{e.get('localidad') or '—'} · {e.get('provincia_desc') or ''}")
        contacto = " · ".join(filter(None, [e.get("contacto_nombre"), e.get("contacto_email"), e.get("contacto_telefono")]))
        st.markdown(f"<div class='kicker' style='margin-top:.5rem'>Contacto</div>"
                    f"{contacto or '<span class=muted>sin cargar — se pide al confirmar un pedido</span>'}",
                    unsafe_allow_html=True)
        if e.get("notas"):
            st.markdown(f"<p class='muted'>Notas: {e['notas']}</p>", unsafe_allow_html=True)

    lista, ev = [], None
    if cod is None:
        if u.get("rol") == "admin":
            st.markdown("<p class='muted'>Usuario administrador, sin historial de pedidos.</p>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<div class='aviso-bloque'>Usuario cliente SIN cliente de Aleph asociado: "
                        "no puede hacer pedidos. Entrá a «Editar» y asignale el cliente_cod en la "
                        "sección Cuenta.</div>", unsafe_allow_html=True)
    else:
        with st.spinner("Buscando pedidos del cliente..."):
            lista = pedidos.listar_pedidos(int(cod))
        m = _metricas_cliente(lista)
        st.markdown("<div class='kicker' style='margin:1rem 0 .3rem'>Métricas</div>", unsafe_allow_html=True)
        met = st.columns(6)
        datos = [("Pedidos", str(m["pedidos"])), ("Unidades", f"{m['unidades']:,}".replace(",", ".")),
                 ("Total histórico", _fmt_compacto(m["total"])),
                 ("Ticket promedio", _fmt_compacto(m["ticket"])),
                 ("Último pedido", m["ultimo"]), ("Cancelados", str(m["cancelados"]))]
        for col, (lab, val) in zip(met, datos):
            col.markdown("<div style='border-top:1px solid rgba(32,30,29,.35); padding-top:.35rem'>"
                         f"<span class='muted'>{lab}</span><br>"
                         f"<span style='font-size:1.4rem; font-weight:600'>{val}</span></div>",
                         unsafe_allow_html=True)

        ct, cp = st.columns([1, 1.6], gap="large")
        with ct:
            st.markdown("<div class='kicker' style='margin:1rem 0 .3rem'>Top productos</div>",
                        unsafe_allow_html=True)
            if m["top"]:
                for codp, nom, uds in m["top"]:
                    st.markdown("<div style='display:flex; justify-content:space-between; "
                                "border-bottom:1px solid rgba(32,30,29,.12); padding:.3rem 0'>"
                                f"<span>{nom} <span class='muted' style='font-size:.8rem'>{codp}</span></span>"
                                f"<span>{uds} u.</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<p class='muted'>Sin compras todavía.</p>", unsafe_allow_html=True)
        with cp:
            st.markdown("<div class='kicker' style='margin:1rem 0 .3rem'>Pedidos · click para ver el "
                        "detalle</div>", unsafe_allow_html=True)
            if lista:
                tabla = pd.DataFrame([{
                    "N°": f"{p['numero']:06d}", "Fecha": p.get("fecha_str", ""),
                    "Unid.": p["unidades"], "Total": _fmt(p["total"]),
                    "Estado": p["estado"].upper(),
                } for p in lista])
                estilos = {"CONFIRMADO": "background-color:#e9f8ff; color:#006786",
                           "PROCESADO": "background-color:#eae7e7; color:#444141",
                           "CANCELADO": "background-color:#fff1f4; color:#aa0b56"}
                _est = lambda v: estilos.get(v, "")  # noqa: E731
                sty = (tabla.style.map(_est, subset=["Estado"]) if hasattr(tabla.style, "map")
                       else tabla.style.applymap(_est, subset=["Estado"]))
                ev = st.dataframe(sty, hide_index=True, use_container_width=True, key=f"cli_ped_{cod}",
                                  on_select="rerun", selection_mode="single-row")
            else:
                st.markdown("<p class='muted'>Sin pedidos todavía.</p>", unsafe_allow_html=True)
        if ev is not None and ev.selection.rows:
            _detalle_pedido(lista[ev.selection.rows[0]])

    if cod is not None:
        # --- Importar historial de Aleph (fase 10) ---
        if st.session_state.get("adm_import_msg"):
            st.markdown("<div class='nota-acento'>" + "<br>".join(st.session_state.pop("adm_import_msg"))
                        + "</div>", unsafe_allow_html=True)
        with st.expander("Importar historial de Aleph"):
            st.markdown("<p class='muted'>Trae los últimos N comprobantes de venta del cliente "
                        "(NP y facturas, sin anulados) desde el espejo del ERP central y los crea "
                        "como pedidos «procesados», con su Excel y backup. Los ya importados se "
                        "saltean: pedir de nuevo NUNCA duplica.</p>", unsafe_allow_html=True)
            i1, i2 = st.columns([1, 1.6], vertical_alignment="bottom")
            n_imp = i1.number_input("Cantidad a traer", 1, 50, 3, key=f"imp_n_{cod}")
            if i2.button("Importar de Aleph", key=f"imp_btn_{cod}", use_container_width=True):
                with st.spinner("Leyendo Aleph e importando..."):
                    try:
                        msgs = aleph_import.importar(int(cod), int(n_imp))
                    except Exception as ex:  # noqa: BLE001
                        msgs = [f"Error importando: {ex}"]
                st.session_state.adm_import_msg = msgs
                st.rerun()

    if cod is not None:
        # --- Reposición sugerida (fase 11): solo franquicias con PV ---
        try:
            pv_rep = reposicion.pv_de_cliente(int(cod))
        except Exception:  # noqa: BLE001
            pv_rep = None
        if pv_rep:
            with st.expander(f"Reposición sugerida hoy — {pv_rep['pv_nombre']}"):
                dias_def = int(overrides.get_config().get("repo_dias_objetivo") or 21)
                st.markdown("<p class='muted'>Lo que el sitio le sugeriría hoy a esta franquicia "
                            "(la velocidad de venta es siempre la de los últimos 30 días).</p>",
                            unsafe_allow_html=True)
                dias_rep = st.pills("Días de venta a cubrir", sorted({7, 14, 21, 30, dias_def}),
                                    default=dias_def, format_func=lambda d: f"{d} días",
                                    key=f"rep_dias_{cod}") or dias_def
                if st.button("Calcular", key=f"rep_calc_{cod}"):
                    with st.spinner("Calculando..."):
                        df_rep = catalog.con_precio(catalog.variantes_publicadas(),
                                                    (e or {}).get("lista_precios") or 1)
                        _, sug_rep = reposicion.sugerencias(int(cod), df_rep, dias_rep)
                    st.session_state[f"rep_sug_{cod}"] = sug_rep
                sug_rep = st.session_state.get(f"rep_sug_{cod}")
                if sug_rep is not None:
                    if len(sug_rep) == 0:
                        st.markdown("<p class='muted'>Nada para reponer hoy.</p>",
                                    unsafe_allow_html=True)
                    else:
                        vis = sug_rep[["producto_cod", "producto_nombre", "color", "talle",
                                       "vendidas_30d", "stock_pv", "sugerido"]]
                        st.dataframe(vis, hide_index=True, use_container_width=True,
                                     column_config={"producto_cod": "Código",
                                                    "producto_nombre": "Producto",
                                                    "vendidas_30d": "Vendió 30d",
                                                    "stock_pv": "Tiene", "sugerido": "Sugerido"})
                        st.download_button("Descargar CSV", key=f"rep_csv_{cod}",
                                           data=vis.to_csv(index=False).encode("utf-8"),
                                           file_name=f"reposicion_{cod}.csv", mime="text/csv")

    # Acciones instantáneas, separadas al pie (no pasan por Guardar)
    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:1rem 0 .4rem'></div>",
                unsafe_allow_html=True)
    a0, a1, a2 = st.columns([2.2, 1.2, 1.2], vertical_alignment="center")
    a0.markdown("<p class='muted' style='margin:0'>Estas dos acciones se aplican al instante, "
                "sin guardar:</p>", unsafe_allow_html=True)
    if a1.button("Resetear password", key="cli_resetpwd", use_container_width=True):
        pwd = auth.generar_password()
        auth.cambiar_password(email, pwd)
        res = auth.guardar_password_en_secret(email, pwd)   # tolerante: nunca rompe
        st.session_state.adm_pwd_msg = (email, pwd)
        if not res["ok"]:
            st.session_state.adm_pwd_warn = ("No se pudo guardar la password en el secret "
                                             f"— anotala AHORA. ({res['error'][:180]})")
        st.rerun()
    if u.get("activo", True):
        if a2.button("Desactivar usuario", key="cli_desactivar", use_container_width=True):
            db.usuario_ref(email).update({"activo": False})
            st.rerun()
    elif a2.button("Activar usuario", key="cli_activar", use_container_width=True):
        db.usuario_ref(email).update({"activo": True})
        st.rerun()


def _cliente_edicion(email: str, u: dict, cod, e) -> None:
    # --- Cuenta: rol y cliente de Aleph al que pertenece el usuario ---
    st.markdown("<div class='kicker' style='margin:.2rem 0 .1rem'>Cuenta</div>"
                "<p class='muted' style='margin:0 0 .4rem'>Rol y cliente de Aleph del usuario. "
                "Sin cliente asociado no puede hacer pedidos.</p>", unsafe_allow_html=True)
    with st.form(f"cuenta_{email}"):
        a1, a2 = st.columns(2)
        rol_n = a1.selectbox("Rol", ["cliente", "admin"], index=0 if u.get("rol") != "admin" else 1)
        cod_n = a2.number_input("cliente_cod de Aleph (0 = sin cliente)", min_value=0, step=1,
                                value=int(cod or 0))
        if st.form_submit_button("Guardar cuenta", use_container_width=True):
            try:
                nuevo_cod = int(cod_n) or None
                cambios = {"rol": rol_n, "cliente_cod": nuevo_cod}
                if nuevo_cod and nuevo_cod != (int(cod) if cod is not None else None):
                    cli_a = catalog.get_cliente(nuevo_cod)
                    if cli_a is None:
                        raise ValueError(f"cliente_cod {nuevo_cod} no existe en dim_cliente")
                    cambios["nombre_display"] = cli_a["nombre_display"]
                db.usuario_ref(email).update(cambios)
                st.session_state.adm_cli_edit = False
                st.toast("Cuenta actualizada")
                st.rerun()
            except Exception as ex:  # noqa: BLE001
                st.error(str(ex))
    st.markdown("<div style='border-top:1px solid rgba(32,30,29,.16); margin:.6rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    if cod is not None:
        o = overrides.get_clientes_overrides().get(int(cod), {})
        with st.form(f"cli_{cod}"):
            usar_desc = st.checkbox("Override de descuento", value=o.get("descuento_pct") is not None)
            desc = st.number_input("Descuento %", 0.0, 100.0,
                                   float(o.get("descuento_pct") or (e or {}).get("descuento") or 0), step=0.5)
            usar_lista = st.checkbox("Override de lista", value=bool(o.get("lista_precios")))
            lista = st.number_input("Lista de precios", 1, 10,
                                    int(o.get("lista_precios") or (e or {}).get("lista_precios") or 1))
            c1, c2 = st.columns(2)
            contacto_n = c1.text_input("Persona de contacto", value=o.get("contacto_nombre") or "")
            contacto_e = c2.text_input("Email de contacto", value=o.get("contacto_email") or "")
            contacto_t = st.text_input("Teléfono de contacto", value=o.get("contacto_telefono") or "",
                                       placeholder="+54 9 ...")
            cuit = st.text_input("CUIT", value=o.get("cuit") or "",
                                 placeholder=f"vacío = usa Aleph ({(e or {}).get('cuit') or '—'})")
            odoo_cli = st.text_input("Nombre del cliente en Odoo (export de franquicias)",
                                     value=o.get("odoo_cliente") or "",
                                     placeholder="ej. Drago Tech, Soporte Drago Leonel — vacío = nombre de Aleph")
            notas = st.text_input("Notas", value=o.get("notas") or "")
            g1, g2 = st.columns(2)
            if g1.form_submit_button("Guardar", type="primary", use_container_width=True):
                overrides.set_cliente_override(int(cod), {
                    "descuento_pct": float(desc) if usar_desc else None,
                    "lista_precios": int(lista) if usar_lista else None,
                    "contacto_nombre": contacto_n.strip(),
                    "contacto_email": contacto_e.strip().lower(),
                    "contacto_telefono": contacto_t.strip(),
                    "cuit": cuit.strip() or None,
                    "odoo_cliente": odoo_cli.strip(),
                    "notas": notas.strip(),
                }, _admin_email())
                st.session_state.adm_cli_edit = False
                st.toast("Cliente guardado")
                st.rerun()
            if g2.form_submit_button("Descartar", use_container_width=True):
                st.session_state.adm_cli_edit = False
                st.rerun()
    else:
        st.markdown("<p class='muted'>Sin cliente asociado no hay datos comerciales para editar: "
                    "asignale un cliente_cod arriba para que pueda pedir.</p>", unsafe_allow_html=True)
        if st.button("Volver a la vista"):
            st.session_state.adm_cli_edit = False
            st.rerun()
    st.markdown("<p class='muted'>Resetear password y activar/desactivar están en la vista de la "
                "ficha (se aplican al instante, no pasan por Guardar).</p>", unsafe_allow_html=True)


@st.dialog("Nuevo usuario")
def _alta_usuario() -> None:
    with st.form("alta_usuario", clear_on_submit=True):
        email = st.text_input("Email")
        cod = st.number_input("cliente_cod de Aleph (0 = sin cliente: solo para admins)",
                              min_value=0, step=1, value=0)
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
                res = auth.guardar_password_en_secret(email, pwd)
                st.session_state.adm_pwd_msg = (email.strip().lower(), pwd)
                if not res["ok"]:
                    st.session_state.adm_pwd_warn = ("No se pudo guardar la password en el secret "
                                                     f"— anotala AHORA. ({res['error'][:180]})")
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
    contacto_p = " · ".join(filter(None, [p.get("contacto_nombre"), p.get("contacto_email"), p.get("contacto_telefono")]))
    if contacto_p:
        st.markdown(f"<p class='muted'>Contacto del pedido: {contacto_p}</p>", unsafe_allow_html=True)
    if p.get("observaciones"):
        st.markdown(f"<p class='muted'>Obs: {p['observaciones']}</p>", unsafe_allow_html=True)
    for h in p.get("historial", []):
        st.markdown(f"<p class='muted'>{h['en'].astimezone(TZ):%d/%m %H:%M} — <b>{h['estado']}</b> "
                    f"por {h['por']}</p>", unsafe_allow_html=True)
        if h.get("detalle"):
            st.markdown(f"<p class='muted' style='margin:-.4rem 0 .4rem 1.2rem; "
                        f"white-space:pre-line'>{h['detalle']}</p>", unsafe_allow_html=True)

    items = pd.DataFrame(p["items"])
    items["foto"] = items.apply(
        lambda r: fotos.miniatura(r["producto_cod"], r.get("color")) if fotos.tiene_fotos(r["producto_cod"]) else "",
        axis=1)
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
            res = email_notif.enviar_confirmacion(p, pedidos.generar_excel(p), p["xlsx_filename"])
            st.success(f"Reenviado a {', '.join(res['destinatarios'])}") if res["enviado"] else st.error(res["error"])
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    cols[3].download_button("Excel", data=pedidos.generar_excel(p),   # fresco: con fotos
                            file_name=p["xlsx_filename"], key=f"dl_{p['numero']}", use_container_width=True)

    # --- Modificar pedido: SOLO en estado confirmado (antes de procesar) ---
    if p["estado"] == "confirmado":
        with st.expander("Modificar pedido (avisa al cliente)"):
            st.markdown("<p class='muted'>Cambiá cantidades o marcá «Quitar» (0 también quita). "
                        "Solo se puede antes de marcarlo procesado. Al guardar se recalculan los "
                        "totales, se regenera el Excel y <b>se le avisa al cliente por email</b>.</p>",
                        unsafe_allow_html=True)
            base = pd.DataFrame([{
                "sku": str(it["sku"]), "producto_cod": it["producto_cod"],
                "producto_nombre": it.get("producto_nombre", ""), "color": it.get("color", ""),
                "talle": it.get("talle", ""), "precio_unit": float(it["precio_unit"]),
                "cantidad": int(it["cantidad"]), "quitar": False,
            } for it in p["items"]])
            med = st.data_editor(
                base, hide_index=True, use_container_width=True, key=f"adm_mod_{p['numero']}",
                disabled=["sku", "producto_cod", "producto_nombre", "color", "talle", "precio_unit"],
                column_config={
                    "sku": None, "producto_cod": "Código", "producto_nombre": "Producto",
                    "color": "Color", "talle": "Talle",
                    "precio_unit": st.column_config.NumberColumn("Precio", format="$ %.0f"),
                    "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1),
                    "quitar": st.column_config.CheckboxColumn("Quitar"),
                })
            if st.button("Guardar cambios y avisar al cliente", type="primary",
                         key=f"adm_mod_ok_{p['numero']}"):
                cants = {str(r["sku"]): (0 if bool(r["quitar"]) else int(r["cantidad"] or 0))
                         for _, r in med.iterrows()}
                try:
                    nuevo = pedidos.modificar_pedido(int(p["numero"]), cants, _admin_email())
                    em = nuevo.get("email_modificado") or {}
                    st.session_state.pop(f"adm_mod_{p['numero']}", None)
                    st.toast(f"Pedido {p['numero']} modificado"
                             + (" · cliente avisado" if em.get("enviado") else " · email no salió"))
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    else:
        st.markdown("<p class='muted'>Un pedido procesado o cancelado ya no se modifica — para "
                    "cambios, coordinalo por fuera o cancelá y rehacé.</p>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _sec_config() -> None:
    """Config global (handoff v2 §E): cada campo con su regla escrita debajo."""
    cfg = overrides.get_config()
    st.markdown("<p class='muted'>Todo esto afecta a los clientes al instante una vez guardado. "
                "Nada se aplica hasta tocar «Guardar configuración».</p>", unsafe_allow_html=True)
    with st.form("config_global"):
        email_to = st.text_input("Emails de Lautin que reciben pedidos (separados por coma)",
                                 value=cfg.get("pedidos_email_to") or "")
        st.markdown("<p class='muted' style='margin-top:-0.6rem'>Vacío = default del deploy "
                    f"({', '.join(appconfig.PEDIDOS_EMAIL_TO)})</p>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        minimo = c1.number_input("Mínimo de unidades por pedido", min_value=0, step=1,
                                 value=int(cfg.get("minimo_pedido_unidades") or 0))
        c1.markdown("<p class='muted' style='margin-top:-0.6rem'>0 = sin mínimo</p>",
                    unsafe_allow_html=True)
        minimo_m = c1.number_input("Mínimo de compra en $", min_value=0, step=5000,
                                   value=int(cfg.get("minimo_pedido_monto") or 0))
        c1.markdown("<p class='muted' style='margin-top:-0.6rem'>Sobre el subtotal a PRECIO DE LISTA "
                    "(sin IVA ni descuento cabecera) — con el descuento aplicado el total puede quedar "
                    "menor. 0 = sin mínimo</p>", unsafe_allow_html=True)
        iva = c2.number_input("IVA % informativo", min_value=0.0, max_value=30.0, step=0.5,
                              value=float(cfg.get("iva_pct") or 0))
        c2.markdown("<p class='muted' style='margin-top:-0.6rem'>Las listas de Aleph son sin IVA; se "
                    "muestra como línea aparte en carrito, Excel y email. 0 = ocultar</p>",
                    unsafe_allow_html=True)
        repo = st.number_input("Reposición: días de venta a cubrir", min_value=7, max_value=90,
                               step=1, value=int(cfg.get("repo_dias_objetivo") or 21))
        st.markdown("<p class='muted' style='margin-top:-0.6rem'>La página «Reposición» de las "
                    "franquicias sugiere cantidades para cubrir esta cantidad de días de venta</p>",
                    unsafe_allow_html=True)
        banner = st.text_area("Banner para clientes", value=cfg.get("banner_texto") or "", height=80)
        st.markdown("<div class='nota-acento'>Así lo va a ver el cliente arriba del catálogo. "
                    "Se muestra en todas las páginas hasta que vacíes el campo.</div>",
                    unsafe_allow_html=True)
        descvta = st.toggle("Aplicar descvta de Aleph", value=bool(cfg.get("aplicar_descvta")))
        st.markdown("<p class='muted' style='margin-top:-0.6rem'>El descuento por venta del ERP (por "
                    "artículo), como lo usa el Woo</p>", unsafe_allow_html=True)
        notificar = st.toggle("Notificar cambios de estado por email",
                              value=bool(cfg.get("notificar_estados", True)))
        st.markdown("<p class='muted' style='margin-top:-0.6rem'>Al cliente y a Lautin cuando un "
                    "pedido pasa a procesado o cancelado</p>", unsafe_allow_html=True)
        if st.form_submit_button("Guardar configuración", type="primary"):
            overrides.set_config({
                "pedidos_email_to": email_to.strip() or None,
                "banner_texto": banner.strip(),
                "aplicar_descvta": bool(descvta),
                "minimo_pedido_unidades": int(minimo) or None,
                "minimo_pedido_monto": float(minimo_m) or None,
                "iva_pct": float(iva),
                "notificar_estados": bool(notificar),
                "repo_dias_objetivo": int(repo),
            }, _admin_email())
            st.toast("Configuración guardada")
            st.rerun()
    b1, b2 = st.columns([1.2, 2.8], vertical_alignment="center")
    if b1.button("Actualizar catálogo ahora", use_container_width=True):
        with st.spinner("Refrescando catálogo e índice de fotos..."):
            catalog.load_variantes(force=True)
            fotos.indice_fotos(force=True)
            overrides.invalidar()
        st.toast("Catálogo actualizado")
        st.rerun()
    hace = catalog.catalogo_actualizado_hace()
    b2.markdown("<p class='muted' style='margin:0'>Relee BigQuery y el índice de fotos"
                + (f" · último refresco hace {hace // 60} min" if hace >= 0 else "")
                + "</p>", unsafe_allow_html=True)
    st.markdown("<div style='border-top:2px solid #201e1d; margin:1.2rem 0 .6rem'></div>",
                unsafe_allow_html=True)
    t1, t2 = st.columns([1, 2], vertical_alignment="bottom")
    t1.markdown("### Plantillas de email")
    t2.markdown("<p class='muted'>Editás el asunto y el cuerpo; la vista previa se arma con un "
                "pedido de ejemplo.</p>", unsafe_allow_html=True)
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


EVENTO_LABEL = {"confirmacion": "Confirmación de pedido",
                "procesado": "Cambio a procesado",
                "cancelado": "Cancelación", "modificado": "Modificación"}

VARIABLES_EMAIL = ("numero", "cliente", "cliente_cod", "usuario", "contacto", "fecha", "unidades",
                   "subtotal", "descuento_pct", "descuento_monto", "total", "iva_pct", "iva_monto",
                   "total_con_iva", "lineas_iva", "lista_precios", "observaciones", "detalle",
                   "quien", "estado")


def _config_emails() -> None:
    """Plantillas por evento (handoff v2 §F): editor y vista previa lado a lado."""
    if "em_evento" not in st.session_state:
        st.session_state.em_evento = "confirmacion"
    evento = st.pills("Evento", list(email_notif.EVENTOS), format_func=EVENTO_LABEL.get,
                      key="em_evento", label_visibility="collapsed") or "confirmacion"
    tpl = email_notif.template_de(evento)
    ejemplo = _pedido_ejemplo()
    vs = email_notif._SafeDict(email_notif.variables_pedido(ejemplo, _admin_email()))

    ced, cpre = st.columns(2, gap="large")
    with ced:
        asunto = st.text_input("Asunto", value=tpl["asunto"], key=f"em_asu_{evento}")
        formato = st.radio("Formato", ["texto", "html"], index=0 if tpl.get("formato") != "html" else 1,
                           key=f"em_fmt_{evento}", horizontal=True)
        cuerpo = st.text_area("Cuerpo", value=tpl["cuerpo"], height=260, key=f"em_cue_{evento}")
        st.markdown("<div class='kicker' style='margin:.2rem 0 .2rem'>Variables disponibles</div>",
                    unsafe_allow_html=True)
        st.markdown(" ".join(f"`{{{v}}}`" for v in VARIABLES_EMAIL))
        st.markdown("<p class='muted'>Los chips no se insertan solos (limitación de Streamlit): "
                    "copiá el nombre en el cuerpo. Una variable que no exista queda literal en el "
                    "email, no rompe el envío.</p>", unsafe_allow_html=True)
    with cpre:
        st.markdown(f"<div class='kicker' style='margin:0 0 .3rem'>Vista previa · pedido "
                    f"N° {ejemplo['numero']} de {ejemplo['cliente_nombre']}</div>",
                    unsafe_allow_html=True)
        para = ejemplo.get("usuario_email", "cliente@ejemplo.com")
        cc = ", ".join(overrides.pedidos_email_to())
        with st.container(border=True):
            st.markdown(f"<p class='muted' style='margin:0'>Para: {para} · CC: {cc}</p>"
                        f"<p style='font-size:1.15rem; font-weight:600; margin:.2rem 0 .6rem'>"
                        f"{asunto.format_map(vs)}</p>", unsafe_allow_html=True)
            if formato == "html":
                components.html(cuerpo.format_map(vs), height=300, scrolling=True)
            else:
                st.markdown(f"<div style='white-space:pre-wrap; font-size:.95rem'>"
                            f"{cuerpo.format_map(vs)}</div>", unsafe_allow_html=True)
            if evento == "confirmacion":
                try:
                    adj = ejemplo.get("xlsx_filename") or pedidos.nombre_archivo(ejemplo)
                except Exception:  # noqa: BLE001 — pedido sintético sin confirmed_at
                    adj = f"pedido_{ejemplo['cliente_cod']}_{ejemplo['numero']}.xlsx"
                st.markdown(f"<p class='muted' style='margin:.6rem 0 0'>Adjunto: {adj}</p>",
                            unsafe_allow_html=True)

    b1, b2, b3, _ = st.columns([1.1, 1.3, 1.6, 1])
    if b1.button("Guardar plantilla", type="primary", use_container_width=True):
        overrides.set_email_template(evento, {"formato": formato, "asunto": asunto.strip(),
                                              "cuerpo": cuerpo}, _admin_email())
        for k in (f"em_fmt_{evento}", f"em_asu_{evento}", f"em_cue_{evento}"):
            st.session_state.pop(k, None)
        st.toast(f"Plantilla «{EVENTO_LABEL[evento]}» guardada")
        st.rerun()
    if b2.button("Enviarme una prueba", use_container_width=True):
        overrides.set_email_template(evento, {"formato": formato, "asunto": asunto.strip(),
                                              "cuerpo": cuerpo}, _admin_email())
        for k in (f"em_fmt_{evento}", f"em_asu_{evento}", f"em_cue_{evento}"):
            st.session_state.pop(k, None)
        res = email_notif.enviar_prueba(evento, ejemplo, _admin_email())
        if res["enviado"]:
            st.success(f"Prueba enviada a {', '.join(res['destinatarios'])}")
        else:
            st.error(f"No se pudo enviar: {res['error']}")
    if b3.button("Volver al texto por defecto", use_container_width=True):
        overrides.reset_email_template(evento, _admin_email())
        for k in (f"em_fmt_{evento}", f"em_asu_{evento}", f"em_cue_{evento}"):
            st.session_state.pop(k, None)
        st.toast("Plantilla restaurada al texto por defecto")
        st.rerun()
    st.markdown(f"<p class='muted'>«Enviarme una prueba» también guarda la plantilla. La prueba va a "
                f"{_admin_email()}, nunca al cliente.</p>", unsafe_allow_html=True)
