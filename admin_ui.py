"""Sección Administración (solo rol admin): Catálogo, Clientes, Pedidos, Config.

SPECS.md §3-§6. Regla: acá se editan SOLO overrides de Firestore; BQ es readonly.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
import streamlit as st

import auth
import catalog
import db
import email_notif
import fotos
import overrides
import pedidos

log = logging.getLogger(__name__)

PUB_LABELS = {None: "Auto", True: "Publicado", False: "Oculto"}
PUB_VALUES = {v: k for k, v in PUB_LABELS.items()}


def _admin_email() -> str:
    return st.session_state.user["email"]


def page_admin() -> None:
    st.markdown("## Administración")
    tab_cat, tab_cli, tab_ped, tab_cfg = st.tabs(["📚 Catálogo", "👥 Clientes", "📦 Pedidos", "⚙️ Config"])
    with tab_cat:
        _tab_catalogo()
    with tab_cli:
        _tab_clientes()
    with tab_ped:
        _tab_pedidos()
    with tab_cfg:
        _tab_config()


# ---------------------------------------------------------------------------
# Catálogo (SPECS §3)
# ---------------------------------------------------------------------------
def _tab_catalogo() -> None:
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()

    c1, c2, c3, c4 = st.columns([2, 1.2, 1.2, 1.2])
    busq = c1.text_input("Buscar", key="adm_busq", placeholder="código o nombre")
    marca = c2.multiselect("Marca", sorted(df["marca"].dropna().unique()), key="adm_marca")
    temporada = c3.multiselect("Temporada", sorted(df["temporada"].dropna().unique()), key="adm_temp")
    rubro = c4.multiselect("Rubro", sorted(df["rubro"].dropna().unique()), key="adm_rubro")
    c5, c6, c7 = st.columns(3)
    solo_ocultos = c5.checkbox("Solo ocultos", key="adm_ocultos")
    solo_sin_foto = c6.checkbox("Solo sin foto", key="adm_sinfoto")
    solo_editados = c7.checkbox("Solo con overrides", key="adm_editados")

    sub = catalog.filtrar_variantes(df, {"marca": marca, "temporada": temporada, "rubro": rubro}, busq)
    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), marca=("marca", "first"), temporada=("temporada", "first"),
        rubro=("rubro", "first"), stock=("stock", "sum"), variantes=("sku", "count"),
        precio1=("precio1", "first"), publicado=("publicado", "first"), destacado=("destacado", "first"),
    ).reset_index()
    prods["foto"] = prods["producto_cod"].map(lambda c: fotos.foto_principal(c) if fotos.tiene_fotos(c) else "")
    prods["sin_foto"] = prods["foto"] == ""
    prods["editado"] = prods["producto_cod"].map(lambda c: c in ov)
    if solo_ocultos:
        prods = prods[prods["publicado"].map(lambda v: v is False)]
    if solo_sin_foto:
        prods = prods[prods["sin_foto"]]
    if solo_editados:
        prods = prods[prods["editado"]]

    st.caption(f"{len(prods)} productos (con stock neto) · {int(prods['sin_foto'].sum())} sin foto · "
               f"{int(prods['editado'].sum())} con overrides · los ocultos no se muestran a clientes")

    # Acciones en lote sobre lo filtrado
    b1, b2, _ = st.columns([1, 1, 2])
    if b1.button("🙈 Ocultar todo lo filtrado", disabled=prods.empty):
        for cod in prods["producto_cod"]:
            overrides.set_catalogo_override(cod, {"publicado": False}, _admin_email())
        st.toast(f"{len(prods)} productos ocultados", icon="🙈")
        st.rerun()
    if b2.button("👁 Volver a automático (filtrado)", disabled=prods.empty):
        for cod in prods["producto_cod"]:
            overrides.set_catalogo_override(cod, {"publicado": None}, _admin_email())
        st.toast(f"{len(prods)} productos en modo automático", icon="👁")
        st.rerun()

    # Tabla editable (paginada) — publicado/destacado/nombre inline
    por_pag = 50
    n_pag = max(1, -(-len(prods) // por_pag))
    pag = int(st.number_input("Página", 1, n_pag, 1, key="adm_pag"))
    page_df = prods.iloc[(pag - 1) * por_pag: pag * por_pag].copy()
    page_df["publicado_lbl"] = page_df["publicado"].map(PUB_LABELS.get)
    ver = st.session_state.get("adm_editor_ver", 0)
    edited = st.data_editor(
        page_df[["foto", "producto_cod", "nombre", "marca", "temporada", "publicado_lbl", "destacado",
                 "stock", "variantes", "precio1", "editado"]],
        hide_index=True, use_container_width=True, key=f"adm_editor_{pag}_{ver}",
        disabled=["foto", "producto_cod", "marca", "temporada", "stock", "variantes", "precio1", "editado"],
        column_config={
            "foto": st.column_config.ImageColumn("Foto", width="small"),
            "producto_cod": "Código", "nombre": st.column_config.TextColumn("Nombre (editable)"),
            "marca": "Marca", "temporada": "Temp.",
            "publicado_lbl": st.column_config.SelectboxColumn("Publicación", options=list(PUB_VALUES), required=True),
            "destacado": st.column_config.CheckboxColumn("Destacado"),
            "stock": st.column_config.NumberColumn("Stock", format="%d"),
            "variantes": st.column_config.NumberColumn("Var.", format="%d"),
            "precio1": st.column_config.NumberColumn("Precio L1", format="$ %.0f"),
            "editado": st.column_config.CheckboxColumn("Override"),
        },
    )
    if st.button("💾 Guardar cambios de la tabla", type="primary"):
        cambios = 0
        for (_, orig), (_, new) in zip(page_df.iterrows(), edited.iterrows()):
            campos = {}
            if new["publicado_lbl"] != orig["publicado_lbl"]:
                campos["publicado"] = PUB_VALUES[new["publicado_lbl"]]
            if bool(new["destacado"]) != bool(orig["destacado"]):
                campos["destacado"] = bool(new["destacado"])
            if str(new["nombre"]).strip() and str(new["nombre"]) != str(orig["nombre"]):
                campos["nombre"] = str(new["nombre"]).strip()
            if campos:
                overrides.set_catalogo_override(orig["producto_cod"], campos, _admin_email())
                cambios += 1
        st.session_state.adm_editor_ver = ver + 1
        st.toast(f"{cambios} producto(s) actualizados", icon="💾")
        if cambios:
            st.rerun()

    # Edición fina de un producto (descripcion + precios por lista)
    with st.expander("✏️ Editar descripción y precios de un producto"):
        cod = st.selectbox("Producto", prods["producto_cod"],
                           format_func=lambda c: f"{c} — {prods.set_index('producto_cod').loc[c, 'nombre']}"
                           if c in prods["producto_cod"].values else c) if not prods.empty else None
        if cod:
            o = ov.get(cod, {})
            fila = df[df["producto_cod"] == cod].iloc[0]
            with st.form(f"edit_{cod}"):
                nombre = st.text_input("Nombre (vacío = el de Aleph)", value=o.get("nombre") or "")
                descr = st.text_area("Descripción (vacío = la de Aleph)", value=o.get("descripcion") or "",
                                     height=100)
                st.caption("Precios override por lista (0 = usar el de Aleph). Precios Aleph: "
                           + " · ".join(f"L{n}: $ {fila[f'precio{n}']:,.0f}" for n in (1, 2, 3, 4)))
                cols = st.columns(4)
                precios = {}
                for i, n in enumerate((1, 2, 3, 4)):
                    precios[str(n)] = cols[i].number_input(f"Lista {n}", min_value=0.0, step=100.0,
                                                           value=float((o.get("precios") or {}).get(str(n), 0)))
                if st.form_submit_button("Guardar producto", type="primary"):
                    overrides.set_catalogo_override(cod, {
                        "nombre": nombre.strip() or None,
                        "descripcion": descr.strip() or None,
                        "precios": {k: v for k, v in precios.items() if v > 0},
                    }, _admin_email())
                    st.toast(f"{cod} guardado", icon="💾")
                    st.rerun()


# ---------------------------------------------------------------------------
# Clientes (SPECS §4)
# ---------------------------------------------------------------------------
def _listar_usuarios() -> list[dict]:
    out = []
    for snap in db.client().collection(db.COL_USUARIOS).stream():
        d = snap.to_dict() or {}
        d["email"] = snap.id
        out.append(d)
    return sorted(out, key=lambda u: u["email"])


def _tab_clientes() -> None:
    usuarios = _listar_usuarios()
    ovs = overrides.get_clientes_overrides()
    rows = []
    for u in usuarios:
        cod = u.get("cliente_cod")
        o = ovs.get(int(cod), {}) if cod is not None else {}
        rows.append({
            "Email": u["email"], "Rol": u.get("rol", "cliente"), "Activo": u.get("activo", True),
            "Cliente": cod, "Nombre": u.get("nombre_display", ""),
            "Desc. override": o.get("descuento_pct"), "Lista override": o.get("lista_precios"),
            "Último login": (u.get("last_login_at").astimezone(pedidos.TZ).strftime("%d/%m %H:%M")
                             if u.get("last_login_at") else "—"),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Desc./Lista override vacíos = se usa lo de Aleph (dim_cliente). El valor efectivo se ve al editar.")

    col_a, col_b = st.columns(2)

    with col_a, st.expander("✏️ Editar cliente / descuento", expanded=True):
        emails = [u["email"] for u in usuarios]
        sel = st.selectbox("Usuario", emails, key="adm_cli_sel")
        u = next(x for x in usuarios if x["email"] == sel)
        cod = u.get("cliente_cod")
        if cod is None:
            st.info("Este usuario no tiene cliente asociado (admin puro).")
        else:
            efectivo = catalog.get_cliente(int(cod)) or {}
            st.markdown(f"**{efectivo.get('nombre_display', cod)}** — efectivo hoy: "
                        f"lista **{efectivo.get('lista_precios')}** ({efectivo.get('lista_origen')}) · "
                        f"desc **{efectivo.get('descuento', 0):g}%** ({efectivo.get('descuento_origen')})")
            o = ovs.get(int(cod), {})
            with st.form(f"cli_{cod}"):
                usar_desc = st.checkbox("Override de descuento", value=o.get("descuento_pct") is not None)
                desc = st.number_input("Descuento %", 0.0, 100.0, float(o.get("descuento_pct") or efectivo.get("descuento") or 0), step=0.5)
                usar_lista = st.checkbox("Override de lista", value=bool(o.get("lista_precios")))
                lista = st.number_input("Lista de precios", 1, 10, int(o.get("lista_precios") or efectivo.get("lista_precios") or 1))
                notas = st.text_input("Notas", value=o.get("notas") or "")
                if st.form_submit_button("Guardar", type="primary"):
                    overrides.set_cliente_override(int(cod), {
                        "descuento_pct": float(desc) if usar_desc else None,
                        "lista_precios": int(lista) if usar_lista else None,
                        "notas": notas.strip(),
                    }, _admin_email())
                    st.toast("Cliente guardado", icon="💾")
                    st.rerun()
        b1, b2 = st.columns(2)
        if b1.button("🔑 Resetear password", key=f"rst_{sel}"):
            pwd = auth.generar_password()
            auth.cambiar_password(sel, pwd)
            auth.guardar_password_en_secret(sel, pwd)
            st.session_state.adm_pwd_nueva = (sel, pwd)
        if b2.button("⛔ Desactivar" if u.get("activo", True) else "✅ Activar", key=f"act_{sel}"):
            db.usuario_ref(sel).update({"activo": not u.get("activo", True)})
            st.rerun()
        if st.session_state.get("adm_pwd_nueva", (None,))[0] == sel:
            st.success(f"Password nueva de {sel}: `{st.session_state.adm_pwd_nueva[1]}` — "
                       "guardala ahora (también quedó en el secret mayorista-seed-passwords).")

    with col_b, st.expander("➕ Alta de usuario", expanded=True):
        with st.form("alta_usuario", clear_on_submit=True):
            email = st.text_input("Email")
            cod = st.number_input("cliente_cod (0 = sin cliente, admin)", min_value=0, step=1, value=0)
            nombre = st.text_input("Nombre para mostrar")
            rol = st.selectbox("Rol", ["cliente", "admin"])
            if st.form_submit_button("Crear usuario", type="primary"):
                try:
                    if cod:
                        cli = catalog.get_cliente(int(cod))
                        if cli is None:
                            raise ValueError(f"cliente_cod {cod} no existe en dim_cliente")
                        nombre = nombre or cli["nombre_display"]
                    pwd = auth.generar_password()
                    auth.crear_usuario(email, pwd, int(cod) or None, nombre or email, rol=rol)
                    auth.guardar_password_en_secret(email, pwd)
                    st.session_state.adm_pwd_alta = (email, pwd)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
        if st.session_state.get("adm_pwd_alta"):
            e, p = st.session_state.adm_pwd_alta
            st.success(f"Usuario **{e}** creado. Password: `{p}` — guardala ahora "
                       "(también quedó en el secret mayorista-seed-passwords).")


# ---------------------------------------------------------------------------
# Pedidos (SPECS §5)
# ---------------------------------------------------------------------------
def _tab_pedidos() -> None:
    with st.spinner("Buscando pedidos..."):
        lista = pedidos.listar_pedidos(None)
    if not lista:
        st.info("No hay pedidos todavía.")
        return
    c1, c2, c3 = st.columns(3)
    estados = c1.multiselect("Estado", sorted({p["estado"] for p in lista}), key="adm_ped_est")
    clientes = c2.multiselect("Cliente", sorted({f"{p['cliente_cod']} · {p['cliente_nombre']}" for p in lista}),
                              key="adm_ped_cli")
    desde = c3.date_input("Desde", value=None, key="adm_ped_desde")
    filt = [p for p in lista
            if (not estados or p["estado"] in estados)
            and (not clientes or f"{p['cliente_cod']} · {p['cliente_nombre']}" in clientes)
            and (not desde or p["confirmed_at"].astimezone(pedidos.TZ).date() >= desde)]
    st.dataframe(pd.DataFrame([{
        "N°": p["numero"], "Fecha": p.get("fecha_str", ""), "Cliente": f"{p['cliente_cod']} · {p['cliente_nombre']}",
        "Unidades": p["unidades"], "Total": p["total"], "Estado": p["estado"],
        "Email": "✅" if (p.get("email") or {}).get("enviado") else "❌",
    } for p in filt]), hide_index=True, use_container_width=True,
        column_config={"Total": st.column_config.NumberColumn(format="$ %.0f")})
    if not filt:
        return
    sel = st.selectbox("Pedido N°", [p["numero"] for p in filt], key="adm_ped_sel")
    p = next(x for x in filt if x["numero"] == sel)
    st.markdown(f"**N° {p['numero']}** · {p['fecha_str']} · {p['cliente_nombre']} · "
                f"$ {p['total']:,.0f} · estado **{p['estado']}**")
    for h in p.get("historial", []):
        st.caption(f"→ {h['estado']} por {h['por']} el {h['en'].astimezone(pedidos.TZ):%d/%m %H:%M}")
    st.dataframe(pd.DataFrame(p["items"])[["producto_cod", "producto_nombre", "color", "talle", "cantidad",
                                            "precio_unit", "subtotal"]], hide_index=True, use_container_width=True)
    cols = st.columns(4)
    for i, nuevo in enumerate(pedidos.ESTADOS_SIGUIENTES.get(p["estado"], [])):
        if cols[i].button(f"Marcar {nuevo}", key=f"est_{sel}_{nuevo}", type="primary" if nuevo == "procesado" else "secondary"):
            pedidos.cambiar_estado(sel, nuevo, _admin_email())
            st.toast(f"Pedido {sel} → {nuevo}", icon="✅")
            st.rerun()
    if cols[2].button("📧 Reenviar email", key=f"mail_{sel}"):
        try:
            data = pedidos.descargar_backup(p["xlsx_gcs_path"]) if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)
            res = email_notif.enviar_confirmacion(p, data, p["xlsx_filename"])
            st.success(f"Reenviado a {', '.join(res['destinatarios'])}") if res["enviado"] else st.error(res["error"])
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    if cols[3].download_button("⬇️ Excel", data=(pedidos.descargar_backup(p["xlsx_gcs_path"])
                                                  if p.get("xlsx_gcs_path") else pedidos.generar_excel(p)),
                               file_name=p["xlsx_filename"], key=f"dl_{sel}"):
        pass


# ---------------------------------------------------------------------------
# Config (SPECS §6)
# ---------------------------------------------------------------------------
def _tab_config() -> None:
    cfg = overrides.get_config()
    with st.form("config_global"):
        email_to = st.text_input("Email(s) de Chimola que reciben pedidos (separar con coma; vacío = usar el default del deploy)",
                                 value=cfg.get("pedidos_email_to") or "")
        banner = st.text_area("Banner para clientes (vacío = no se muestra)", value=cfg.get("banner_texto") or "", height=80)
        descvta = st.checkbox("Aplicar además el descuento por artículo de Aleph (descvta, como el Woo)",
                              value=bool(cfg.get("aplicar_descvta")))
        minimo = st.number_input("Mínimo de unidades por pedido (0 = sin mínimo)", min_value=0, step=1,
                                 value=int(cfg.get("minimo_pedido_unidades") or 0))
        if st.form_submit_button("Guardar configuración", type="primary"):
            overrides.set_config({
                "pedidos_email_to": email_to.strip() or None,
                "banner_texto": banner.strip(),
                "aplicar_descvta": bool(descvta),
                "minimo_pedido_unidades": int(minimo) or None,
            }, _admin_email())
            st.toast("Configuración guardada", icon="💾")
            st.rerun()
    st.caption(f"En DEV los emails se redirigen a EMAIL_OVERRIDE_TO ({'activo' if bool(__import__('config').EMAIL_OVERRIDE_TO) else 'inactivo'}).")
