"""Admin → Inicio: KPIs de pedidos y salud del catálogo."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

import adminlib
import catalog
import fotos
import overrides
import pedidos as ped

from api.routers.admin._common import _j

router = APIRouter()


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------
@router.get("/inicio")
def inicio():
    lista = ped.listar_pedidos(None, limit=2000)
    k = adminlib.kpis(lista, dt.datetime.now(dt.timezone.utc))
    df = catalog.variantes_admin()
    prods = df.groupby("producto_cod").agg(publicado=("publicado", "first"), precio1=("precio1", "first")).reset_index()
    return {
        **_j(k),
        "salud": {
            "productos": int(len(prods)),
            "ocultos": int(prods["publicado"].map(lambda v: v is False).sum()),
            "sin_foto": int((~prods["producto_cod"].map(fotos.tiene_fotos)).sum()),
            "sin_precio_l1": int((prods["precio1"] <= 0).sum()),
            "con_overrides": len(overrides.get_catalogo_overrides()),
        },
        "catalogo_hace_seg": catalog.catalogo_actualizado_hace(),
    }
