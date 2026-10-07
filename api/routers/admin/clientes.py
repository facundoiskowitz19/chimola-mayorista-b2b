"""Admin → Clientes / usuarios: alta, ficha, cuenta, datos comerciales, password, activo, Aleph, reposición."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import adminlib
import aleph_import
import auth as auth_mod
import catalog
import db
import overrides
import pedidos as ped
import reposicion as repo

from api import deps
from api.routers.admin._common import _j

router = APIRouter()


# ---------------------------------------------------------------------------
# Clientes / usuarios
# ---------------------------------------------------------------------------
def _u_json(u: dict) -> dict:
    d = _j({k: v for k, v in u.items() if k != "password_hash"})
    return d


@router.get("/clientes")
def clientes():
    usuarios = adminlib.listar_usuarios()
    cods = sorted({int(u["cliente_cod"]) for u in usuarios if u.get("cliente_cod") is not None})
    efectivos = catalog.get_clientes(cods) if cods else {}
    out = []
    for u in usuarios:
        cod = u.get("cliente_cod")
        e = efectivos.get(int(cod)) if cod is not None else None
        out.append({**_u_json(u), "cliente": _j(e) if e else None})
    return {"items": out}


class UsuarioIn(BaseModel):
    email: str
    cliente_cod: int | None = None
    nombre: str = ""
    rol: str = "cliente"


def _nueva_password(email: str, pwd: str) -> dict:
    res = auth_mod.guardar_password_en_secret(email, pwd)
    return {"password": pwd, "en_secret": res["ok"],
            "aviso": None if res["ok"] else f"No se pudo guardar la password en el secret — anotala AHORA. ({res['error'][:180]})"}


@router.post("/clientes")
def crear_usuario(body: UsuarioIn):
    nombre = body.nombre.strip()
    if body.cliente_cod:
        cli = catalog.get_cliente(int(body.cliente_cod))
        if cli is None:
            raise HTTPException(422, f"cliente_cod {body.cliente_cod} no existe en dim_cliente")
        nombre = nombre or cli["nombre_display"]
    if body.rol not in ("cliente", "admin"):
        raise HTTPException(422, "Rol inválido (cliente o admin)")
    pwd = auth_mod.generar_password()
    try:
        auth_mod.crear_usuario(body.email, pwd, body.cliente_cod or None, nombre or body.email, rol=body.rol)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"email": body.email.strip().lower(), **_nueva_password(body.email.strip().lower(), pwd)}


@router.get("/clientes/{email}")
def ficha_cliente(email: str, dias: int | None = None):
    u = auth_mod.get_usuario(email)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    cod = u.get("cliente_cod")
    e = catalog.get_cliente(int(cod)) if cod is not None else None
    o = overrides.get_clientes_overrides().get(int(cod), {}) if cod is not None else {}
    lista = ped.listar_pedidos(int(cod)) if cod is not None else []
    pv = repo.pv_de_cliente(int(cod)) if cod is not None else None
    return {
        "usuario": _u_json(u), "cliente": _j(e) if e else None, "override": _j(o),
        "metricas": _j(adminlib.metricas_cliente(lista)) if cod is not None else None,
        "pedidos": [{k: _j(p.get(k)) for k in ("numero", "fecha_str", "estado", "unidades", "total")} for p in lista],
        "pv": _j(pv),
        "repo_dias_default": int(overrides.get_config().get("repo_dias_objetivo") or 21),
    }


class CuentaIn(BaseModel):
    rol: str
    cliente_cod: int | None = None


@router.put("/clientes/{email}/cuenta")
def guardar_cuenta(email: str, body: CuentaIn):
    u = auth_mod.get_usuario(email)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    nuevo = int(body.cliente_cod) if body.cliente_cod else None
    cambios: dict = {"rol": body.rol if body.rol in ("cliente", "admin") else "cliente", "cliente_cod": nuevo}
    if nuevo and nuevo != (int(u["cliente_cod"]) if u.get("cliente_cod") is not None else None):
        cli = catalog.get_cliente(nuevo)
        if cli is None:
            raise HTTPException(422, f"cliente_cod {nuevo} no existe en dim_cliente")
        cambios["nombre_display"] = cli["nombre_display"]
    db.usuario_ref(email).update(cambios)
    deps.invalidar_usuario(email)
    return {"ok": True}


class ComercialIn(BaseModel):
    descuento_pct: float | None = None
    lista_precios: int | None = None
    contacto_nombre: str = ""
    contacto_email: str = ""
    contacto_telefono: str = ""
    cuit: str | None = None
    odoo_cliente: str = ""
    notas: str = ""


@router.put("/clientes/{email}/comercial")
def guardar_comercial(email: str, body: ComercialIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    overrides.set_cliente_override(int(u["cliente_cod"]), {
        "descuento_pct": body.descuento_pct, "lista_precios": body.lista_precios,
        "contacto_nombre": body.contacto_nombre.strip(), "contacto_email": body.contacto_email.strip().lower(),
        "contacto_telefono": body.contacto_telefono.strip(), "cuit": (body.cuit or "").strip() or None,
        "odoo_cliente": body.odoo_cliente.strip(), "notas": body.notas.strip(),
    }, c.email)
    deps.invalidar_cliente(int(u["cliente_cod"]))
    return {"ok": True}


@router.post("/clientes/{email}/reset-password")
def reset_password(email: str):
    if not auth_mod.get_usuario(email):
        raise HTTPException(404, "Usuario no encontrado")
    pwd = auth_mod.generar_password()
    auth_mod.cambiar_password(email, pwd)
    deps.invalidar_usuario(email)
    return {"email": email, **_nueva_password(email, pwd)}


class ActivoIn(BaseModel):
    activo: bool


@router.post("/clientes/{email}/activo")
def set_activo(email: str, body: ActivoIn):
    if not auth_mod.get_usuario(email):
        raise HTTPException(404, "Usuario no encontrado")
    db.usuario_ref(email).update({"activo": bool(body.activo)})
    deps.invalidar_usuario(email)
    return {"ok": True}


class ImportIn(BaseModel):
    n: int = 3


@router.post("/clientes/{email}/importar-aleph")
def importar_aleph(email: str, body: ImportIn):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    try:
        msgs = aleph_import.importar(int(u["cliente_cod"]), max(1, min(int(body.n), 50)))
    except Exception as ex:  # noqa: BLE001
        msgs = [f"Error importando: {ex}"]
    return {"mensajes": msgs}


@router.get("/clientes/{email}/reposicion")
def reposicion_cliente(email: str, dias: int | None = Query(None, ge=7, le=90)):
    u = auth_mod.get_usuario(email)
    if not u or u.get("cliente_cod") is None:
        raise HTTPException(422, "El usuario no tiene cliente asociado")
    cod = int(u["cliente_cod"])
    e = catalog.get_cliente(cod) or {}
    dias = dias or int(overrides.get_config().get("repo_dias_objetivo") or 21)
    df = catalog.con_precio(catalog.variantes_publicadas(), int(e.get("lista_precios") or 1))
    pv, sug = repo.sugerencias(cod, df, dias)
    if pv is None:
        raise HTTPException(403, "No es franquicia")
    cols = ["producto_cod", "producto_nombre", "color", "talle", "vendidas_30d", "stock_pv", "sugerido"]
    return {"pv": _j(pv), "dias": dias, "items": _j(sug[cols]) if not sug.empty else []}
