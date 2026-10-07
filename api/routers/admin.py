"""Administración (solo rol admin). Réplica 1:1 de lo que hacía `admin_ui.py` (Streamlit),
sobre los mismos módulos: overrides, catalog, pedidos, auth, email_notif, aleph_import,
reposicion, sitio. Nunca escribe en BigQuery."""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

import adminlib
import aleph_import
import auth as auth_mod
import catalog
import db
import email_notif
import fotos
import overrides
import pedidos as ped
import reposicion as repo
import sitio

from api import colores, deps

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(deps.ctx_admin)])

PUB_LABELS = {None: "Automático", True: "Publicado", False: "Oculto"}
EVENTO_LABEL = {"confirmacion": "Confirmación de pedido", "procesado": "Cambio a procesado",
                "cancelado": "Cancelación", "modificado": "Modificación"}
VARIABLES_EMAIL = ("numero", "cliente", "cliente_cod", "usuario", "contacto", "fecha", "unidades",
                   "subtotal", "descuento_pct", "descuento_monto", "total", "iva_pct", "iva_monto",
                   "total_con_iva", "lineas_iva", "lista_precios", "observaciones", "detalle", "quien",
                   "estado", "cambios", "ahorro_descvta", "linea_ahorro")


def _pub(v):
    return v if v in (True, False) else None


def _j(o):
    return deps.jsonable(o)


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------
@router.get("/inicio")
def inicio():
    lista = ped.listar_pedidos(None)
    k = adminlib.kpis(lista, dt.datetime.now(dt.timezone.utc))
    df = catalog.variantes_admin()
    prods = df.groupby("producto_cod").agg(publicado=("publicado", "first"), precio1=("precio1", "first")).reset_index()
    return {
        **_j(k),
        "salud": {
            "productos": int(len(prods)),
            "ocultos": int(prods["publicado"].map(lambda v: v is False).sum()),
            "sin_foto": int((~prods["producto_cod"].map(fotos.tiene_fotos)).sum()),
            "sin_precio_l1": int((prods["precio1"] <= 0).sum()),
            "con_overrides": len(overrides.get_catalogo_overrides()),
        },
        "catalogo_hace_seg": catalog.catalogo_actualizado_hace(),
    }


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
def _prods_admin(q: str, marca, temporada, categoria, rubro, pill: str):
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()
    sub = catalog.filtrar_variantes(df, {"marca": marca or [], "temporada": temporada or [],
                                         "categoria": categoria or [], "rubro": rubro or []}, q or "")
    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), marca=("marca", "first"), temporada=("temporada", "first"),
        rubro=("rubro", "first"), categoria=("categoria", "first"), stock=("stock", "sum"),
        variantes=("sku", "count"), precio1=("precio1", "first"),
        publicado=("publicado", "first"), destacado=("destacado", "first"),
    ).reset_index()
    prods["sin_foto"] = ~prods["producto_cod"].map(fotos.tiene_fotos)
    prods["editado"] = prods["producto_cod"].map(lambda c: c in ov)
    counts = {
        "todos": len(prods),
        "publicados": int(prods["publicado"].map(lambda v: v is not False).sum()),
        "ocultos": int(prods["publicado"].map(lambda v: v is False).sum()),
        "destacados": int(prods["destacado"].fillna(False).astype(bool).sum()),
        "sin_foto": int(prods["sin_foto"].sum()),
        "con_override": int(prods["editado"].sum()),
    }
    if pill == "publicados":
        prods = prods[prods["publicado"].map(lambda v: v is not False)]
    elif pill == "ocultos":
        prods = prods[prods["publicado"].map(lambda v: v is False)]
    elif pill == "destacados":
        prods = prods[prods["destacado"].fillna(False).astype(bool)]
    elif pill == "sin_foto":
        prods = prods[prods["sin_foto"]]
    elif pill == "con_override":
        prods = prods[prods["editado"]]
    return df, sub, prods, counts


@router.get("/catalogo")
def catalogo(q: str = "", marca: list[str] | None = Query(None), temporada: list[str] | None = Query(None),
             categoria: list[str] | None = Query(None), rubro: list[str] | None = Query(None),
             pill: str = "todos", page: int = 1, per_page: int = 50):
    df, _sub, prods, counts = _prods_admin(q, marca, temporada, categoria, rubro, pill)
    total = len(prods)
    per_page = max(1, min(per_page, 200))
    pag = prods.iloc[(page - 1) * per_page: page * per_page]
    items = []
    for _, r in pag.iterrows():
        cod = r["producto_cod"]
        items.append({
            "producto_cod": cod, "nombre": r["nombre"], "marca": r["marca"], "temporada": r["temporada"],
            "rubro": r["rubro"], "categoria": r["categoria"], "stock": int(r["stock"]), "variantes": int(r["variantes"]),
            "precio1": _j(r["precio1"]), "publicado": _pub(r["publicado"]), "publicacion": PUB_LABELS[_pub(r["publicado"])],
            "destacado": bool(r["destacado"]) if pd.notna(r["destacado"]) else False,
            "sin_foto": bool(r["sin_foto"]), "editado": bool(r["editado"]),
            "foto": fotos.url_foto_publica(cod, fotos._portada_filename(cod, fotos.indice_fotos().get(cod.upper(), []))) if not r["sin_foto"] else None,
        })
    return {
        "total": total, "page": page, "per_page": per_page, "pages": max(1, math.ceil(total / per_page)),
        "items": items, "counts": counts,
        "cods_filtrados": prods["producto_cod"].tolist(),
        "facetas": {k: sorted(df[k].dropna().unique().tolist()) for k in ("marca", "temporada", "categoria", "rubro")},
    }


