"""Catálogo: grilla con filtros, mega-menú, ficha de producto, buscador, curva sugerida.

Secciones del header (los 3 "homes"):
  marro → Chimola, todo menos Indumentaria/Pijamas
  indu  → Chimola, Indumentaria + Pijamas
  lima  → Lima
Privacidad: el stock NUNCA sale a usuarios no-admin (ver SPECS §12)."""
from __future__ import annotations

import math
import re

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

import catalog
import fotos
import sitio

from api import colores, deps

router = APIRouter(tags=["catalogo"])

SECCIONES = sitio.SECCIONES
PER_PAGE_DEFAULT = 24
PER_PAGE_MAX = 96


def _seccion_df(df: pd.DataFrame, seccion: str | None) -> pd.DataFrame:
    if seccion and seccion not in SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    return sitio.filtrar_seccion(df, seccion)


def _seccion_de(row) -> str:
    return sitio.seccion_de(row["marca"], row["categoria"])


def _lista(v: list[str] | None) -> list[str]:
    out: list[str] = []
    for x in v or []:
        out += [p for p in x.split("|") if p]
    return out


def card(row, df_var: pd.DataFrame | None = None, es_admin: bool = False) -> dict:
    """Card de producto para la grilla / carruseles."""
    cod = row["producto_cod"]
    cols = list(row["colores"]) if isinstance(row.get("colores"), (list, tuple)) else []
    try:
        por_color = fotos.foto_por_color(cod, cols)
    except Exception:  # noqa: BLE001
        por_color = {}
    fn_portada = fotos._portada_filename(cod, fotos.indice_fotos().get(cod.upper(), []))
    swatches = []
    for c in cols:
        fn = por_color.get(fotos.norm(c))
        swatches.append({"color": c, "hex": colores.hex_de(c),
                         "foto": fotos.url_foto_publica(cod, fn) if fn else None})
    pct = float(row.get("pct_desc") or 0)
    return {
        "producto_cod": cod,
        "nombre": row["producto_nombre"],
        "marca": row["marca"], "temporada": row["temporada"], "rubro": row["rubro"],
        "categoria": row["categoria"], "seccion": _seccion_de(row),
        "precio": deps.jsonable(row["precio"]),
        "precio_lista": deps.jsonable(row.get("precio_lista")),
        "pct_desc": pct,
        "foto": fotos.url_foto_publica(cod, fn_portada) if fn_portada else None,
        "tiene_foto": bool(fn_portada),
        "colores": swatches,
        "destacado": bool(row.get("destacado", False)),
        "n_variantes": int(row.get("n_variantes") or 0),
        **({"stock": int(row.get("stock") or 0)} if es_admin else {}),
    }


@router.get("/catalogo")
def listar(
    c: deps.Ctx = Depends(deps.ctx_requerido),
    seccion: str | None = None,
    categoria: list[str] | None = Query(None), rubro: list[str] | None = Query(None),
    marca: list[str] | None = Query(None), temporada: list[str] | None = Query(None),
    color: list[str] | None = Query(None), talle: list[str] | None = Query(None),
    q: str = "", solo_foto: bool = True, solo_desc: bool = False,
    precio_min: float | None = None, precio_max: float | None = None,
    orden: str = "destacados", page: int = 1, per_page: int = PER_PAGE_DEFAULT,
):
    df = _seccion_df(deps.df_cliente(c), seccion)
    sel = {"categoria": _lista(categoria), "rubro": _lista(rubro), "marca": _lista(marca),
           "temporada": _lista(temporada), "color": _lista(color), "talle": _lista(talle)}
    sub = catalog.filtrar_variantes(df, sel, q)
    if solo_desc:
        sub = sub[sub["pct_desc"] > 0] if "pct_desc" in sub.columns else sub
    sub = sub[sub["precio"].notna()]
    prods = catalog.productos(sub)
    if "destacado" in sub.columns and not prods.empty:
        prods = prods.merge(sub.groupby("producto_cod")["destacado"].max().reset_index(), on="producto_cod", how="left")
    if solo_foto and not prods.empty:
        prods = prods[prods["producto_cod"].map(fotos.tiene_fotos)]
    if precio_min is not None:
        prods = prods[prods["precio"] >= precio_min]
    if precio_max is not None:
        prods = prods[prods["precio"] <= precio_max]

    if orden == "precio_asc":
        prods = prods.sort_values(["precio", "producto_cod"])
    elif orden == "precio_desc":
        prods = prods.sort_values(["precio", "producto_cod"], ascending=[False, True])
    elif orden == "nombre":
        prods = prods.sort_values("producto_nombre")
    elif not prods.empty:   # destacados primero, después "lo nuevo": código descendente como proxy
        dest = prods["destacado"].fillna(False).astype(bool) if "destacado" in prods.columns else pd.Series(False, index=prods.index)
        prods = prods.assign(_d=dest.astype(int)).sort_values(["_d", "producto_cod"], ascending=[False, False]).drop(columns="_d")

    total = len(prods)
    per_page = max(1, min(per_page, PER_PAGE_MAX))
    pag = prods.iloc[(page - 1) * per_page: page * per_page]
    return {
        "seccion": seccion, "total": total, "page": page, "per_page": per_page,
        "pages": max(1, math.ceil(total / per_page)),
        "items": [card(r, es_admin=c.es_admin) for _, r in pag.iterrows()],
        "facetas": _facetas(df, sel),
        "precio_rango": {"min": deps.jsonable(prods["precio"].min()) if total else None,
                         "max": deps.jsonable(prods["precio"].max()) if total else None},
    }


