"""Admin → Home del sitio (por sección, con upload de imágenes) y menú desplegable."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

import sitio

from api import deps

router = APIRouter()


# ---------------------------------------------------------------------------
# Home + menú del sitio
# ---------------------------------------------------------------------------
@router.get("/home/{seccion}")
def home_admin(seccion: str):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    return {"seccion": seccion, "config": sitio.get_home(seccion), "personalizada": sitio.es_personalizada(seccion),
            "defaults": sitio.DEFAULTS[seccion], "tipos_seccion": sitio.TIPOS_SECCION}


class HomeIn(BaseModel):
    """Forma exacta de la home de una sección. `extra="forbid"`: un payload con otra forma (p. ej. la
    respuesta del GET reenviada) se rechaza en vez de guardarse como home vacía."""
    model_config = ConfigDict(extra="forbid")
    hero: list[dict] = []
    bloques: list[dict] = []
    secciones: list[dict] = []
    banner_grilla: dict | None = None
    banners_catalogo: list[dict] = []


@router.put("/home/{seccion}")
def set_home(seccion: str, body: HomeIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_home(seccion, body.model_dump(), c.email)
    return {"ok": True}


@router.delete("/home/{seccion}")
def reset_home(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.reset_home(seccion, c.email)
    return {"ok": True}


@router.post("/home/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(422, "Solo imágenes")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "Máximo 10 MB")
    return {"url": sitio.subir_imagen(data, file.filename or "imagen.jpg", file.content_type)}


@router.get("/menu/{seccion}")
def menu_admin(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    df = deps.df_cliente(c)
    return {"seccion": seccion, "auto": sitio.menu_auto(df, seccion), "config": sitio.get_menu(seccion),
            "efectivo": sitio.menu_efectivo(df, seccion), "tope_auto": sitio.MENU_AUTO_TOPE}


class MenuIn(BaseModel):
    """Listas del menú de una sección (vacías = automático). Misma política estricta que HomeIn."""
    model_config = ConfigDict(extra="forbid")
    temporadas: list[dict] = []
    tipos: list[dict] = []
    tendencias: list[dict] = []
    oportunidades: list[dict] = []
    grupos: list[dict] = []


@router.put("/menu/{seccion}")
def set_menu(seccion: str, body: MenuIn, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.set_menu(seccion, body.model_dump(), c.email)
    return {"ok": True}


@router.delete("/menu/{seccion}")
def reset_menu(seccion: str, c: deps.Ctx = Depends(deps.ctx_admin)):
    if seccion not in sitio.SECCIONES:
        raise HTTPException(404, "Sección desconocida")
    sitio.reset_menu(seccion, c.email)
    return {"ok": True}
