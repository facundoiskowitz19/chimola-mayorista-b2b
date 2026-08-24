"""Firestore: usuarios, pedidos, carritos, login_attempts, contadores."""
from __future__ import annotations

from functools import lru_cache

from google.cloud import firestore

import config

COL_USUARIOS = "usuarios"          # doc id = email (lowercase) → unicidad gratis
COL_PEDIDOS = "pedidos"            # doc id = numero zero-padded (ej: 000012)
COL_CARRITOS = "carritos"          # doc id = email
COL_LOGIN_ATTEMPTS = "login_attempts"
COL_CONTADORES = "contadores"
COL_CATALOGO_OVERRIDES = "catalogo_overrides"   # doc id = producto_cod
COL_CLIENTES_OVERRIDES = "clientes_overrides"   # doc id = cliente_cod
COL_CONFIG = "config"                            # doc único: global


@lru_cache(maxsize=1)
def client() -> firestore.Client:
    return firestore.Client(project=config.FIRESTORE_PROJECT, database=config.FIRESTORE_DATABASE)


def usuario_ref(email: str):
    return client().collection(COL_USUARIOS).document(email.strip().lower())


def carrito_ref(email: str):
    return client().collection(COL_CARRITOS).document(email.strip().lower())


def pedidos_col():
    return client().collection(COL_PEDIDOS)


def catalogo_overrides_col():
    return client().collection(COL_CATALOGO_OVERRIDES)


def clientes_overrides_col():
    return client().collection(COL_CLIENTES_OVERRIDES)


def config_ref():
    return client().collection(COL_CONFIG).document("global")


def emails_ref():
    return client().collection(COL_CONFIG).document("emails")


@firestore.transactional
def _next_numero(tx, ref):
    snap = ref.get(transaction=tx)
    actual = int(snap.get("valor")) if snap.exists and snap.get("valor") is not None else 0
    tx.set(ref, {"valor": actual + 1})
    return actual + 1


def proximo_numero_pedido() -> int:
    """Numerador secuencial de pedidos (transacción)."""
    ref = client().collection(COL_CONTADORES).document("pedidos")
    return _next_numero(client().transaction(), ref)