def _facetas(df: pd.DataFrame, sel: dict) -> dict:
    """Opciones con conteo de productos, facetado dependiente (cada filtro respeta los demás)."""
    out = {}
    for f in catalog.FILTROS:
        otros = {k: v for k, v in sel.items() if k != f and v}
        sub = catalog.filtrar_variantes(df, otros)
        if f == "categoria" and "categorias" in sub.columns:
            cnt = sub[["producto_cod", "categorias"]].explode("categorias").dropna().groupby("categorias")["producto_cod"].nunique()
        else:
            cnt = sub.groupby(f)["producto_cod"].nunique()
        opciones = [{"valor": k, "n": int(v)} for k, v in cnt.items() if k]
        if f == "talle":
            opciones.sort(key=lambda o: catalog.talle_key(o["valor"]))
        else:
            opciones.sort(key=lambda o: (-o["n"], o["valor"]))
        if f == "color":
            for o in opciones:
                o["hex"] = colores.hex_de(o["valor"])
        out[f] = opciones
    return out


@router.get("/catalogo/menu")
def menu(c: deps.Ctx = Depends(deps.ctx_requerido)):
    """Mega-menú por sección: lo configurado en el admin (config/home.menu) o automático."""
    df = deps.df_cliente(c)
    return {key: sitio.menu_efectivo(df, key) for key in SECCIONES}


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------
def _familia(nombre: str) -> str | None:
    """Última palabra "de familia" del nombre: 'Mochila Rubber' → 'Rubber'."""
    toks = [t for t in re.split(r"\s+", (nombre or "").strip()) if t]
    if len(toks) < 2:
        return None
    fam = toks[-1]
    return fam if len(fam) >= 3 and not fam.isdigit() else None


@router.get("/productos/{cod}")
def producto(cod: str, c: deps.Ctx = Depends(deps.ctx_requerido)):
    df = deps.df_cliente(c)
    p = catalog.get_producto(df, cod.upper())
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    fts = fotos.fotos_producto(p["producto_cod"], p["colores"])
    por_color = fotos.foto_por_color(p["producto_cod"], p["colores"])
    for f in fts:
        f["url"] = fotos.url_foto_publica(p["producto_cod"], f["filename"])
    variantes = []
    for v in p["variantes"]:
        d = {k: deps.jsonable(v.get(k)) for k in ("sku", "ean", "color_cod", "color", "talle",
                                                   "precio", "precio_lista", "pct_desc", "es_manual")}
        d["disponible"] = int(v["stock"]) > 0
        if c.es_admin:
            d["stock"] = int(v["stock"])
        variantes.append(d)
    talles = sorted({v["talle"] for v in p["variantes"]}, key=catalog.talle_key)
    cols = sorted({v["color"] for v in p["variantes"]})

    # Relacionados: 1º los elegidos a mano en el admin (y los productos que lo eligieron a él),
    # 2º misma "familia" por nombre, 3º mismo rubro+marca. Siempre con foto, máx 8.
    import overrides
    ov = overrides.get_catalogo_overrides()
    manuales = list((ov.get(p["producto_cod"]) or {}).get("relacionados") or [])
    manuales += [c for c, o in ov.items() if p["producto_cod"] in (o.get("relacionados") or []) and c not in manuales]
    prods = catalog.productos(df[df["producto_cod"] != p["producto_cod"]])
    fam = _familia(p["producto_nombre"])
    rel_man = prods[prods["producto_cod"].isin(manuales)]
    rel_man = rel_man.assign(_o=rel_man["producto_cod"].map({c: i for i, c in enumerate(manuales)})).sort_values("_o").drop(columns="_o")
    rel_fam = prods[prods["producto_nombre"].str.contains(rf"\b{re.escape(fam)}\b", case=False, regex=True)] if fam else prods.iloc[0:0]
    rel = pd.concat([rel_man, rel_fam[~rel_fam["producto_cod"].isin(rel_man["producto_cod"])]])
    if len(rel) < 4:
        mismo = prods[(prods["rubro"] == p["rubro"]) & (prods["marca"] == p["marca"]) &
                      (~prods["producto_cod"].isin(rel["producto_cod"]))]
        rel = pd.concat([rel, mismo.head(8 - len(rel))])
    rel = rel[rel["producto_cod"].map(fotos.tiene_fotos)].head(8)

    row = df[df["producto_cod"] == p["producto_cod"]].iloc[0]
    return {
        **{k: deps.jsonable(p[k]) for k in ("producto_cod", "producto_nombre", "marca", "temporada", "rubro",
                                              "categoria", "descripcion", "ub", "precio", "precio_lista", "pct_desc")},
        "seccion": _seccion_de(row),
        "colores": [{"color": col, "hex": colores.hex_de(col),
                     "foto": fotos.url_foto_publica(p["producto_cod"], por_color[fotos.norm(col)]) if por_color.get(fotos.norm(col)) else None}
                    for col in cols],
        "talles": talles,
        "variantes": variantes,
        "fotos": [{"url": f["url"], "filename": f["filename"], "color": f["color_norm"], "principal": f["is_main"]} for f in fts],
        "relacionados": [card(r) for _, r in rel.iterrows()],
        "familia": fam,
    }


