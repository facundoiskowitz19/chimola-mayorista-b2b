"""Mega-menú por sección: automático desde BQ, pisado por `config/home.menu.<seccion>` si existe."""
from __future__ import annotations

import datetime as dt

from sitio._store import _ref, get_home_raw, invalidar
from sitio.secciones import SECCIONES, filtrar_seccion

# ---------------------------------------------------------------------------
# Mega-menú: automático desde BQ, pisado por `config/home.menu.<seccion>` si existe
# ---------------------------------------------------------------------------
# Config por sección: {"temporadas": [{valor, nombre, nuevo, anterior}], "tipos": [{valor, nombre}],
#                      "tendencias": [{valor, nombre}]}   — lista vacía/ausente = automático.
MENU_LISTAS = ("temporadas", "tipos", "tendencias")
MENU_AUTO_TOPE = {"temporadas": 9, "tipos": 12, "tendencias": 20}


def _conteo(sub, col: str) -> list[dict]:
    if col == "categoria" and "categorias" in sub.columns:
        ex = sub[["producto_cod", "categorias"]].explode("categorias").dropna()
        g = ex.groupby("categorias")["producto_cod"].nunique().sort_values(ascending=False)
    else:
        g = sub.groupby(col)["producto_cod"].nunique().sort_values(ascending=False)
    return [{"valor": str(k), "n": int(v)} for k, v in g.items() if k and k != "Otros"]


def menu_auto(df, seccion: str) -> dict:
    """Todas las opciones disponibles en BQ para la sección, con conteo de productos
    (sin tope: el tope se aplica al mostrar, y el admin ve la lista completa)."""
    sub = filtrar_seccion(df, seccion)
    if "precio" in sub.columns:
        sub = sub[sub["precio"].notna()]
    tend = [t for t in _conteo(sub, "categoria") if t["valor"] not in ("Marroquineria", "Indumentaria")]
    return {
        "temporadas": _conteo(sub, "temporada"), "tipos": _conteo(sub, "rubro"), "tendencias": tend,
        "oportunidades": int(sub[sub["pct_desc"] > 0]["producto_cod"].nunique()) if "pct_desc" in sub.columns else 0,
        "n": int(sub["producto_cod"].nunique()),
    }


def get_menu(seccion: str) -> dict | None:
    """Config guardada del menú de la sección (None = todo automático)."""
    return (get_home_raw().get("menu") or {}).get(seccion) or None


def set_menu(seccion: str, data: dict, por: str) -> None:
    if seccion not in SECCIONES:
        raise KeyError(seccion)
    limpio = {}
    for lista in MENU_LISTAS:
        items = []
        for it in data.get(lista) or []:
            valor = str(it.get("valor") or "").strip()
            if not valor:
                continue
            d = {"valor": valor, "nombre": str(it.get("nombre") or "").strip() or valor}
            if lista == "temporadas":
                d["nuevo"] = bool(it.get("nuevo"))
                d["anterior"] = bool(it.get("anterior"))
            items.append(d)
        limpio[lista] = items
    ops = []
    for it in data.get("oportunidades") or []:
        nombre = str(it.get("nombre") or "").strip(); link = str(it.get("link") or "").strip()
        if nombre and link:
            ops.append({"nombre": nombre, "link": link, "oculto": bool(it.get("oculto"))})
    limpio["oportunidades"] = ops
    grupos = []
    for g in data.get("grupos") or []:   # columnas extra: tipos de producto DENTRO de una categoría
        titulo = str(g.get("titulo") or "").strip(); cat = str(g.get("categoria") or "").strip()
        if titulo and cat:
            grupos.append({"titulo": titulo, "categoria": cat, "oculto": bool(g.get("oculto"))})
    limpio["grupos"] = grupos
    _ref().set({"menu": {seccion: limpio}, "updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por},
               merge=True)
    # merge=True fusiona listas por posición en mapas anidados: reemplazar explícito.
    _ref().update({f"menu.{seccion}": limpio})
    invalidar()


def reset_menu(seccion: str, por: str) -> None:
    from google.cloud import firestore
    _ref().set({"updated_at": dt.datetime.now(dt.timezone.utc), "updated_by": por}, merge=True)
    _ref().update({f"menu.{seccion}": firestore.DELETE_FIELD})
    invalidar()


def menu_efectivo(df, seccion: str) -> dict:
    """Lo que ve el cliente: config del admin si existe (solo valores que hoy tienen
    productos), si no automático. Cada ítem: {valor, nombre, n, (nuevo, anterior)}."""
    auto = menu_auto(df, seccion)
    cfg = get_menu(seccion) or {}
    out = {"nombre": SECCIONES[seccion]["nombre"], "marca": SECCIONES[seccion]["marca"],
           "oportunidades": auto["oportunidades"], "n": auto["n"], "personalizado": {}}
    for lista in MENU_LISTAS:
        disponibles = {a["valor"]: a["n"] for a in auto[lista]}
        conf = cfg.get(lista) or []
        if conf:
            items = [{**it, "n": disponibles[it["valor"]]} for it in conf if it["valor"] in disponibles]
            out["personalizado"][lista] = True
        else:
            items = [{"valor": a["valor"], "nombre": a["valor"], "n": a["n"]} for a in auto[lista][:MENU_AUTO_TOPE[lista]]]
            if lista == "temporadas":
                for i, it in enumerate(items):
                    it["nuevo"] = i == 0
                    it["anterior"] = i >= 3
            out["personalizado"][lista] = False
        if lista == "temporadas":
            for it in items:
                it.setdefault("nuevo", False)
                it.setdefault("anterior", False)
        out[lista] = items
    # Grupos (vista 7 de Vale: GIRLS / BOYS): una columna por categoría con los tipos de producto
    # que tiene esa categoría en la sección. Los nombres/orden de tipos respetan la config de "tipos".
    sub = filtrar_seccion(df, seccion)
    if "precio" in sub.columns:
        sub = sub[sub["precio"].notna()]
    renombres = {t["valor"]: t["nombre"] for t in out["tipos"]}
    orden_tipos = {t["valor"]: i for i, t in enumerate(out["tipos"])}
    grupos_out = []
    for g in cfg.get("grupos") or []:
        if g.get("oculto"):
            continue
        import catalog as _cat
        sg = sub[_cat.mask_categoria(sub, [g["categoria"]])]
        cnt = sg.groupby("rubro")["producto_cod"].nunique()
        tipos_g = [{"valor": r, "nombre": renombres.get(r, r), "n": int(n)} for r, n in cnt.items() if r and r != "Otros"]
        tipos_g.sort(key=lambda t: (orden_tipos.get(t["valor"], 999), -t["n"]))
        grupos_out.append({"titulo": g["titulo"], "categoria": g["categoria"], "tipos": tipos_g,
                           "n": int(sg["producto_cod"].nunique())})
    out["grupos"] = grupos_out
    out["personalizado"]["grupos"] = bool(grupos_out)
    # Cuarta columna: links libres. Default = ofertas (productos con descuento) + ver todo.
    conf_ops = cfg.get("oportunidades") or []
    if conf_ops:
        out["oportunidades_items"] = [o for o in conf_ops if not o.get("oculto")]
        out["personalizado"]["oportunidades"] = True
    else:
        out["oportunidades_items"] = [
            {"nombre": f"Ver ofertas ({auto['oportunidades']})", "link": f"/c/{seccion}?solo_desc=1"},
            {"nombre": f"Ver todo {SECCIONES[seccion]['nombre']} ({auto['n']})", "link": f"/c/{seccion}"},
        ]
        out["personalizado"]["oportunidades"] = False
    return out