class LoteIn(BaseModel):
    cods: list[str]
    campos: dict


@router.post("/catalogo/lote")
def lote(body: LoteIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    campos = {k: v for k, v in body.campos.items() if k in ("publicado", "destacado")}
    if not campos or not body.cods:
        raise HTTPException(422, "Nada para aplicar")
    n = overrides.set_masivo(body.cods, campos, c.email)
    return {"n": n}


@router.get("/catalogo/fotomap")
def fotomap(q: str = "", marca: list[str] | None = Query(None), temporada: list[str] | None = Query(None),
            categoria: list[str] | None = Query(None), rubro: list[str] | None = Query(None), pill: str = "todos"):
    _df, sub, prods, _c = _prods_admin(q, marca, temporada, categoria, rubro, pill)
    sub = sub[sub["producto_cod"].isin(prods["producto_cod"])]
    rows = fotos.mapeo_variantes(sub[["producto_cod", "sku", "color", "talle"]].to_dict("records"),
                                 overrides_por_prod=overrides.get_catalogo_overrides())
    cnt: dict[str, int] = {}
    for r in rows:
        cnt[r["origen"]] = cnt.get(r["origen"], 0) + 1
    return {"rows": rows, "counts": cnt, "n": len(rows)}


@router.get("/productos/{cod}")
def producto_admin(cod: str):
    cod = cod.upper()
    df = catalog.variantes_admin()
    filas = df[df["producto_cod"] == cod].copy()
    if filas.empty:
        raise HTTPException(404, "Producto sin stock neto hoy (no está en el catálogo actual)")
    filas["_tk"] = filas["talle"].map(catalog.talle_key)
    filas = filas.sort_values(["color", "_tk"])
    f0 = filas.iloc[0]
    o = overrides.get_catalogo_overrides().get(cod, {})
    raw = catalog.load_variantes()
    raw_p = raw[raw["producto_cod"] == cod]
    stock_bq = {r["sku"]: int(r["stock"]) for _, r in raw_p.iterrows()}
    r0 = raw_p.iloc[0] if not raw_p.empty else None
    files = sorted(fotos.indice_fotos().get(cod, []))
    colores_prod = list(dict.fromkeys(filas["color"]))
    mapa_auto = fotos.foto_por_color(cod, colores_prod, files, None) if files else {}
    vov = o.get("variantes") or {}
    return {
        "producto_cod": cod,
        "efectivo": {"nombre": f0["producto_nombre"], "descripcion": _j(f0.get("descripcion")) or "",
                     "marca": f0["marca"], "temporada": f0["temporada"], "rubro": f0["rubro"], "categoria": f0.get("categoria"),
                     "precios": {str(n): _j(f0.get(f"precio{n}")) for n in (1, 2, 3, 4)}},
        "aleph": {"nombre": str(r0["producto_nombre"]) if r0 is not None else "",
                  "descripcion": str(r0.get("descripcion") or "") if r0 is not None else "",
                  "precios": {str(n): float(r0[f"precio{n}"]) if r0 is not None else 0 for n in (1, 2, 3, 4)},
                  "descvta": float(r0.get("descvta") or 0) if r0 is not None else 0},
        "override": _j({k: v for k, v in o.items() if k not in ("updated_at",)}) | {"updated_at": _j(o.get("updated_at"))},
        "variantes": [{
            "sku": r["sku"], "color": r["color"], "talle": r["talle"], "ean": _j(r["ean"]),
            "stock": 0 if vov.get(r["sku"], {}).get("oculta") else int(r["stock"]),
            "stock_aleph": None if r.get("es_manual") else stock_bq.get(r["sku"], 0),
            "precio1": _j(r["precio1"]), "es_manual": bool(r.get("es_manual", False)),
            "ov": _j(vov.get(r["sku"], {})),
        } for _, r in filas.iterrows()],
        "fotos": {"files": files, "n": len(files), "portada_auto": fotos._portada_filename(cod, files),
                  "portada": o.get("portada") if o.get("portada") in files else None,
                  "principal": fotos.foto_principal(cod) if files else None,
                  "urls": {fn: fotos.url_foto_publica(cod, fn) for fn in files},
                  "por_color": [{"color": c, "auto": mapa_auto.get(fotos.norm(c)),
                                 "manual": (o.get("fotos_color") or {}).get(fotos.norm(c)), "norm": fotos.norm(c)} for c in colores_prod]},
        "colores": [{"color": c, "hex": colores.hex_de(c)} for c in colores_prod],
        "clasificacion": {"categoria": f0.get("categoria"), "rubro": f0["rubro"],
                          "categoria_aleph": str(r0.get("tipo_producto") or "") if r0 is not None else "",
                          "rubro_aleph": str(r0["rubro"]) if r0 is not None else "",
                          "opciones_categoria": sorted(df["categoria"].dropna().unique().tolist()),
                          "opciones_rubro": sorted(df["rubro"].dropna().unique().tolist())},
        "relacionados": _relacionados_info(o.get("relacionados") or [], df),
        "relacionados_inversos": _relacionados_info(
            [c for c, oo in overrides.get_catalogo_overrides().items() if cod in (oo.get("relacionados") or [])], df),
    }


def _relacionados_info(cods: list[str], df: pd.DataFrame) -> list[dict]:
    out = []
    for c in cods:
        sub = df[df["producto_cod"] == c]
        files = fotos.indice_fotos().get(c.upper(), [])
        fn = fotos._portada_filename(c, files) if files else None
        out.append({"producto_cod": c, "nombre": sub.iloc[0]["producto_nombre"] if not sub.empty else "(sin stock hoy)",
                    "foto": fotos.url_foto_publica(c, fn) if fn else None, "en_catalogo": not sub.empty})
    return out


class ProductoIn(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    precios: dict[str, float | None] = {}
    publicado: bool | None = None
    destacado: bool = False
    ub: int | None = None
    descuento_pct: float | None = None
    portada: str | None = None            # "" = automática
    fotos_color: dict[str, str] | None = None
    variantes: dict[str, dict] = {}
    variantes_extra: dict[str, dict] | None = None
    categoria: str | None = None
    rubro: str | None = None
    relacionados: list[str] | None = None
    categorias_extra: list[str] | None = None


@router.put("/productos/{cod}")
def guardar_producto(cod: str, body: ProductoIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    campos = {
        "nombre": (body.nombre or "").strip() or None, "descripcion": (body.descripcion or "").strip() or None,
        "precios": {k: float(v) for k, v in body.precios.items() if v and v > 0},
        "publicado": body.publicado, "destacado": bool(body.destacado),
        "ub": body.ub or None, "variantes": body.variantes, "descuento_pct": body.descuento_pct,
    }
    if body.portada is not None:
        campos["portada"] = body.portada
    if body.fotos_color is not None:
        campos["fotos_color"] = body.fotos_color
    if body.variantes_extra is not None:
        campos["variantes_extra"] = body.variantes_extra
    campos["categoria"] = body.categoria
    campos["rubro"] = body.rubro
    if body.relacionados is not None:
        campos["relacionados"] = body.relacionados
    if body.categorias_extra is not None:
        campos["categorias_extra"] = body.categorias_extra
    overrides.set_catalogo_override(cod.upper(), campos, c.email)
    return {"ok": True}


@router.delete("/productos/{cod}/overrides")
def quitar_overrides(cod: str):
    overrides.quitar_catalogo_override(cod.upper())
    return {"ok": True}


class ExtraIn(BaseModel):
    color: str
    talle: str = "U"
    stock: int
    precio: float
    ean: str = ""


@router.post("/productos/{cod}/variantes-extra")
def agregar_extra(cod: str, body: ExtraIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    cod = cod.upper()
    if not body.color.strip() or body.stock <= 0 or body.precio <= 0:
        raise HTTPException(422, "Color, stock > 0 y precio L1 > 0 son obligatorios para una variante manual.")
    o = overrides.get_catalogo_overrides().get(cod, {})
    nuevos = dict(o.get("variantes_extra") or {})
    sku = adminlib.sku_variante_manual(cod, body.color, body.talle)
    nuevos[sku] = {"color": body.color.strip().upper(), "talle": body.talle.strip().upper().replace(" ", "") or "U",
                   "stock": int(body.stock), "precios": {"1": float(body.precio)}, "ean": body.ean.strip()}
    overrides.set_catalogo_override(cod, {"variantes_extra": nuevos}, c.email)
    return {"sku": sku}


@router.get("/categorias")
def categorias():
    """Árbol Categoría → Tipo de producto con conteo de productos y stock, más los
    productos reclasificados a mano. Los nombres salen de Aleph (tipo_producto → categoría,
    rubro → tipo); «Otros» = sin categoría en Aleph."""
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()
    ex = df.explode("categorias").rename(columns={"categorias": "cat"}) if "categorias" in df.columns else df.assign(cat=df["categoria"])
    ex = ex.dropna(subset=["cat"])
    g = ex.groupby(["cat", "rubro"]).agg(productos=("producto_cod", "nunique"), stock=("stock", "sum")).reset_index().rename(columns={"cat": "categoria"})
    arbol: dict[str, dict] = {}
    for _, r in g.iterrows():
        cat = arbol.setdefault(r["categoria"], {"categoria": r["categoria"], "productos": 0, "stock": 0, "tipos": []})
        cat["tipos"].append({"rubro": r["rubro"], "productos": int(r["productos"]), "stock": int(r["stock"])})
        cat["stock"] += int(r["stock"])
    for cat in arbol.values():
        cat["productos"] = int(ex[ex["cat"] == cat["categoria"]]["producto_cod"].nunique())
        cat["tipos"].sort(key=lambda t: -t["productos"])
    # Categorías creadas por el admin que hoy no tienen productos con stock
    for o in ov.values():
        for c in (o.get("categorias_extra") or []) + ([o["categoria"]] if o.get("categoria") else []):
            arbol.setdefault(c, {"categoria": c, "productos": 0, "stock": 0, "tipos": []})
    reclas = [{"producto_cod": c, "categoria": o.get("categoria"), "rubro": o.get("rubro"),
               "categorias_extra": o.get("categorias_extra") or []}
              for c, o in ov.items() if o.get("categoria") or o.get("rubro") or o.get("categorias_extra")]
    por_sec = {k: int(sitio.filtrar_seccion(df, k)["producto_cod"].nunique()) for k in sitio.SECCIONES}
    return {"arbol": sorted(arbol.values(), key=lambda c: -c["productos"]), "reclasificados": reclas,
            "por_seccion": por_sec, "secciones": {k: v["nombre"] for k, v in sitio.SECCIONES.items()}}


@router.get("/categorias/{nombre}")
def categoria_detalle(nombre: str):
    """Productos de una categoría (principal o adicional), con origen de la pertenencia."""
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()
    sub = df[catalog.mask_categoria(df, [nombre])]
    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), categoria=("categoria", "first"), rubro=("rubro", "first"),
        marca=("marca", "first"), stock=("stock", "sum"), publicado=("publicado", "first")).reset_index()
    items = []
    for _, r in prods.iterrows():
        cod = r["producto_cod"]; o = ov.get(cod, {})
        files = fotos.indice_fotos().get(cod.upper(), [])
        fn = fotos._portada_filename(cod, files) if files else None
        if r["categoria"] == nombre:
            origen = "manual" if o.get("categoria") == nombre else "aleph"
        else:
            origen = "extra"
        items.append({"producto_cod": cod, "nombre": r["nombre"], "rubro": r["rubro"], "marca": r["marca"],
                      "stock": int(r["stock"]), "publicado": _pub(r["publicado"]), "origen": origen,
                      "categoria_principal": r["categoria"], "foto": fotos.url_foto_publica(cod, fn) if fn else None})
    return {"categoria": nombre, "items": items, "n": len(items)}


@router.get("/categorias/{nombre}/banner")
def categoria_banner(nombre: str):
    return {"banners": sitio.banners_de_categoria(nombre), "secciones": {k: v["nombre"] for k, v in sitio.SECCIONES.items()}}


class CatBannerIn(BaseModel):
    seccion: str
    banner: dict | None = None


@router.put("/categorias/{nombre}/banner")
def set_categoria_banner(nombre: str, body: CatBannerIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if body.seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_banner_categoria(body.seccion, nombre, body.banner, c.email)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tipos de producto (rubro): vista, mover productos, banner
# ---------------------------------------------------------------------------
@router.get("/tipos/{rubro}")
def tipo_detalle(rubro: str, categoria: str | None = None):
    """Productos de un tipo de producto (opcionalmente dentro de una categoría), con origen."""
    df = catalog.variantes_admin()
    ov = overrides.get_catalogo_overrides()
    sub = df[df["rubro"] == rubro]
    if categoria:
        sub = sub[catalog.mask_categoria(sub, [categoria])]
    prods = sub.groupby("producto_cod", sort=True).agg(
        nombre=("producto_nombre", "first"), categoria=("categoria", "first"), marca=("marca", "first"),
        stock=("stock", "sum"), publicado=("publicado", "first")).reset_index()
    raw = catalog.load_variantes()
    rubro_aleph = raw.groupby("producto_cod")["rubro"].first().to_dict()
    items = []
    for _, r in prods.iterrows():
        cod = r["producto_cod"]; o = ov.get(cod, {})
        files = fotos.indice_fotos().get(cod.upper(), [])
        fn = fotos._portada_filename(cod, files) if files else None
        items.append({"producto_cod": cod, "nombre": r["nombre"], "categoria": r["categoria"], "marca": r["marca"],
                      "stock": int(r["stock"]), "publicado": _pub(r["publicado"]),
                      "origen": "manual" if o.get("rubro") == rubro else "aleph", "rubro_aleph": rubro_aleph.get(cod),
                      "foto": fotos.url_foto_publica(cod, fn) if fn else None})
    return {"rubro": rubro, "categoria": categoria, "items": items, "n": len(items),
            "opciones_rubro": sorted(df["rubro"].dropna().unique().tolist())}


class MoverIn(BaseModel):
    rubro: str | None = None     # None = volver al de Aleph


@router.post("/tipos/{rubro}/productos")
def tipo_agregar(rubro: str, body: CatProdIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    """Trae un producto a este tipo (pisa el rubro de Aleph en el sitio)."""
    cod = body.producto_cod.strip().upper()
    if catalog.variantes_admin().query("producto_cod == @cod").empty:
        raise HTTPException(404, f"{cod} no está en el catálogo actual")
    overrides.set_catalogo_override(cod, {"rubro": rubro}, c.email)
    return {"ok": True}


@router.put("/productos/{cod}/rubro")
def mover_rubro(cod: str, body: MoverIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    """Mueve el producto a otro tipo (o None = vuelve al rubro de Aleph)."""
    overrides.set_catalogo_override(cod.upper(), {"rubro": body.rubro}, c.email)
    return {"ok": True}


@router.get("/tipos/{rubro}/banner")
def tipo_banner(rubro: str):
    return {"banners": sitio.banners_de_filtro("rubro", rubro), "secciones": {k: v["nombre"] for k, v in sitio.SECCIONES.items()}}


class TipoBannerIn(BaseModel):
    seccion: str
    banner: dict | None = None


@router.put("/tipos/{rubro}/banner")
def set_tipo_banner(rubro: str, body: TipoBannerIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if body.seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_banner_filtro(body.seccion, "rubro", rubro, body.banner, c.email)
    return {"ok": True}


class CatProdIn(BaseModel):
    producto_cod: str


@router.post("/categorias/{nombre}/productos")
def categoria_agregar(nombre: str, body: CatProdIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    """Suma el producto a la categoría como categoría adicional (no toca la principal)."""
    cod = body.producto_cod.strip().upper()
    df = catalog.variantes_admin()
    if df[df["producto_cod"] == cod].empty:
        raise HTTPException(404, f"{cod} no está en el catálogo actual")
    o = overrides.get_catalogo_overrides().get(cod, {})
    extras = list(o.get("categorias_extra") or [])
    if nombre.strip() and nombre.strip().lower() not in {e.lower() for e in extras}:
        extras.append(nombre.strip())
    overrides.set_catalogo_override(cod, {"categorias_extra": extras}, c.email)
    return {"ok": True, "categorias_extra": extras}


@router.delete("/categorias/{nombre}/productos/{cod}")
def categoria_quitar(nombre: str, cod: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    """Quita una categoría ADICIONAL del producto. La principal (Aleph o manual) se cambia en la ficha."""
    cod = cod.upper()
    o = overrides.get_catalogo_overrides().get(cod, {})
    extras = [e for e in (o.get("categorias_extra") or []) if e.lower() != nombre.strip().lower()]
    overrides.set_catalogo_override(cod, {"categorias_extra": extras}, c.email)
    return {"ok": True, "categorias_extra": extras}


# ---------------------------------------------------------------------------
# Clientes / usuarios
# ---------------------------------------------------------------------------
def _u_json(u: dict) -> dict:
    d = _j({k: v for k, v in u.items() if k != "password_hash"})
    return d


@router.get("/clientes")
def clientes():
    usuarios = adminlib.listar_usuarios()
    cods = sorted({int(u["cliente_cod"]) for u in usuarios if u.get("cliente_cod") is not None})
    efectivos = catalog.get_clientes(cods) if cods else {}
    out = []
    for u in usuarios:
        cod = u.get("cliente_cod")
        e = efectivos.get(int(cod)) if cod is not None else None
        out.append({**_u_json(u), "cliente": _j(e) if e else None})
    return {"items": out}


class UsuarioIn(BaseModel):
    email: str
    cliente_cod: int | None = None
    nombre: str = ""
    rol: str = "cliente"


def _nueva_password(email: str, pwd: str) -> dict:
    res = auth_mod.guardar_password_en_secret(email, pwd)
    return {"password": pwd, "en_secret": res["ok"],
            "aviso": None if res["ok"] else f"No se pudo guardar la password en el secret — anotala AHORA. ({res['error'][:180]})"}


@router.post("/clientes")
def crear_usuario(body: UsuarioIn):
    nombre = body.nombre.strip()
    if body.cliente_cod:
        cli = catalog.get_cliente(int(body.cliente_cod))
        if cli is None:
            raise HTTPException(422, f"cliente_cod {body.cliente_cod} no existe en dim_cliente")
        nombre = nombre or cli["nombre_display"]
    pwd = auth_mod.generar_password()
    try:
        auth_mod.crear_usuario(body.email, pwd, body.cliente_cod or None, nombre or body.email, rol=body.rol)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"email": body.email.strip().lower(), **_nueva_password(body.email.strip().lower(), pwd)}


@router.get("/clientes/{email}")
def ficha_cliente(email: str, dias: int | None = None):
    u = auth_mod.get_usuario(email)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    cod = u.get("cliente_cod")
    e = catalog.get_cliente(int(cod)) if cod is not None else None
    o = overrides.get_clientes_overrides().get(int(cod), {}) if cod is not None else {}
    lista = ped.listar_pedidos(int(cod)) if cod is not None else []
    pv = repo.pv_de_cliente(int(cod)) if cod is not None else None
    return {
        "usuario": _u_json(u), "cliente": _j(e) if e else None, "override": _j(o),
        "metricas": _j(adminlib.metricas_cliente(lista)) if cod is not None else None,
        "pedidos": [{k: _j(p.get(k)) for k in ("numero", "fecha_str", "estado", "unidades", "total")} for p in lista],
        "pv": _j(pv),
        "repo_dias_default": int(overrides.get_config().get("repo_dias_objetivo") or 21),
    }


class CuentaIn(BaseModel):
    rol: str
    cliente_cod: int | None = None


@router.put("/clientes/{email}/cuenta")
def guardar_cuenta(email: str, body: CuentaIn):
    u = auth_mod.get_usuario(email)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    nuevo = int(body.cliente_cod) if body.cliente_cod else None
    cambios: dict = {"rol": body.rol if body.rol in ("cliente", "admin") else "cliente", "cliente_cod": nuevo}
    if nuevo and nuevo != (int(u["cliente_cod"]) if u.get("cliente_cod") is not None else None):
        cli = catalog.get_cliente(nuevo)
        if cli is None:
            raise HTTPException(422, f"cliente_cod {nuevo} no existe en dim_cliente")
        cambios["nombre_display"] = cli["nombre_display"]
    db.usuario_ref(email).update(cambios)
    return {"ok": True}


class ComercialIn(BaseModel):
    descuento_pct: float | None = None
    lista_precios: int | None = None
    contacto_nombre: str = ""
    contacto_email: str = ""
    contacto_telefono: str = ""
    cuit: str | None = None
    odoo_cliente: str = ""
    notas: str = ""


@router.put("/clientes/{email}/comercial")
def guardar_comercial(email: str, body: ComercialIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    overrides.set_cliente_override(int(u["cliente_cod"]), {
        "descuento_pct": body.descuento_pct, "lista_precios": body.lista_precios,
        "contacto_nombre": body.contacto_nombre.strip(), "contacto_email": body.contacto_email.strip().lower(),
        "contacto_telefono": body.contacto_telefono.strip(), "cuit": (body.cuit or "").strip() or None,
        "odoo_cliente": body.odoo_cliente.strip(), "notas": body.notas.strip(),
    }, c.email)
    deps.invalidar_cliente(int(u["cliente_cod"]))
    return {"ok": True}


@router.post("/clientes/{email}/reset-password")
def reset_password(email: str):
    if not auth_mod.get_usuario(email):
        raise HTTPException(404, "Usuario no encontrado")
    pwd = auth_mod.generar_password()
    auth_mod.cambiar_password(email, pwd)
    return {"email": email, **_nueva_password(email, pwd)}


class ActivoIn(BaseModel):
    activo: bool


@router.post("/clientes/{email}/activo")
def set_activo(email: str, body: ActivoIn):
    if not auth_mod.get_usuario(email):
        raise HTTPException(404, "Usuario no encontrado")
    db.usuario_ref(email).update({"activo": bool(body.activo)})
    return {"ok": True}


class ImportIn(BaseModel):
    n: int = 3


@router.post("/clientes/{email}/importar-aleph")
def importar_aleph(email: str, body: ImportIn):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    try:
        msgs = aleph_import.importar(int(u["cliente_cod"]), max(1, min(int(body.n), 50)))
    except Exception as ex:  # noqa: BLE001
        msgs = [f"Error importando: {ex}"]
    return {"mensajes": msgs}


@router.get("/clientes/{email}/reposicion")
def reposicion_cliente(email: str, dias: int | None = Query(None, ge=7, le=90)):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    cod = int(u["cliente_cod"])
    e = catalog.get_cliente(cod) or {}
    dias = dias or int(overrides.get_config().get("repo_dias_objetivo") or 21)
    df = catalog.con_precio(catalog.variantes_publicadas(), int(e.get("lista_precios") or 1))
    pv, sug = repo.sugerencias(cod, df, dias)
    if pv is None:
        raise HTTPException(403, "No es franquicia")
    cols = ["producto_cod", "producto_nombre", "color", "talle", "vendidas_30d", "stock_pv", "sugerido"]
    return {"pv": _j(pv), "dias": dias, "items": _j(sug[cols]) if not sug.empty else []}


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
@router.get("/pedidos")
def pedidos_admin(estado: str | None = None, cliente_cod: int | None = None, desde: str | None = None):
    lista = ped.listar_pedidos(None)
    counts = {"todos": len(lista)}
    for e in ("confirmado", "procesado", "cancelado"):
        counts[e] = sum(1 for p in lista if p.get("estado") == e)
    d0 = dt.date.fromisoformat(desde) if desde else None
    filt = [p for p in lista
            if (not estado or p.get("estado") == estado)
            and (cliente_cod is None or int(p.get("cliente_cod", -1)) == cliente_cod)
            and (not d0 or p["confirmed_at"].astimezone(adminlib.TZ).date() >= d0)]
    return {
        "counts": counts,
        "clientes": sorted({(int(p["cliente_cod"]), p.get("cliente_nombre", "")) for p in lista}),
        "items": [{**{k: _j(p.get(k)) for k in ("numero", "fecha_str", "confirmed_at", "cliente_cod", "cliente_nombre",
                                                  "usuario_email", "unidades", "total", "estado", "observaciones")},
                   "email_enviado": bool((p.get("email") or {}).get("enviado")), "n_items": len(p.get("items", []))}
                  for p in filt],
    }


class EstadoIn(BaseModel):
    nuevo: str


@router.post("/pedidos/{numero}/estado")
def cambiar_estado(numero: int, body: EstadoIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    try:
        ped.cambiar_estado(numero, body.nuevo, c.email)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.post("/pedidos/{numero}/reenviar")
def reenviar(numero: int):
    p = ped.get_pedido(numero)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    res = email_notif.enviar_confirmacion(p, ped.generar_excel(p), p.get("xlsx_filename") or f"pedido_{numero:06d}.xlsx")
    return _j(res)


class ModificarIn(BaseModel):
    cantidades: dict[str, int]


@router.post("/pedidos/{numero}/modificar")
def modificar(numero: int, body: ModificarIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    try:
        nuevo = ped.modificar_pedido(numero, {str(k): int(v) for k, v in body.cantidades.items()}, c.email)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "email_modificado": _j(nuevo.get("email_modificado"))}


# ---------------------------------------------------------------------------
# Config + emails
# ---------------------------------------------------------------------------
@router.get("/config")
def get_config():
    import config as appconfig
    return {"config": _j(overrides.get_config()), "default_email_to": appconfig.PEDIDOS_EMAIL_TO,
            "catalogo_hace_seg": catalog.catalogo_actualizado_hace(), "email_override_to": appconfig.EMAIL_OVERRIDE_TO}


class ConfigIn(BaseModel):
    pedidos_email_to: str | None = None
    banner_texto: str = ""
    aplicar_descvta: bool = True
    minimo_pedido_unidades: int | None = None
    minimo_pedido_monto: float | None = None
    iva_pct: float = 21.0
    notificar_estados: bool = True
    repo_dias_objetivo: int = 21


@router.put("/config")
def set_config(body: ConfigIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    overrides.set_config({
        "pedidos_email_to": (body.pedidos_email_to or "").strip() or None,
        "banner_texto": body.banner_texto.strip(), "aplicar_descvta": bool(body.aplicar_descvta),
        "minimo_pedido_unidades": int(body.minimo_pedido_unidades) if body.minimo_pedido_unidades else None,
        "minimo_pedido_monto": float(body.minimo_pedido_monto) if body.minimo_pedido_monto else None,
        "iva_pct": float(body.iva_pct), "notificar_estados": bool(body.notificar_estados),
        "repo_dias_objetivo": int(body.repo_dias_objetivo),
    }, c.email)
    return {"ok": True}


@router.post("/config/refrescar")
def refrescar():
    catalog.load_variantes(force=True)
    fotos.indice_fotos(force=True)
    overrides.invalidar()
    sitio.invalidar()
    return {"ok": True, "catalogo_hace_seg": catalog.catalogo_actualizado_hace()}


def _pedido_ejemplo() -> dict:
    lista = ped.listar_pedidos(None, limit=1)
    if lista:
        return lista[0]
    ahora = dt.datetime.now(dt.timezone.utc)
    return {"numero": 1, "cliente_nombre": "Cliente de ejemplo", "cliente_cod": 0, "usuario_email": "cliente@ejemplo.com",
            "fecha_str": ahora.strftime("%d/%m/%Y %H:%M"), "unidades": 12, "subtotal": 120000.0, "descuento_pct": 20.0,
            "descuento_monto": 24000.0, "total": 96000.0, "iva_pct": 21.0, "iva_monto": 20160.0, "total_con_iva": 116160.0,
            "lista_precios": 1, "observaciones": "", "estado": "confirmado", "confirmed_at": ahora,
            "items": [{"sku": "M211_U_1", "producto_cod": "M211", "producto_nombre": "Mochila de ejemplo", "color": "AQUA",
                       "talle": "U", "cantidad": 12, "precio_unit": 10000.0, "subtotal": 120000.0}]}


@router.get("/emails")
def emails(c: deps.Ctx = Depends(deps.ctx_admin)):
    ejemplo = _pedido_ejemplo()
    guardados = overrides.get_emails_config()
    return {
        "eventos": [{"evento": ev, "label": EVENTO_LABEL[ev], "template": email_notif.template_de(ev),
                     "default": email_notif.DEFAULT_TEMPLATES[ev], "personalizado": bool(guardados.get(ev))}
                    for ev in email_notif.EVENTOS],
        "variables": VARIABLES_EMAIL,
        "ejemplo": {"numero": ejemplo.get("numero"), "cliente_nombre": ejemplo.get("cliente_nombre"),
                    "para": ejemplo.get("usuario_email", "cliente@ejemplo.com"), "cc": overrides.pedidos_email_to(),
                    "adjunto": ejemplo.get("xlsx_filename") or f"pedido_{ejemplo.get('cliente_cod')}_{ejemplo.get('numero')}.xlsx"},
        "admin_email": c.email,
    }


class TemplateIn(BaseModel):
    formato: str = "texto"
    asunto: str
    cuerpo: str


@router.post("/emails/{evento}/preview")
def preview(evento: str, body: TemplateIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if evento not in email_notif.EVENTOS:
        raise HTTPException(404, "Evento desconocido")
    vs = email_notif._SafeDict(email_notif.variables_pedido(_pedido_ejemplo(), c.email))
    try:
        return {"asunto": body.asunto.format_map(vs), "cuerpo": body.cuerpo.format_map(vs), "formato": body.formato}
    except (ValueError, KeyError, IndexError) as e:
        raise HTTPException(422, f"La plantilla tiene llaves mal formadas: {e}")


@router.put("/emails/{evento}")
def guardar_template(evento: str, body: TemplateIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if evento not in email_notif.EVENTOS:
        raise HTTPException(404, "Evento desconocido")
    overrides.set_email_template(evento, {"formato": body.formato, "asunto": body.asunto.strip(), "cuerpo": body.cuerpo}, c.email)
    return {"ok": True}


@router.delete("/emails/{evento}")
def reset_template(evento: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if evento not in email_notif.EVENTOS:
        raise HTTPException(404, "Evento desconocido")
    overrides.reset_email_template(evento, c.email)
    return {"ok": True}


@router.post("/emails/{evento}/prueba")
def prueba(evento: str, body: TemplateIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    """Guarda la plantilla y manda una prueba al admin (nunca al cliente)."""
    if evento not in email_notif.EVENTOS:
        raise HTTPException(404, "Evento desconocido")
    overrides.set_email_template(evento, {"formato": body.formato, "asunto": body.asunto.strip(), "cuerpo": body.cuerpo}, c.email)
    return _j(email_notif.enviar_prueba(evento, _pedido_ejemplo(), c.email))


# ---------------------------------------------------------------------------
# Home + menú del sitio
# ---------------------------------------------------------------------------
@router.get("/home/{seccion}")
def home_admin(seccion: str):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    return {"seccion": seccion, "config": sitio.get_home(seccion), "personalizada": sitio.es_personalizada(seccion),
            "defaults": sitio.DEFAULTS[seccion], "tipos_seccion": sitio.TIPOS_SECCION}


@router.put("/home/{seccion}")
def set_home(seccion: str, body: dict, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_home(seccion, body, c.email)
    return {"ok": True}


@router.delete("/home/{seccion}")
def reset_home(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.reset_home(seccion, c.email)
    return {"ok": True}


@router.post("/home/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(422, "Solo imágenes")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "Máximo 10 MB")
    return {"url": sitio.subir_imagen(data, file.filename or "imagen.jpg", file.content_type)}


@router.get("/menu/{seccion}")
def menu_admin(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    df = deps.df_cliente(c)
    return {"seccion": seccion, "auto": sitio.menu_auto(df, seccion), "config": sitio.get_menu(seccion),
            "efectivo": sitio.menu_efectivo(df, seccion), "tope_auto": sitio.MENU_AUTO_TOPE}


@router.put("/menu/{seccion}")
def set_menu(seccion: str, body: dict, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_menu(seccion, body, c.email)
    return {"ok": True}


@router.delete("/menu/{seccion}")
def reset_menu(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.reset_menu(seccion, c.email)
    return {"ok": True}
