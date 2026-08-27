"""Configuración central. Todo por variable de entorno (con defaults DEV).

En Cloud Run las secrets llegan como env (`--set-secrets`). Local: `.env`.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "dev")                       # dev | prod
GCP_PROJECT = os.getenv("GCP_PROJECT", "chimola-deteccion")
BQ_PROJECT = os.getenv("BQ_PROJECT", GCP_PROJECT)
FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT", GCP_PROJECT)
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "(default)")

DS_MARTS = os.getenv("BQ_DS_MARTS", "franquicias_marts")
DS_DWH = os.getenv("BQ_DS_DWH", "franquicias_dwh")
DS_RAW = os.getenv("BQ_DS_RAW", "franquicias_raw")

V_STOCK_OMNI = f"`{BQ_PROJECT}.{DS_MARTS}.stock_omnicanal`"
V_STOCK_CENTRAL = f"`{BQ_PROJECT}.{DS_MARTS}.v_stock_central_actual`"
T_STOCK_RAW = f"`{BQ_PROJECT}.{DS_RAW}.stock`"
T_ARTICULOSOL = f"`{BQ_PROJECT}.{DS_RAW}.articulosol`"
T_DIM_CLIENTE = f"`{BQ_PROJECT}.{DS_DWH}.dim_cliente`"

# Safeguard: tope de bytes por query (1 GB).
MAX_BYTES_BILLED = int(os.getenv("MAX_BYTES_BILLED", str(1_000_000_000)))

# Fotos (bucket vive en PROD; público hoy, igual firmamos URLs).
BUCKET_FOTOS = os.getenv("BUCKET_FOTOS", "ecommerce-b2b-imagenes")
FOTOS_PREFIX = os.getenv("FOTOS_PREFIX", "catalogo/fotos_productos")
FOTO_URL_TTL_SEG = int(os.getenv("FOTO_URL_TTL_SEG", "3600"))

# Backup de pedidos.
BUCKET_PEDIDOS = os.getenv("BUCKET_PEDIDOS", "chimola-mayorista-pedidos-dev")

# Email.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_SECRET_PROJECT = os.getenv("SMTP_SECRET_PROJECT", "chimola-490015")
SMTP_SECRET_NAME = os.getenv("SMTP_SECRET_NAME", "email-smtp-credentials")
# Email de Chimola que recibe los pedidos (a definir con el equipo; DEV → fiskowitz).
PEDIDOS_EMAIL_TO = [e.strip() for e in os.getenv("PEDIDOS_EMAIL_TO", "fiskowitz@lautin.com.ar").split(",") if e.strip()]
# DEV: si está seteado, TODOS los mails van a esta casilla (no molestar a clientes reales).
EMAIL_OVERRIDE_TO = os.getenv("EMAIL_OVERRIDE_TO", "").strip()
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"

# Auth.
JWT_TTL_HORAS = int(os.getenv("JWT_TTL_HORAS", "24"))
JWT_SECRET_NAME = os.getenv("JWT_SECRET_NAME", "mayorista-jwt-key")
LOGIN_MAX_INTENTOS = int(os.getenv("LOGIN_MAX_INTENTOS", "5"))
LOGIN_VENTANA_MIN = int(os.getenv("LOGIN_VENTANA_MIN", "15"))
COOKIE_NAME = "mayorista_session"

# Catálogo.
CATALOGO_TTL_SEG = int(os.getenv("CATALOGO_TTL_SEG", "1800"))
ITEMS_POR_PAGINA = int(os.getenv("ITEMS_POR_PAGINA", "24"))

TZ = "America/Argentina/Buenos_Aires"


@lru_cache(maxsize=32)
def get_secret(name: str, project: str | None = None) -> str:
    """Lee la última versión de un secret de Secret Manager (cacheado)."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{project or GCP_PROJECT}/secrets/{name}/versions/latest"
    return client.access_secret_version(request={"name": path}).payload.data.decode("utf-8")


def jwt_secret() -> str:
    """Clave de firma JWT: env `JWT_KEY` (Cloud Run / .env) o Secret Manager."""
    key = os.getenv("JWT_KEY")
    if key:
        return key
    return get_secret(JWT_SECRET_NAME, GCP_PROJECT)
