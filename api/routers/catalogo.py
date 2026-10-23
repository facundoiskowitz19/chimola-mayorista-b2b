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
        por_color = fotos.foto_por_color(cod, cols, None, fotos._overrides_fotos(cod))   # respeta fotos_color del admin
    except Exception:  # noqa: BLE001
        por_color = {}
    fn_portada = fotos._portada_filename(cod, fotos.indice_fotos().get(cod.upper(), []))
    swatches = []
    for c in cols:
        fn = por_color.get(fotos.norm(c))
        swatches.append({"color": c, "hex": colores.hex_de(c),
                         "foto": fotos.url_foto_publica(cod, fn) if fn else None})
    pct = float(row.get("pct_desc") or 0)
    alias = sitio.get_alias()
    return {
        "producto_cod": cod,
        "nombre": row["producto_nombre"],
        "marca": row["marca"], "temporada": row["temporada"], "rubro": row["rubro"],
        "categoria": row["categoria"], "seccion": _seccion_de(row),
        # Nombres visibles (alias del admin; si no hay, el valor de Aleph)
        "rubro_nombre": alias["rubro"].get(row["rubro"], row["rubro"]),
        "temporada_nombre": alias["temporada"].get(row["temporada"], row["temporada"]),
        "categoria_nombre": alias["categoria"].get(row["categoria"], row["categoria"]),
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
    orden: str = "destacados", page: int = Query(1, ge=1), per_page: int = Query(PER_PAGE_DEFAULT, ge=1, le=PER_PAGE_MAX),
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
    # Rango de precios ANTES de aplicar precio_min/max: así el slider no se achica a medida que se acota.
    rango = {"min": deps.jsonable(prods["precio"].min()) if len(prods) else None,
             "max": deps.jsonable(prods["precio"].max()) if len(prods) else None}
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
        "facetas": _facetas(_base_facetas(df, q, solo_desc, solo_foto), sel),
        "precio_rango": rango,
        "alias": sitio.get_alias(),   # título, chips y migajas muestran el alias; filtros y URLs usan el valor de Aleph
    }


def _base_facetas(df: pd.DataFrame, q: str, solo_desc: bool, solo_foto: bool) -> pd.DataFrame:
    """Universo sobre el que se calculan las facetas: ya filtrado por búsqueda, oferta y foto,
    así el rail nunca ofrece opciones que dejarían la grilla vacía."""
    base = catalog.filtrar_variantes(df, None, q)
    if solo_desc and "pct_desc" in base.columns:
        base = base[base["pct_desc"] > 0]
    base = base[base["precio"].notna()]
    if solo_foto and not base.empty:
        con_foto = {c for c in base["producto_cod"].unique() if fotos.tiene_fotos(c)}
        base = base[base["producto_cod"].isin(con_foto)]
    return base


def _facetas(df: pd.DataFrame, sel: dict) -> dict:
    """Opciones con conteo de productos, facetado dependiente (cada filtro respeta los demás)."""
    out = {}
    alias = sitio.get_alias()
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
        if f in alias:
            for o in opciones:
                o["nombre"] = alias[f].get(o["valor"], o["valor"])
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


def relacionados_manuales(cod: str) -> list[str]:
    """Los elegidos a mano en el admin para `cod` más los productos que lo eligieron a él."""
    import overrides
    ov = overrides.get_catalogo_overrides()
    manuales = list((ov.get(cod) or {}).get("relacionados") or [])
    manuales += [c for c, o in ov.items() if cod in (o.get("relacionados") or []) and c not in manuales]
    return manuales


def relacionados_de(df: pd.DataFrame, cod: str, nombre: str, rubro: str, marca: str,
                    manuales: list[str] | None = None, n: int = 8) -> pd.DataFrame:
    """Productos relacionados: 1º los manuales del admin (None = leerlos de los overrides; [] = solo
    automáticos, lo que el admin ve como «por defecto»), 2º misma "familia" por nombre (última palabra),
    3º mismo tipo de producto + marca si quedaron menos de 4. Siempre con foto, máx `n`."""
    if manuales is None:
        manuales = relacionados_manuales(cod)
    prods = catalog.productos(df[df["producto_cod"] != cod])
    fam = _familia(nombre)
    rel_man = prods[prods["producto_cod"].isin(manuales)]
    rel_man = rel_man.assign(_o=rel_man["producto_cod"].map({c: i for i, c in enumerate(manuales)})).sort_values("_o").drop(columns="_o")
    rel_fam = prods[prods["producto_nombre"].str.contains(rf"\b{re.escape(fam)}\b", case=False, regex=True)] if fam else prods.iloc[0:0]
    rel = pd.concat([rel_man, rel_fam[~rel_fam["producto_cod"].isin(rel_man["producto_cod"])]])
    if len(rel) < 4:
        mismo = prods[(prods["rubro"] == rubro) & (prods["marca"] == marca) & (~prods["producto_cod"].isin(rel["producto_cod"]))]
        rel = pd.concat([rel, mismo.head(n - len(rel))])
    return rel[rel["producto_cod"].map(fotos.tiene_fotos)].head(n)


