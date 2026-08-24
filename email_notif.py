"""Email de confirmación de pedido (SMTP Gmail Workspace, secret del pipeline hermano).

Secret `email-smtp-credentials` (Secret Manager, proyecto chimola-490015): JSON {user, password}.
"""
from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache

import config

log = logging.getLogger(__name__)

XLSX_MIME = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@lru_cache(maxsize=1)
def _smtp_creds() -> tuple[str, str]:
    payload = json.loads(config.get_secret(config.SMTP_SECRET_NAME, config.SMTP_SECRET_PROJECT))
    return payload["user"], payload["password"]


def _fmt(n: float) -> str:
    return f"$ {n:,.0f}".replace(",", ".")


def cuerpo_pedido(pedido: dict) -> str:
    lineas = [
        f"Pedido N° {pedido['numero']} — {pedido['cliente_nombre']} (cliente {pedido['cliente_cod']})",
        f"Fecha: {pedido['fecha_str']}",
        f"Usuario: {pedido['usuario_email']}",
        "",
        f"Unidades: {pedido['unidades']}",
        f"Subtotal (lista {pedido['lista_precios']}, sin IVA): {_fmt(pedido['subtotal'])}",
        f"Descuento cabecera {pedido['descuento_pct']:g}%: -{_fmt(pedido['descuento_monto'])}",
        f"TOTAL: {_fmt(pedido['total'])}",
    ]
    if float(pedido.get("iva_pct") or 0) > 0:
        lineas += [f"IVA {pedido['iva_pct']:g}%: {_fmt(pedido.get('iva_monto', 0))}",
                   f"TOTAL c/IVA: {_fmt(pedido.get('total_con_iva', 0))}"]
    lineas.append("")
    if pedido.get("observaciones"):
        lineas += ["Observaciones:", pedido["observaciones"], ""]
    lineas.append("Detalle:")
    for it in pedido["items"]:
        lineas.append(f"  - {it['producto_cod']} {it['producto_nombre']} | {it['color']} | T {it['talle']} "
                      f"| {it['cantidad']} u × {_fmt(it['precio_unit'])} = {_fmt(it['subtotal'])}")
    lineas += ["", "El Excel del pedido va adjunto.", "", "— Mayorista Chimola / Lautin"]
    return "\n".join(lineas)


def _destinatarios(pedido: dict) -> tuple[list[str], list[str]]:
    """(to, chimola). Destino Chimola administrable (config/global, fallback env).
    En DEV, `EMAIL_OVERRIDE_TO` redirige todo."""
    import overrides

    cliente = [pedido["usuario_email"]]
    chimola = overrides.pedidos_email_to()
    if config.EMAIL_OVERRIDE_TO:
        return [config.EMAIL_OVERRIDE_TO], []
    return cliente, chimola


ASUNTO_ESTADO = {
    "procesado": "Tu pedido N° {n} fue procesado por Lautin",
    "cancelado": "Pedido N° {n} cancelado",
}


def cuerpo_estado(pedido: dict, nuevo: str, por: str) -> str:
    base = [f"Pedido N° {pedido['numero']} — {pedido['cliente_nombre']} (cliente {pedido['cliente_cod']})",
            f"Fecha del pedido: {pedido['fecha_str']} · {pedido['unidades']} u. · total {_fmt(pedido['total'])}", ""]
    if nuevo == "procesado":
        base += ["El equipo de Lautin procesó tu pedido y ya está en preparación.",
                 "El detalle está en el Excel que recibiste al confirmarlo."]
    elif nuevo == "cancelado":
        quien = "el cliente" if por == pedido.get("usuario_email") else "el equipo de Lautin"
        base += [f"El pedido fue CANCELADO por {quien} ({por}).",
                 "Si fue un error, respondé este mail o contactá a Lautin."]
    else:
        base += [f"El pedido pasó al estado: {nuevo}."]
    base += ["", "— Mayorista Lautin"]
    return "\n".join(base)


def enviar_cambio_estado(pedido: dict, nuevo: str, por: str) -> dict:
    """Notifica al cliente + Chimola el cambio de estado. Best-effort, nunca levanta."""
    to, chimola = _destinatarios(pedido)
    todos = to + chimola
    if not config.EMAIL_ENABLED:
        return {"enviado": False, "destinatarios": todos, "error": "deshabilitado"}
    try:
        user, password = _smtp_creds()
        subject = "[Mayorista Lautin] " + ASUNTO_ESTADO.get(nuevo, f"Pedido N° {{n}} — {nuevo}").format(n=pedido["numero"])
        body = cuerpo_estado(pedido, nuevo, por)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            for dest in (to, chimola):
                if not dest:
                    continue
                msg = EmailMessage()
                msg["From"] = user
                msg["To"] = ", ".join(dest)
                msg["Subject"] = subject
                msg.set_content(body)
                smtp.send_message(msg)
        log.info("Email estado %s del pedido %s enviado a %s", nuevo, pedido["numero"], todos)
        return {"enviado": True, "destinatarios": todos, "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("Fallo email de estado %s del pedido %s", nuevo, pedido.get("numero"))
        return {"enviado": False, "destinatarios": todos, "error": str(e)}


def enviar_confirmacion(pedido: dict, xlsx_bytes: bytes, filename: str) -> dict:
    """Envía 1 mail al cliente + 1 a Chimola con el Excel adjunto.
    Devuelve {enviado: bool, destinatarios: [...], error: str|None}. Nunca levanta."""
    to, chimola = _destinatarios(pedido)
    todos = to + chimola
    if not config.EMAIL_ENABLED:
        log.info("EMAIL_ENABLED=false; no envío a %s", todos)
        return {"enviado": False, "destinatarios": todos, "error": "deshabilitado"}
    try:
        user, password = _smtp_creds()
        subject = f"[Mayorista Chimola] Pedido N° {pedido['numero']} — {pedido['cliente_nombre']}"
        body = cuerpo_pedido(pedido)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            for dest in (to, chimola):
                if not dest:
                    continue
                msg = EmailMessage()
                msg["From"] = user
                msg["To"] = ", ".join(dest)
                msg["Subject"] = subject
                msg.set_content(body)
                msg.add_attachment(xlsx_bytes, maintype=XLSX_MIME[0], subtype=XLSX_MIME[1], filename=filename)
                smtp.send_message(msg)
        log.info("Email pedido %s enviado a %s", pedido["numero"], todos)
        return {"enviado": True, "destinatarios": todos, "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("Fallo enviando email del pedido %s", pedido.get("numero"))
        return {"enviado": False, "destinatarios": todos, "error": str(e)}
