"""Login email + password (bcrypt), sesión JWT (TTL 24h) y rate limit en login.

Usuarios viven en Firestore `usuarios/{email}`:
  {email, password_hash, cliente_cod, nombre_display, rol: cliente|admin, activo, created_at}
"""
from __future__ import annotations

import datetime as dt
import logging

import bcrypt
import jwt
from google.cloud import firestore

import config
import db

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(pwd: str, pwd_hash: str | None) -> bool:
    if not pwd or not pwd_hash:
        return False
    try:
        return bcrypt.checkpw(pwd.encode("utf-8"), pwd_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_jwt(user: dict, ttl_hours: int | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user["email"],
        "cliente_cod": int(user["cliente_cod"]) if user.get("cliente_cod") is not None else None,
        "rol": user.get("rol", "cliente"),
        "nombre": user.get("nombre_display", ""),
        "iat": now,
        "exp": now + dt.timedelta(hours=ttl_hours or config.JWT_TTL_HORAS),
    }
    return jwt.encode(payload, config.jwt_secret(), algorithm="HS256")


def verify_jwt(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, config.jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as e:
        log.info("JWT inválido: %s", e)
        return None


# ---------------------------------------------------------------------------
# Rate limit (Firestore, sobrevive a múltiples instancias de Cloud Run)
# ---------------------------------------------------------------------------
def _attempts_ref(email: str):
    return db.client().collection(db.COL_LOGIN_ATTEMPTS).document(email.strip().lower())


def bloqueado(email: str) -> int:
    """Minutos restantes de bloqueo (0 = no bloqueado)."""
    snap = _attempts_ref(email).get()
    if not snap.exists:
        return 0
    d = snap.to_dict() or {}
    desde = d.get("ventana_desde")
    if not desde:
        return 0
    fin = desde + dt.timedelta(minutes=config.LOGIN_VENTANA_MIN)
    ahora = dt.datetime.now(dt.timezone.utc)
    if ahora >= fin:
        return 0
    if int(d.get("intentos", 0)) >= config.LOGIN_MAX_INTENTOS:
        return max(1, int((fin - ahora).total_seconds() // 60) + 1)
    return 0


def _registrar_fallo(email: str) -> None:
    ref = _attempts_ref(email)
    snap = ref.get()
    ahora = dt.datetime.now(dt.timezone.utc)
    d = snap.to_dict() if snap.exists else {}
    desde = d.get("ventana_desde")
    if not desde or ahora - desde > dt.timedelta(minutes=config.LOGIN_VENTANA_MIN):
        ref.set({"ventana_desde": ahora, "intentos": 1})
    else:
        ref.update({"intentos": firestore.Increment(1)})


def _limpiar_fallos(email: str) -> None:
    _attempts_ref(email).delete()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def get_usuario(email: str) -> dict | None:
    snap = db.usuario_ref(email).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d["email"] = snap.id
    return d


def crear_usuario(email: str, password: str, cliente_cod: int | None, nombre_display: str,
                  rol: str = "cliente", activo: bool = True, sobrescribir: bool = False) -> dict:
    email = (email or "").strip().lower()
    # Email vacío/roto → Firestore devuelve un 400 críptico (path 'usuarios/'
    # con trailing slash). Validar acá con un error humano.
    if not email or "@" not in email or " " in email or "/" in email \
            or "." not in email.split("@")[-1]:
        raise ValueError("Email inválido: completá una dirección real (ej: persona@empresa.com)")
    ref = db.usuario_ref(email)
    if ref.get().exists and not sobrescribir:
        raise ValueError(f"El usuario {email} ya existe")
    doc = {
        "email": email,
        "password_hash": hash_password(password),
        "cliente_cod": int(cliente_cod) if cliente_cod is not None else None,
        "nombre_display": nombre_display,
        "rol": rol,
        "activo": activo,
        "created_at": dt.datetime.now(dt.timezone.utc),
    }
    ref.set(doc)
    return doc


def generar_password(n: int = 14) -> str:
    import secrets as _secrets
    import string
    alfabeto = string.ascii_letters + string.digits
    return "".join(_secrets.choice(alfabeto) for _ in range(n))


def guardar_password_en_secret(email: str, password: str,
                               secret_name: str = "mayorista-seed-passwords") -> None:
    """Merge {email: password} en el secret (mismo formato que scripts/seed_usuarios.py)."""
    import json

    from google.api_core.exceptions import AlreadyExists
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{config.GCP_PROJECT}"
    try:
        client.create_secret(request={"parent": parent, "secret_id": secret_name,
                                      "secret": {"replication": {"automatic": {}}}})
    except AlreadyExists:
        pass
    previo = {}
    try:
        resp = client.access_secret_version(request={"name": f"{parent}/secrets/{secret_name}/versions/latest"})
        previo = json.loads(resp.payload.data.decode("utf-8"))
    except Exception:  # noqa: BLE001 — primera versión
        pass
    previo[email.strip().lower()] = password
    client.add_secret_version(request={"parent": f"{parent}/secrets/{secret_name}",
                                       "payload": {"data": json.dumps(previo, indent=2).encode("utf-8")}})


def cambiar_password(email: str, password: str) -> None:
    db.usuario_ref(email).update({"password_hash": hash_password(password),
                                  "password_updated_at": dt.datetime.now(dt.timezone.utc)})


def login(email: str, password: str) -> tuple[str | None, dict | None, str | None]:
    """→ (jwt, user, error). Mensaje de error genérico (no revela si el email existe)."""
    email = (email or "").strip().lower()
    if not email or not password:
        return None, None, "Ingresá email y contraseña."
    mins = bloqueado(email)
    if mins:
        return None, None, f"Demasiados intentos. Probá de nuevo en {mins} min."
    user = get_usuario(email)
    if not user or not user.get("activo", True) or not verify_password(password, user.get("password_hash")):
        _registrar_fallo(email)
        log.info("Login fallido: %s", email)
        return None, None, "Email o contraseña incorrectos."
    _limpiar_fallos(email)
    db.usuario_ref(email).update({"last_login_at": dt.datetime.now(dt.timezone.utc)})
    log.info("Login ok: %s (cliente_cod=%s rol=%s)", email, user.get("cliente_cod"), user.get("rol"))
    return create_jwt(user), user, None
