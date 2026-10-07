"""Pedidos: confirmar, historial, Excel, cancelar, repetir, export Odoo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import fotos
import odoo_export
import overrides
import pedidos as ped
import reposicion

from api import deps

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


class ConfirmarIn(BaseModel):
    contacto_nombre: str = ""
    contacto_email: str = ""
    contacto_telefono: str = ""
    observaciones: str = ""


def _pedido_json(p: dict, c: deps.Ctx) -> dict:
    d = deps.jsonable(p)
    for it in d.get("items", []):
        it["foto"] = fotos.url_variante_publica(it.get("producto_cod") or "", it.get("color")) or None
    d["puede_cancelar"] = ped.puede_cancelar(p, c.usuario_dict())
    d["odoo"] = _es_franquicia_pedido(p) and p.get("estado") != "cancelado"
    return d


@router.get("")
def listar(c: deps.Ctx = Depends(deps.ctx_requerido)):
    if not c.es_admin and c.cliente_cod is None:
        return {"items": []}
    lista = ped.listar_pedidos(None if c.es_admin else c.cliente_cod)
    resumen = []
    for p in lista:
        resumen.append({k: deps.jsonable(p.get(k)) for k in ("numero", "fecha_str", "confirmed_at", "estado", "unidades",
                                                              "total", "total_con_iva", "cliente_nombre", "cliente_cod",
                                                              "xlsx_filename", "observaciones")}
                       | {"n_items": len(p.get("items", []))})
    return {"items": resumen}


@router.get("/{numero}")
def detalle(numero: int, c: deps.Ctx = Depends(deps.ctx_requerido)):
    p = _get(numero, c)
    return _pedido_json(p, c)


def _es_franquicia_pedido(p: dict) -> bool:
    """El export Odoo depende del cliente DEL PEDIDO (no del que mira: un admin no tiene cliente)."""
    try:
        return reposicion.pv_de_cliente(int(p.get("cliente_cod"))) is not None
    except (TypeError, ValueError):
        return False


def _get(numero: int, c: deps.Ctx) -> dict:
    p = ped.get_pedido(numero)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    if not c.es_admin and int(p.get("cliente_cod", -1)) != int(c.cliente_cod or -2):
        raise HTTPException(403, "No es tu pedido")
    return p


@router.post("")
def confirmar(body: ConfirmarIn, c: deps.Ctx = Depends(deps.ctx_cliente)):
    items = ped.cargar_carrito(c.email)
    if not items:
        raise HTTPException(422, "El carrito está vacío")
    cli = dict(c.cliente or {})
    # Contacto: si cambió, queda guardado para la próxima (igual que el Streamlit).
    cambios = {k: getattr(body, k).strip() for k in ("contacto_nombre", "contacto_email", "contacto_telefono")
               if getattr(body, k).strip() != (cli.get(k) or "")}
    if cambios:
        overrides.set_cliente_override(int(cli["cliente_cod"]), cambios, c.email)
        deps.invalidar_cliente(cli["cliente_cod"])
    cli.update({k: getattr(body, k).strip() for k in ("contacto_nombre", "contacto_email", "contacto_telefono")})
    try:
        p, _xlsx = ped.confirmar_pedido(c.usuario_dict(), cli, items, body.observaciones)
    except ped.StockInsuficiente as e:
        # Ajustar el carrito a lo disponible y devolver el detalle (sin números de stock).
        prob = {x["sku"]: x for x in e.problemas}
        nuevos = []
        for it in items:
            if it["sku"] in prob:
                disp = int(prob[it["sku"]]["disponible"])
                if disp > 0:
                    nuevos.append({**it, "cantidad": disp, "stock": disp})
            else:
                nuevos.append(it)
        ped.guardar_carrito(c.email, nuevos)
        raise HTTPException(409, {"tipo": "stock", "mensaje": "Algunas cantidades superan la disponibilidad actual. "
                                  "Ajustamos tu carrito: revisalo y confirmá de nuevo.",
                                  "skus": list(prob)})
    except ped.MinimoNoAlcanzado as e:
        raise HTTPException(422, {"tipo": "minimo_unidades", "mensaje": str(e)})
    except ped.MinimoMontoNoAlcanzado as e:
        raise HTTPException(422, {"tipo": "minimo_monto", "mensaje": str(e)})
    except ValueError as e:
        raise HTTPException(422, {"tipo": "error", "mensaje": str(e)})
    return _pedido_json(p, c)


@router.get("/{numero}/excel")
def excel(numero: int, c: deps.Ctx = Depends(deps.ctx_requerido)):
    p = _get(numero, c)
    data = ped.generar_excel(p)
    fn = p.get("xlsx_filename") or f"pedido_{numero:06d}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/{numero}/odoo")
def odoo(numero: int, c: deps.Ctx = Depends(deps.ctx_requerido)):
    p = _get(numero, c)
    if not _es_franquicia_pedido(p):
        raise HTTPException(403, "Solo franquicias")
    ov_cli = overrides.get_clientes_overrides().get(int(p.get("cliente_cod") or -1), {})
    nombre = ov_cli.get("odoo_cliente") or p.get("cliente_nombre") or ""
    data = odoo_export.generar_excel_odoo(p, nombre)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{odoo_export.nombre_archivo(p)}"'})


@router.post("/{numero}/cancelar")
def cancelar(numero: int, c: deps.Ctx = Depends(deps.ctx_cliente)):
    _get(numero, c)
    try:
        p = ped.cancelar_por_cliente(numero, c.usuario_dict())
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _pedido_json(ped.get_pedido(numero) or p, c)


@router.post("/{numero}/repetir")
def repetir(numero: int, c: deps.Ctx = Depends(deps.ctx_cliente)):
    """Carga en el carrito las variantes del pedido, a precio actual y recortado al stock."""
    p = _get(numero, c)
    df = deps.df_cliente(c)
    nuevos, avisos = ped.repetir_pedido(p, df)
    items = ped.cargar_carrito(c.email)
    for it in nuevos:
        items = ped.agregar_al_carrito(items, it)
    ped.guardar_carrito(c.email, items)
    return {"agregadas": sum(i["cantidad"] for i in nuevos), "avisos": avisos, "n_items": len(items)}
