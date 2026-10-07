"""Administración (solo rol admin). Réplica 1:1 de lo que hacía `admin_ui.py` (Streamlit),
sobre los mismos módulos: overrides, catalog, pedidos, auth, email_notif, aleph_import,
reposicion, sitio. Nunca escribe en BigQuery.

Paquete (2026-10-07, antes un solo `admin.py` de 860 líneas): un módulo por pantalla del admin.
Todos cuelgan de este router con prefijo `/admin` y la dependencia `ctx_admin`."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from api.routers.admin import catalogo, categorias, clientes, configuracion, emails, home_menu, inicio, pedidos
from api.routers.admin.home_menu import HomeIn, MenuIn  # noqa: F401  (tests)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(deps.ctx_admin)])
for _m in (inicio, catalogo, categorias, clientes, pedidos, configuracion, emails, home_menu):
    router.include_router(_m.router)
