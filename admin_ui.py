"""Sección Administración (solo rol admin) — estilo wp-admin/Woo.

Inicio (KPIs) · Catálogo (selección + lote + editor modal con variantes) ·
Clientes · Pedidos (click en fila, estados con color) · Config.
SPECS.md §3-§6. Acá se editan SOLO overrides de Firestore; BQ es readonly.
"""
from __future__ import annotations

import datetime as dt
import logging
import zoneinfo

import pandas as pd
import streamlit as st

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

PUB_LABELS = {None: "⚪ Auto", True: "🟢 Publicado", False: "🙈 Oculto"}
ESTADO_BADGE = {"confirmado": ("🟡", "#b7791f", "#fef5e7"), "procesado": ("🟢", "#276749", "#e6f4ea"),
                "cancelado": ("🔴", "#9b2c2c", "#fdecea")}
SECCIONES = ["inicio", "catalogo", "clientes", "pedidos", "config"]


def _admin_email() -> str:
    return st.session_state.user["email"]


def _badge_estado(estado: str) -> str:
    emoji, fg, bg = ESTADO_BADGE.get(estado, ("⚪", "#555", "#eee"))
    return (f"<span style='background:{bg};color:{fg};padding:.15rem .6rem;border-radius:999px;"
            f"font-weight:700;font-size:.8rem'>{emoji} {estado.upper()}</span>")


def page_admin() -> None:
    st.markdown("## Administración")
    conteo = pedidos.contar_por_estado()
    sin_procesar = conteo.get("confirmado", 0)
    labels = {"inicio": "🏠 Inicio", "catalogo": "📚 Catálogo", "clientes": "👥 Clientes",
              "pedidos": "📦 Pedidos" + (f" · {sin_procesar} sin procesar" if sin_procesar else ""),
              "config": "⚙️ Config"}
    sec = st.segmented_control("Sección", SECCIONES, format_func=lambda s: labels[s],
                               key="adm_nav", label_visibility="collapsed", default="inicio")
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