@router.get("/productos/{cod}")
def producto(cod: str, c: deps.Ctx = Depends(deps.ctx_requerido)):
    df = deps.df_cliente(c)
    p = catalog.get_producto(df, cod.upper())
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    fts = fotos.fotos_producto_publicas(p["producto_cod"], p["colores"])   # URLs públicas: sin signBlob por foto
    por_color = fotos.foto_por_color(p["producto_cod"], p["colores"], None, fotos._overrides_fotos(p["producto_cod"]))
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

    rel = relacionados_de(df, p["producto_cod"], p["producto_nombre"], p["rubro"], p["marca"])
    fam = _familia(p["producto_nombre"])

    row = df[df["producto_cod"] == p["producto_cod"]].iloc[0]
    ft = catalog.ficha_texto(p.get("descripcion"))
    # En Tienda Nube las medidas de la ropa son del paquete (ej. 10 × 10 × 5 para un vestido): solo valen para marroquinería/bazar.
    es_ropa = str(row.get("categoria") or "") in catalog.CATEGORIAS_ROPA
    med_struct = None if es_ropa else catalog.medidas_formato(row.get("alto_cm"), row.get("ancho_cm"), row.get("profundidad_cm"))
    peso = row.get("peso_kg")
    _j = deps.jsonable
    return {
        **{k: deps.jsonable(p[k]) for k in ("producto_cod", "producto_nombre", "marca", "temporada", "rubro",
                                              "categoria", "descripcion", "ub", "precio", "precio_lista", "pct_desc")},
        "seccion": _seccion_de(row),
        "rubro_nombre": sitio.nombre_de("rubro", p["rubro"]) or p["rubro"],
        "categoria_nombre": sitio.nombre_de("categoria", p["categoria"]) or p["categoria"],
        "temporada_nombre": sitio.nombre_de("temporada", p["temporada"]) or p["temporada"],
        **{"descripcion_corta": ft["corta"], "medidas": med_struct or ft["medidas"], "materiales": ft["materiales"],
           "medidas_origen": "tiendanube" if med_struct else ("descripcion" if ft["medidas"] else None),
           "peso_kg": _j(peso) if peso is not None and _j(peso) and _j(peso) > 0 else None},
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
def repartir_proporcional(stocks: dict[str, int], total: int, pesos: dict[str, float] | None = None) -> dict[str, int]:
    """Reparte `total` entre las variantes en proporción a `pesos` (por defecto, al stock), sin superar el
    stock de cada una. Si una variante se llena, lo que le faltaba se vuelve a repartir entre las demás en
    la misma proporción. Suma exacta `total` (o todo lo que hay si no alcanza). Función pura (testeable)."""
    cap = {k: int(v) for k, v in stocks.items() if int(v) > 0}
    total = max(0, min(int(total), sum(cap.values())))
    if total == 0 or not cap:
        return {k: 0 for k in stocks}
    w = {k: float((pesos or {}).get(k) or 0) for k in cap}
    if sum(w.values()) <= 0:
        w = {k: float(cap[k]) for k in cap}
    for k in cap:                      # variante con stock pero sin peso: pesa lo que tiene
        if w[k] <= 0:
            w[k] = float(cap[k])
    asig = {k: 0 for k in cap}
    resto = total
    activos = set(cap)
    while resto > 0 and activos:
        sw = sum(w[k] for k in activos)
        cuotas = {k: resto * w[k] / sw for k in activos}
        base = {k: min(int(math.floor(cuotas[k])), cap[k] - asig[k]) for k in activos}
        if sum(base.values()) > 0:
            for k, b in base.items():
                asig[k] += b
                resto -= b
        else:                           # solo quedan fracciones: mayor resto, una unidad a cada una
            for k in sorted(activos, key=lambda k: (-(cuotas[k] - math.floor(cuotas[k])), -w[k], k)):
                if resto <= 0:
                    break
                if asig[k] < cap[k]:
                    asig[k] += 1
                    resto -= 1
        activos = {k for k in activos if asig[k] < cap[k]}
    return {k: asig.get(k, 0) for k in stocks}


@router.get("/productos/{cod}/curva")
def curva(cod: str, total: int = Query(..., ge=1, le=2_000), c: deps.Ctx = Depends(deps.ctx_requerido)):
    """Curva sugerida en la proporción en que Chimola COMPRÓ el producto (`compras_total` por variante:
    recibidas + OC pendientes, de `venta_temporada_extended`), acotada a lo disponible hoy menos lo que ya
    está en el carrito. Sin datos de compras, proporcional al stock. `total` acotado: con un total enorme
    la respuesta sería el stock exacto de cada variante (SPECS §12: nunca revelar números de stock)."""
    df = deps.df_cliente(c)
    p = catalog.get_producto(df, cod.upper())
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    # Lo que ya está en el carrito se descuenta: la curva reparte lo que QUEDA por pedir de cada variante.
    en_carrito: dict[str, int] = {}
    if c.puede_pedir:
        import pedidos
        en_carrito = {i["sku"]: int(i["cantidad"]) for i in pedidos.cargar_carrito(c.email)}
    stocks = {v["sku"]: max(0, int(v["stock"]) - en_carrito.get(v["sku"], 0))
              for v in p["variantes"] if pd.notna(v.get("precio"))}
    compras = {v["sku"]: int(v.get("compras_total") or 0) for v in p["variantes"] if v["sku"] in stocks}
    base = "compras" if sum(compras.values()) > 0 else "stock"
    asig = repartir_proporcional(stocks, total, compras if base == "compras" else None)
    asignado = sum(asig.values())
    por_sku = {v["sku"]: v for v in p["variantes"]}
    return {
        "total_pedido": total, "total_asignado": asignado,
        "recortado": asignado < total,   # no hay disponibilidad para todo el total (sin revelar cuánto)
        "considera_carrito": any(en_carrito.get(s) for s in stocks),
        "base": base,   # "compras" = proporción de la curva comprada; "stock" = sin datos de compras
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
