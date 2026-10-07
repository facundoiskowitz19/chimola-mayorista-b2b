"""Admin → Config global del sitio y refresco de caches."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import catalog
import fotos
import overrides
import reposicion as repo
import sitio

from api import deps
from api.routers.admin._common import _j

router = APIRouter()


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
    deps.invalidar_todo()
    repo.invalidar()
    return {"ok": True, "catalogo_hace_seg": catalog.catalogo_actualizado_hace()}