def _sec_inicio() -> None:
    with st.spinner("Calculando..."):
        lista = pedidos.listar_pedidos(None)
        k = _kpis(lista, dt.datetime.now(dt.timezone.utc))
        df = catalog.variantes_admin()
    c = st.columns(5)
    c[0].metric("🟡 Sin procesar", k["sin_procesar"])
    c[1].metric("Pedidos del mes", k["pedidos_mes"])
    c[2].metric("Ventas del mes (sin IVA)", f"$ {k['monto_mes']:,.0f}".replace(",", "."))
    c[3].metric("Unidades del mes", f"{k['unidades_mes']:,}".replace(",", "."))
    c[4].metric("Clientes que pidieron", k["clientes_mes"])

    st.markdown("#### Salud del catálogo")
    prods = df.groupby("producto_cod").agg(publicado=("publicado", "first"), precio1=("precio1", "first")).reset_index()
    sin_foto = int((~prods["producto_cod"].map(fotos.tiene_fotos)).sum())
    c = st.columns(5)
    c[0].metric("Productos con stock", len(prods))
    c[1].metric("🙈 Ocultos", int(prods["publicado"].map(lambda v: v is False).sum()))
    c[2].metric("Sin foto", sin_foto)
    c[3].metric("Sin precio L1", int((prods["precio1"] <= 0).sum()))
    c[4].metric("Con overrides", len(overrides.get_catalogo_overrides()))

    if k["top"]:
        st.markdown("#### Top productos del mes")
        st.dataframe(pd.DataFrame(k["top"], columns=["Código", "Producto", "Unidades"]),
                     hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def _sec_catalogo() -> None:
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()

    c1, c2, c3, c4 = st.columns([2, 1.2, 1.2, 1.2])
    busq = c1.text_input("Buscar", key="adm_busq", placeholder="código o nombre")
    marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="adm_marca")
    temporada = c3.multiselect("Temporada", sorted(df["temporada"].dropna().unique()), key="adm_temp")
    rubro = c4.multiselect("Rubro", sorted(df["rubro"].dropna().unique()), key="adm_rubro")
    sub = catalog.filtrar_variantes(df, {"marca": marca, "temporada": temporada, "rubro": rubro}, busq)

    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), marca=("marca", "first"), temporada=("temporada", "first"),
        rubro=("rubro", "first"), stock=("stock", "sum"), variantes=("sku", "count"),
        precio1=("precio1", "first"), publicado=("publicado", "first"), destacado=("destacado", "first"),
    ).reset_index()
    prods["sin_foto"] = ~prods["producto_cod"].map(fotos.tiene_fotos)
    prods["editado"] = prods["producto_cod"].map(lambda c: c in ov)

    # Filtros rápidos tipo Woo, con contadores
    counts = {
        "Todos": len(prods),
        "Publicados": int(prods["publicado"].map(lambda v: v is not False).sum()),
        "Ocultos": int(prods["publicado"].map(lambda v: v is False).sum()),
        "Destacados": int(prods["destacado"].sum()),
        "Sin foto": int(prods["sin_foto"].sum()),
        "Con override": int(prods["editado"].sum()),
    }
    pill = st.pills("Filtro rápido", list(counts), key="adm_pill", label_visibility="collapsed",
                    format_func=lambda p: f"{p} ({counts[p]})", default="Todos") or "Todos"
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

    # Paginación ‹ x/y ›
    por_pag = 50
    n_pag = max(1, -(-len(prods) // por_pag))
    pag = min(st.session_state.get("adm_pag", 1), n_pag)
    page_df = prods.iloc[(pag - 1) * por_pag: pag * por_pag].copy()
    page_df["foto"] = page_df["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    page_df["pub"] = page_df["publicado"].map(PUB_LABELS.get)
    page_df["dest"] = page_df["destacado"].map(lambda v: "⭐" if v else "")
    page_df["ovr"] = page_df["editado"].map(lambda v: "✏️" if v else "")

    ev = st.dataframe(
        page_df[["foto", "producto_cod", "nombre", "marca", "temporada", "pub", "dest", "stock", "variantes", "precio1", "ovr"]],
        hide_index=True, use_container_width=True, key="adm_tabla",
        on_select="rerun", selection_mode="multi-row",
        column_config={
            "foto": st.column_config.ImageColumn("", width="small"),
            "producto_cod": "Código", "nombre": "Nombre", "marca": "Marca", "temporada": "Temp.",
            "pub": "Publicación", "dest": "⭐", "ovr": "✏️",
            "stock": st.column_config.NumberColumn("Stock", format="%d"),
            "variantes": st.column_config.NumberColumn("Var.", format="%d"),
            "precio1": st.column_config.NumberColumn("Precio L1", format="$ %.0f"),
        })
    sel_cods = [page_df.iloc[i]["producto_cod"] for i in ev.selection.rows]

    b = st.columns([1.3, 1, 1, 1, 1, 1.4, 2])
    b[0].markdown(f"**{len(sel_cods)} seleccionado(s)**" if sel_cods
                  else f"<span class='muted'>Seleccioná filas con el checkbox · pág {pag}/{n_pag}</span>",
                  unsafe_allow_html=True)
    if b[1].button("✏️ Editar", disabled=len(sel_cods) != 1, use_container_width=True):
        _editar_producto(sel_cods[0])
    if b[2].button("🙈 Ocultar", disabled=not sel_cods, use_container_width=True):
        _aplicar_lote(sel_cods, {"publicado": False})
    if b[3].button("⚪ Auto", disabled=not sel_cods, use_container_width=True):
        _aplicar_lote(sel_cods, {"publicado": None})
    if b[4].button("⭐ Destacar", disabled=not sel_cods, use_container_width=True):
        _aplicar_lote(sel_cods, {"destacado": True})
    if b[5].button("☆ Quitar destacado", disabled=not sel_cods, use_container_width=True):
        _aplicar_lote(sel_cods, {"destacado": False})
    with b[6]:
        p1, p2, p3 = st.columns(3)
        if p1.button("‹", disabled=pag <= 1):
            st.session_state.adm_pag = pag - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center;padding-top:.4rem'>{pag} / {n_pag}</div>", unsafe_allow_html=True)
        if p3.button("›", disabled=pag >= n_pag):
            st.session_state.adm_pag = pag + 1
            st.rerun()

    with st.expander("Acciones sobre TODO lo filtrado"):
        st.caption(f"Afecta a los {len(prods)} productos del filtro actual (todas las páginas).")
        f1, f2 = st.columns(2)
        if f1.button("🙈 Ocultar todo lo filtrado", disabled=prods.empty):
            _aplicar_lote(list(prods["producto_cod"]), {"publicado": False})
        if f2.button("⚪ Todo lo filtrado a automático", disabled=prods.empty):
            _aplicar_lote(list(prods["producto_cod"]), {"publicado": None})


def _aplicar_lote(cods: list[str], campos: dict) -> None:
    if len(cods) > 10:
        _confirmar_lote(cods, campos)
        return
    for cod in cods:
        overrides.set_catalogo_override(cod, campos, _admin_email())
    st.toast(f"{len(cods)} producto(s) actualizados", icon="💾")
    st.rerun()


@st.dialog("Confirmar acción masiva")
def _confirmar_lote(cods: list[str], campos: dict) -> None:
    st.warning(f"Vas a aplicar **{campos}** a **{len(cods)} productos**. ¿Seguro?")
    c1, c2 = st.columns(2)
    if c1.button("✅ Sí, aplicar", type="primary", use_container_width=True):
        for cod in cods:
            overrides.set_catalogo_override(cod, campos, _admin_email())
        st.toast(f"{len(cods)} producto(s) actualizados", icon="💾")
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


@st.dialog("Editar producto", width="large")
def _editar_producto(cod: str) -> None:
    df = catalog.variantes_admin()
    filas = df[df["producto_cod"] == cod].sort_values(["color", "talle"])
    if filas.empty:
        st.error("Producto sin stock neto hoy (no está en el catálogo actual).")
        return
    f0 = filas.iloc[0]
    o = overrides.get_catalogo_overrides().get(cod, {})
    raw = catalog.load_variantes()   # stock BQ sin overrides, para referencia
    stock_bq = {r["sku"]: int(r["stock"]) for _, r in raw[raw["producto_cod"] == cod].iterrows()}

    ci, cd = st.columns([1, 2.2])
    with ci:
        st.image(fotos.foto_principal(cod), use_container_width=True)
        n_fotos = len(fotos.indice_fotos().get(cod.upper(), []))
        st.caption(f"**{cod}** · {f0['marca']} · {f0['temporada']} · {f0['rubro']} · {n_fotos} foto(s)")
        if o:
            st.caption(f"✏️ Overrides por {o.get('updated_by', '?')}")
    with cd:
        nombre = st.text_input("Nombre (vacío = Aleph)", value=o.get("nombre") or "",
                               placeholder=str(f0["producto_nombre"]))
        descr = st.text_area("Descripción (vacío = Aleph)", value=o.get("descripcion") or "", height=80)
        pcols = st.columns(4)
        precios = {}
        for i, n in enumerate((1, 2, 3, 4)):
            aleph = float(raw[raw.producto_cod == cod].iloc[0][f"precio{n}"]) if not raw[raw.producto_cod == cod].empty else 0
            precios[str(n)] = pcols[i].number_input(f"Precio L{n}", min_value=0.0, step=100.0,
                                                    value=float((o.get("precios") or {}).get(str(n), 0)),
                                                    help=f"Aleph: $ {aleph:,.0f} · 0 = usar Aleph")
        r1, r2, r3 = st.columns([1.4, 1, 1])
        pub = r1.radio("Publicación", list(PUB_LABELS.values()),
                       index=list(PUB_LABELS).index(o.get("publicado", None) if o.get("publicado") in (True, False) else None),
                       horizontal=True)
        dest = r2.checkbox("⭐ Destacado", value=bool(o.get("destacado")))
        ub = r3.number_input("Múltiplo (U.B.)", min_value=0, step=1, value=int(o.get("ub") or 0),
                             help="Cantidad mínima y múltiplo de compra por variante (como el u.b del Woo). 0 = libre")

    st.markdown("**Variantes** — stock/precio manual pisan a Aleph (vacío = automático). "
                "⚠ Con stock manual el sitio deja de validar contra el stock real.")
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
            "precio_manual_l1": st.column_config.NumberColumn("Precio manual L1", min_value=0.0, step=100.0, format="$ %.0f"),
        })

    g1, g2 = st.columns([1, 1])
    if g1.button("💾 Guardar producto", type="primary", use_container_width=True):
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
        overrides.set_catalogo_override(cod, {
            "nombre": nombre.strip() or None, "descripcion": descr.strip() or None,
            "precios": {k: v for k, v in precios.items() if v > 0},
            "publicado": {v: k for k, v in PUB_LABELS.items()}[pub],
            "destacado": bool(dest), "ub": int(ub) or None, "variantes": variantes,
        }, _admin_email())
        st.toast(f"{cod} guardado", icon="💾")
        st.rerun()
    if g2.button("🗑 Quitar TODOS los overrides", use_container_width=True):
        overrides.quitar_catalogo_override(cod)
        st.toast(f"{cod} volvió 100% a Aleph", icon="🗑")
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


def _sec_clientes() -> None:
    usuarios = _listar_usuarios()
    cods = sorted({int(u["cliente_cod"]) for u in usuarios if u.get("cliente_cod") is not None})
    with st.spinner("Leyendo clientes..."):
        efectivos = catalog.get_clientes(cods)
    rows = []
    for u in usuarios:
        cod = u.get("cliente_cod")
        e = efectivos.get(int(cod)) if cod is not None else None
        rows.append({
            "Email": u["email"], "Rol": u.get("rol", "cliente"), "Activo": "✅" if u.get("activo", True) else "⛔",
            "Cliente": cod, "Nombre": (e or {}).get("nombre_display", u.get("nombre_display", "")),
            "Lista": f"{e['lista_precios']} ({e['lista_origen']})" if e else "—",
            "Desc %": f"{e['descuento']:g} ({e['descuento_origen']})" if e else "—",
            "Último login": (u.get("last_login_at").astimezone(TZ).strftime("%d/%m %H:%M")
                             if u.get("last_login_at") else "—"),
        })
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                      key="adm_cli_tabla", on_select="rerun", selection_mode="single-row")
    sel = usuarios[ev.selection.rows[0]] if ev.selection.rows else None
    c1, c2, _ = st.columns([1, 1, 2])
    if c1.button("✏️ Editar seleccionado", disabled=sel is None):
        _editar_cliente(sel["email"])
    if c2.button("➕ Nuevo usuario"):
        _alta_usuario()
    if st.session_state.get("adm_pwd_msg"):
        e, p = st.session_state.pop("adm_pwd_msg")
        st.success(f"Password de **{e}**: `{p}` — guardala ahora (también quedó en el secret "
                   "`mayorista-seed-passwords`).")


