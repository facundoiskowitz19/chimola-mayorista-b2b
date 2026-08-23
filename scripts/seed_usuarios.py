"""Semillas: crea usuarios de prueba en Firestore con passwords aleatorias y
guarda el mapa {email: password} en Secret Manager (`mayorista-seed-passwords`)
para compartirlo con el equipo de prueba. Nunca imprime las passwords salvo `--print`.

Uso (con ADC apuntando a DEV):
  ./venv/bin/python scripts/seed_usuarios.py                 # crea los 3 de PLAN.md
  ./venv/bin/python scripts/seed_usuarios.py --print         # además muestra las passwords
  ./venv/bin/python scripts/seed_usuarios.py --reset         # regenera password de los existentes
  ./venv/bin/python scripts/seed_usuarios.py --email x@y.com --cliente 2722 --nombre "X"   # uno custom
"""
from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
import config  # noqa: E402

SEED = [
    {"email": "franquicia_jujuy_test@lautin.com.ar", "cliente_cod": 2722, "nombre": "Franquicia Jujuy (test)", "rol": "cliente"},
    {"email": "franquicia_mendoza_test@lautin.com.ar", "cliente_cod": 2723, "nombre": "Franquicia Mendoza (test)", "rol": "cliente"},
    {"email": "admin@lautin.com.ar", "cliente_cod": None, "nombre": "Admin Chimola", "rol": "admin"},
]
SECRET_NAME = "mayorista-seed-passwords"
ALFABETO = string.ascii_letters + string.digits


def nueva_password(n: int = 14) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(n))


def guardar_en_secret_manager(passwords: dict[str, str]) -> None:
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{config.GCP_PROJECT}"
    try:
        client.create_secret(request={"parent": parent, "secret_id": SECRET_NAME,
                                      "secret": {"replication": {"automatic": {}}}})
    except AlreadyExists:
        pass
    # Merge con lo que ya había (para no perder usuarios anteriores)
    previo = {}
    try:
        resp = client.access_secret_version(request={"name": f"{parent}/secrets/{SECRET_NAME}/versions/latest"})
        previo = json.loads(resp.payload.data.decode("utf-8"))
    except Exception:  # noqa: BLE001
        pass
    previo.update(passwords)
    client.add_secret_version(request={"parent": f"{parent}/secrets/{SECRET_NAME}",
                                       "payload": {"data": json.dumps(previo, indent=2).encode("utf-8")}})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", help="mostrar passwords por stdout")
    ap.add_argument("--reset", action="store_true", help="regenerar password si el usuario existe")
    ap.add_argument("--no-secret", action="store_true", help="no guardar en Secret Manager")
    ap.add_argument("--email"); ap.add_argument("--cliente", type=int); ap.add_argument("--nombre")
    ap.add_argument("--rol", default="cliente")
    args = ap.parse_args()

    usuarios = SEED
    if args.email:
        usuarios = [{"email": args.email, "cliente_cod": args.cliente, "nombre": args.nombre or args.email, "rol": args.rol}]

    print(f"Proyecto Firestore: {config.FIRESTORE_PROJECT} (APP_ENV={config.APP_ENV})")
    passwords: dict[str, str] = {}
    for u in usuarios:
        existe = auth.get_usuario(u["email"]) is not None
        if existe and not args.reset:
            print(f"  = {u['email']} ya existe (usar --reset para regenerar password)")
            continue
        pwd = nueva_password()
        if existe:
            auth.cambiar_password(u["email"], pwd)
            print(f"  ~ {u['email']} password regenerada")
        else:
            auth.crear_usuario(u["email"], pwd, u["cliente_cod"], u["nombre"], rol=u["rol"])
            print(f"  + {u['email']} creado (cliente_cod={u['cliente_cod']}, rol={u['rol']})")
        passwords[u["email"]] = pwd

    if passwords and not args.no_secret:
        guardar_en_secret_manager(passwords)
        print(f"Passwords guardadas en Secret Manager: {config.GCP_PROJECT}/{SECRET_NAME}")
        print(f"  ver: gcloud secrets versions access latest --secret={SECRET_NAME} --project={config.GCP_PROJECT}")
    if passwords and args.print:
        for e, p in passwords.items():
            print(f"  {e}: {p}")


if __name__ == "__main__":
    main()
