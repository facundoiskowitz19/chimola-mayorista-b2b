"""Login / logout / me. Misma cookie JWT (`mayorista_session`) que el Streamlit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import auth as auth_mod
import config

from api import deps

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    token, user, err = auth_mod.login(body.email, body.password)
    if err:
        raise HTTPException(401, err)
    response.set_cookie(
        deps.COOKIE, token, max_age=config.JWT_TTL_HORAS * 3600, httponly=True,
        samesite="lax", secure=_secure(request), path="/",
    )
    claims = auth_mod.verify_jwt(token) or {}
    ctx = deps.Ctx(claims, deps.get_cliente(claims.get("cliente_cod")))
    return ctx.publico()


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(deps.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(c: deps.Ctx = Depends(deps.ctx_requerido)):
    return c.publico()
