"""Helpers compartidos por los routers del admin."""
from __future__ import annotations

from api import deps

PUB_LABELS = {None: "Automático", True: "Publicado", False: "Oculto"}
EVENTO_LABEL = {"confirmacion": "Confirmación de pedido", "procesado": "Cambio a procesado",
                "cancelado": "Cancelación", "modificado": "Modificación"}

def _pub(v):
    return v if v in (True, False) else None


def _j(o):
    return deps.jsonable(o)
