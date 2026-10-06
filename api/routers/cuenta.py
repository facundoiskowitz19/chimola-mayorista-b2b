"""Mis datos: contacto editable y cambio de contraseña."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth as auth_mod
import overrides

from api import deps

router = APIRouter(prefix="/cuenta", tags=["cuenta"])


class ContactoIn(BaseModel):
    contacto_nombre: str = ""
    contacto_email: str = ""
    contacto_telefono: str = ""


class PasswordIn(BaseModel):
    actual: str
    nueva: str


@router.put("/contacto")
def contacto(body: ContactoIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    overrides.set_cliente_override(int(c.cliente_cod), {k: v.strip() for k, v in body.model_dump().items()}, c.email)
    deps.invalidar_cliente(c.cliente_cod)
    return deps.Ctx({"sub": c.email, "rol": c.rol, "cliente_cod": c.cliente_cod, "nombre": c.nombre},
                    deps.get_cliente(c.cliente_cod)).publico()


@router.post("/password")
def password(body: PasswordIn, c: deps.Ctx = Depends(deps.ctx_requerido)):
    u = auth_mod.get_usuario(c.email)
    if not u or not auth_mod.verify_password(body.actual, u.get("password_hash")):
        raise HTTPException(401, "La contraseña actual no es correcta")
    if len(body.nueva) < 8:
        raise HTTPException(422, "La nueva contraseña debe tener al menos 8 caracteres")
    auth_mod.cambiar_password(c.email, body.nueva)
    return {"ok": True}
