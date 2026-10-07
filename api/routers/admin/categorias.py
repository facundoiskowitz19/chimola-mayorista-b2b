"""Admin → Categorías y tipos de producto (multicategoría, reclasificación y banners por filtro)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import catalog
import fotos
import overrides
import sitio

from api import deps
from api.routers.admin._common import _pub

router = APIRouter()


# ---------------------------------------------------------------------------
# Categorías y tipos de producto: árbol, productos de cada una, mover/traer, banners
# ---------------------------------------------------------------------------
class CatProdIn(BaseModel):
    producto_cod: str


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
    if extras != list(o.get("categorias_extra") or []):   # sin cambios → no crear un override vacío
        overrides.set_catalogo_override(cod, {"categorias_extra": extras}, c.email)
    return {"ok": True, "categorias_extra": extras}
