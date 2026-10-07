"""Admin → Pedidos: listado con filtros, cambio de estado, reenvío de email, modificación."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import adminlib
import email_notif
import pedidos as ped

from api import deps
from api.routers.admin._common import _j

router = APIRouter()


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
@router.get("/pedidos")
def pedidos_admin(estado: str | None = None, cliente_cod: int | None = None, desde: str | None = None):
    lista = ped.listar_pedidos(None)
    counts = {"todos": len(lista)}
    for e in ("confirmado", "procesado", "cancelado"):
        counts[e] = sum(1 for p in lista if p.get("estado") == e)
    try:
        d0 = dt.date.fromisoformat(desde) if desde else None
    except ValueError:
        raise HTTPException(422, "Fecha «desde» inválida (AAAA-MM-DD)")
    filt = [p for p in lista
            if (not estado or p.get("estado") == estado)
            and (cliente_cod is None or int(p.get("cliente_cod", -1)) == cliente_cod)
            and (not d0 or p["confirmed_at"].astimezone(adminlib.TZ).date() >= d0)]
    return {
        "counts": counts,
        "clientes": sorted({(int(p["cliente_cod"]), str(p.get("cliente_nombre") or "")) for p in lista}),
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
