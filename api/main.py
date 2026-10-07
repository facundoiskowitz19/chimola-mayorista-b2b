"""API JSON del mayorista (FastAPI) sobre los módulos Python existentes.

Corre con el root del repo en el PYTHONPATH (`import catalog`, `import pedidos`,
etc.). No reimplementa lógica de negocio: envuelve lo que ya usa el Streamlit.

    uvicorn api.main:app --reload --port 8000     (desde el root del repo)
"""
from __future__ import annotations

import logging
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.routers import admin, auth, carrito, catalogo, cuenta, home, pedidos, reposicion  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

_es_prod = os.getenv("APP_ENV", "dev").lower() == "prod"
app = FastAPI(title="Mayorista Lautin API", version="0.1.0",
              docs_url=None if _es_prod else "/docs", openapi_url=None if _es_prod else "/openapi.json")

# CORS solo hace falta en desarrollo local (Next en :3000 → API en :8000).
# En Cloud Run el front llega vía rewrite same-origin.
_origins = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, catalogo.router, carrito.router, pedidos.router, cuenta.router, home.router,
          reposicion.router, admin.router):
    app.include_router(r)


@app.get("/health")
def health():
    import catalog
    return {"ok": True, "catalogo_hace_seg": catalog.catalogo_actualizado_hace()}


@app.on_event("startup")
def _warmup():
    """Precarga catálogo + índice de fotos en background (cold start ~30 s)."""
    def run():
        try:
            import catalog
            import fotos
            catalog.load_variantes()
            fotos.indice_fotos()
            log.info("warmup listo")
        except Exception:  # noqa: BLE001
            log.exception("warmup falló")
    threading.Thread(target=run, daemon=True).start()