@st.dialog("Editar cliente", width="large")
def _editar_cliente(email: str) -> None:
    u = auth.get_usuario(email)
    if not u:
        st.error("Usuario no encontrado")
        return
    cod = u.get("cliente_cod")
    st.markdown(f"**{email}** · rol `{u.get('rol', 'cliente')}`")
    if cod is not None:
        e = catalog.get_cliente(int(cod)) or {}
        st.caption(f"{e.get('nombre_display', cod)} · efectivo hoy: lista **{e.get('lista_precios')}** "
                   f"({e.get('lista_origen')}) · desc **{e.get('descuento', 0):g}%** ({e.get('descuento_origen')})")
        o = overrides.get_clientes_overrides().get(int(cod), {})
        with st.form(f"cli_{cod}"):
            usar_desc = st.checkbox("Override de descuento", value=o.get("descuento_pct") is not None)
            desc = st.number_input("Descuento %", 0.0, 100.0,
                                   float(o.get("descuento_pct") or e.get("descuento") or 0), step=0.5)
            usar_lista = st.checkbox("Override de lista", value=bool(o.get("lista_precios")))
            lista = st.number_input("Lista de precios", 1, 10, int(o.get("lista_precios") or e.get("lista_precios") or 1))
            notas = st.text_input("Notas", value=o.get("notas") or "")
            if st.form_submit_button("💾 Guardar", type="primary", use_container_width=True):
                overrides.set_cliente_override(int(cod), {
                    "descuento_pct": float(desc) if usar_desc else None,
                    "lista_precios": int(lista) if usar_lista else None,
                    "notas": notas.strip(),
                }, _admin_email())
                st.toast("Cliente guardado", icon="💾")
                st.rerun()
    else:
        st.info("Usuario sin cliente asociado (admin puro).")
    b1, b2 = st.columns(2)
    if b1.button("🔑 Resetear password", use_container_width=True):
        pwd = auth.generar_password()
        auth.cambiar_password(email, pwd)
        auth.guardar_password_en_secret(email, pwd)
        st.session_state.adm_pwd_msg = (email, pwd)
        st.rerun()
    if b2.button("⛔ Desactivar" if u.get("activo", True) else "✅ Activar", use_container_width=True):
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
        st.info("No hay pedidos todavía.")
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
                              key="adm_ped_cli")
    desde = c2.date_input("Desde", value=None, key="adm_ped_desde")
    filt = [p for p in lista
            if (pill == "Todos" or p["estado"] == pill.lower())
            and (not clientes or f"{p['cliente_cod']} · {p['cliente_nombre']}" in clientes)
            and (not desde or p["confirmed_at"].astimezone(TZ).date() >= desde)]
    tabla = pd.DataFrame([{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""),
        "Cliente": f"{p['cliente_cod']} · {p['cliente_nombre'][:40]}",
        "Unidades": p["unidades"], "Total": p["total"],
        "Estado": f"{ESTADO_BADGE.get(p['estado'], ('⚪',))[0]} {p['estado']}",
        "Email": "✅" if (p.get("email") or {}).get("enviado") else "—",
    } for p in filt])
    ev = st.dataframe(tabla, hide_index=True, use_container_width=True, key="adm_ped_tabla",
                      on_select="rerun", selection_mode="single-row",
                      column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})
    if not ev.selection.rows:
        st.caption("Click en una fila para ver el detalle.")
        return
    p = filt[ev.selection.rows[0]]

    st.markdown(f"### Pedido N° {p['numero']} &nbsp; {_badge_estado(p['estado'])}", unsafe_allow_html=True)
    st.markdown(f"{p['fecha_str']} · **{p['cliente_nombre']}** (cliente {p['cliente_cod']}) · "
                f"{p['usuario_email']} · {p['unidades']} u. · **$ {p['total']:,.0f}** "
                f"(desc. {p['descuento_pct']:g}%)".replace(",", "."))
    if p.get("observaciones"):
        st.caption(f"Obs: {p['observaciones']}")
    for h in p.get("historial", []):
        st.caption(f"🕘 {h['en'].astimezone(TZ):%d/%m %H:%M} — **{h['estado']}** por {h['por']}")

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
            st.toast(f"Pedido {p['numero']} → {nuevo}", icon="✅")
            st.rerun()
    if cols[2].button("📧 Reenviar email", key=f"mail_{p['numero']}", use_container_width=True):
        try:
            data = pedidos.descargar_backup(p["xlsx_gcs_path"]) if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)
            res = email_notif.enviar_confirmacion(p, data, p["xlsx_filename"])
            st.success(f"Reenviado a {', '.join(res['destinatarios'])}") if res["enviado"] else st.error(res["error"])
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    cols[3].download_button("⬇️ Excel", data=(pedidos.descargar_backup(p["xlsx_gcs_path"])
                                              if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)),
                            file_name=p["xlsx_filename"], key=f"dl_{p['numero']}", use_container_width=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _sec_config() -> None:
    cfg = overrides.get_config()
    with st.form("config_global"):
        email_to = st.text_input("Email(s) de Chimola que reciben pedidos (coma; vacío = default del deploy)",
                                 value=cfg.get("pedidos_email_to") or "")
        banner = st.text_area("Banner para clientes (vacío = no se muestra)", value=cfg.get("banner_texto") or "", height=80)
        c1, c2, c3 = st.columns(3)
        descvta = c1.checkbox("Aplicar descvta de Aleph (como el Woo)", value=bool(cfg.get("aplicar_descvta")))
        minimo = c2.number_input("Mínimo de unidades por pedido (0 = sin mínimo)", min_value=0, step=1,
                                 value=int(cfg.get("minimo_pedido_unidades") or 0))
        iva = c3.number_input("IVA % informativo (0 = ocultar)", min_value=0.0, max_value=30.0, step=0.5,
                              value=float(cfg.get("iva_pct") or 0),
                              help="Las listas de Aleph son sin IVA. Se muestra como línea aparte en carrito/Excel/email.")
        if st.form_submit_button("💾 Guardar configuración", type="primary"):
            overrides.set_config({
                "pedidos_email_to": email_to.strip() or None,
                "banner_texto": banner.strip(),
                "aplicar_descvta": bool(descvta),
                "minimo_pedido_unidades": int(minimo) or None,
                "iva_pct": float(iva),
            }, _admin_email())
            st.toast("Configuración guardada", icon="💾")
            st.rerun()
    if appconfig.EMAIL_OVERRIDE_TO:
        st.caption(f"⚠ DEV: todos los emails se redirigen a {appconfig.EMAIL_OVERRIDE_TO}.")