# ---------------------------------------------------------------------------
# Curva sugerida (indumentaria): reparte un total proporcional al stock
# ---------------------------------------------------------------------------
def repartir_proporcional(stocks: dict[str, int], total: int) -> dict[str, int]:
    """Método del mayor resto: suma exacta `total`, nunca más que el stock de cada sku.
    Función pura (testeable)."""
    disp = {k: int(v) for k, v in stocks.items() if int(v) > 0}
    cap = sum(disp.values())
    total = max(0, min(int(total), cap))
    if total == 0 or not disp:
        return {k: 0 for k in stocks}
    cuotas = {k: total * v / cap for k, v in disp.items()}
    asig = {k: min(int(math.floor(q)), disp[k]) for k, q in cuotas.items()}
    falta = total - sum(asig.values())
    orden = sorted(disp, key=lambda k: (-(cuotas[k] - math.floor(cuotas[k])), -disp[k], k))
    i = 0
    while falta > 0 and i < 10_000:
        k = orden[i % len(orden)]
        if asig[k] < disp[k]:
            asig[k] += 1
            falta -= 1
        i += 1
    return {k: asig.get(k, 0) for k in stocks}


@router.get("/productos/{cod}/curva")
def curva(cod: str, total: int = Query(..., ge=1, le=100_000), c: deps.Ctx = Depends(deps.ctx_requerido)):
    df = deps.df_cliente(c)
    p = catalog.get_producto(df, cod.upper())
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    stocks = {v["sku"]: int(v["stock"]) for v in p["variantes"] if pd.notna(v.get("precio"))}
    asig = repartir_proporcional(stocks, total)
    asignado = sum(asig.values())
    por_sku = {v["sku"]: v for v in p["variantes"]}
    return {
        "total_pedido": total, "total_asignado": asignado,
        "recortado": asignado < total,   # no hay disponibilidad para todo el total (sin revelar cuánto)
        "items": [{"sku": s, "color": por_sku[s]["color"], "talle": por_sku[s]["talle"], "cantidad": n}
                  for s, n in asig.items() if n > 0],
    }


# ---------------------------------------------------------------------------
# Buscador con sugerencias
# ---------------------------------------------------------------------------
@router.get("/buscar")
def buscar(q: str = Query("", min_length=0), c: deps.Ctx = Depends(deps.ctx_requerido)):
    q = q.strip()
    if len(q) < 2:
        return {"nombres": [], "productos": []}
    df = deps.df_cliente(c)
    sub = catalog.filtrar_variantes(df[df["precio"].notna()], None, q)
    prods = catalog.productos(sub)
    # Los productos sin foto (colecciones nuevas) también se encuentran: van después de los que tienen.
    if not prods.empty:
        prods = prods.assign(_f=prods["producto_cod"].map(fotos.tiene_fotos).astype(int)).sort_values(["_f", "producto_cod"], ascending=[False, True]).drop(columns="_f")
    nombres = list(dict.fromkeys(prods["producto_nombre"].tolist()))[:5]
    return {"nombres": nombres, "productos": [card(r) for _, r in prods.head(3).iterrows()], "total": len(prods)}
