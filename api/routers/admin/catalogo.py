"""Admin → Catálogo: listado con pills/facetas, acciones en lote, auditoría fotos↔variantes,
ficha de producto (overrides) y variantes manuales."""
from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import adminlib
import catalog
import fotos
import overrides

from api import colores, deps
from api.routers.admin._common import PUB_LABELS, _j, _pub

router = APIRouter()


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
             pill: str = "todos", page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200)):
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
