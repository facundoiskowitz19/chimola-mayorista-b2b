"""Admin → Plantillas de email por evento: preview, guardar, reset, prueba."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import email_notif
import overrides
import pedidos as ped

from api import deps
from api.routers.admin._common import EVENTO_LABEL, _j

router = APIRouter()


VARIABLES_EMAIL = ("numero", "cliente", "cliente_cod", "usuario", "contacto", "fecha", "unidades",
                   "subtotal", "descuento_pct", "descuento_monto", "total", "iva_pct", "iva_monto",
                   "total_con_iva", "lineas_iva", "lista_precios", "observaciones", "detalle", "quien",
                   "estado", "cambios", "ahorro_descvta", "linea_ahorro")



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
