"""Lógica pura del admin (sin Streamlit ni GCP), compartida por el admin Next (API)
y el Streamlit viejo mientras conviven. Copiada de admin_ui._kpis/_metricas_cliente."""
from __future__ import annotations

import datetime as dt
import zoneinfo

import config

TZ = zoneinfo.ZoneInfo(config.TZ)


def kpis(lista: list[dict], ahora: dt.datetime) -> dict:
    """KPIs del mes a partir de la lista de pedidos."""
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
        "top": sorted(([c, d["nombre"], d["unidades"]] for c, d in top.items()), key=lambda x: -x[2])[:5],
    }


def metricas_cliente(lista: list[dict]) -> dict:
    """Métricas del historial de UN cliente."""
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
        "top": sorted(([c, d["nombre"], d["unidades"]] for c, d in top.items()), key=lambda x: -x[2])[:5],
    }


def listar_usuarios() -> list[dict]:
    import db
    out = []
    for snap in db.client().collection(db.COL_USUARIOS).stream():
        d = snap.to_dict() or {}
        d["email"] = snap.id
        d.pop("password_hash", None)
        out.append(d)
    return sorted(out, key=lambda u: u["email"])


def sku_variante_manual(cod: str, color: str, talle: str) -> str:
    import re
    talle_n = (talle or "").strip().upper().replace(" ", "") or "U"
    slug = re.sub(r"[^A-Z0-9]", "", (color or "").strip().upper())[:12] or "MANUAL"
    return f"{cod}_{talle_n}_X{slug}"
