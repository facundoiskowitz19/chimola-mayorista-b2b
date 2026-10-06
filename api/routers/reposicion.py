"""Reposición sugerida (solo franquicias titulares de un PV). Motor en `reposicion.py`."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

import fotos
import overrides
import reposicion as repo

from api import colores, deps

router = APIRouter(prefix="/reposicion", tags=["reposicion"])


@router.get("")
def sugerencias(dias: int | None = Query(None, ge=7, le=90), c: deps.Ctx = Depends(deps.ctx_cliente)):
    pv = repo.pv_de_cliente(int(c.cliente_cod))
    if pv is None:
        raise HTTPException(403, "La reposición sugerida es solo para franquicias")
    dias = dias or int(overrides.get_config().get("repo_dias_objetivo") or 21)
    df = deps.df_cliente(c)
    _, sug = repo.sugerencias(int(c.cliente_cod), df, dias)
    items = []
    if not sug.empty:
        for _, r in sug.iterrows():
            items.append({
                "sku": r["sku"], "producto_cod": r["producto_cod"], "nombre": r["producto_nombre"],
                "marca": r["marca"], "rubro": r["rubro"], "categoria": r.get("categoria", "Otros"),
                "temporada": r["temporada"], "color": r["color"], "hex": colores.hex_de(r["color"]),
                "talle": r["talle"],
                "precio": deps.jsonable(r["precio"]), "precio_lista": deps.jsonable(r.get("precio_lista")),
                "pct_desc": float(r.get("pct_desc") or 0),
                "vendidas_30d": int(r["vendidas_30d"] or 0),
                "stock_pv": max(0, int(r["stock_pv"] or 0)),
                "cobertura_dias": max(0.0, float(r["cobertura_dias"])) if pd.notna(r.get("cobertura_dias")) else None,
                "sugerido": int(r["sugerido"]),
                "ub": int(r["ub"]) if "ub" in sug.columns and pd.notna(r.get("ub")) and r.get("ub") else None,
                "foto": fotos.url_variante_publica(r["producto_cod"], r["color"]) or None,
            })
    return {"pv": {"pv_cod": pv["pv_cod"], "pv_nombre": pv["pv_nombre"]}, "dias": dias,
            "items": items, "total_sugerido": int(sum(i["sugerido"] for i in items))}
