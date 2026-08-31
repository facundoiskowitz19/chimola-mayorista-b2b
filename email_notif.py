"""Emails del mayorista (SMTP Gmail Workspace, secret del pipeline hermano).

Secret `email-smtp-credentials` (Secret Manager, chimola-490015): JSON {user, password}.

Fase 6 (E3): los textos salen de TEMPLATES editables desde el admin
(doc Firestore `config/emails`, ver overrides.get_emails_config). Cada evento
(`confirmacion` | `procesado` | `cancelado`) tiene formato texto|html, asunto
y cuerpo con variables `{numero} {cliente} {cliente_cod} {usuario} {fecha}
{unidades} {subtotal} {descuento_pct} {descuento_monto} {total} {iva_pct}
{iva_monto} {total_con_iva} {lista_precios} {observaciones} {detalle} {quien}
{estado}`. Una variable desconocida queda literal (no rompe el envío).
"""
from __future__ import annotations

import json
import logging
import re
import smtplib
from email.message import EmailMessage
from functools import lru_cache

import config

log = logging.getLogger(__name__)

XLSX_MIME = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")

EVENTOS = ("confirmacion", "procesado", "cancelado", "modificado")

DEFAULT_TEMPLATES = {
    "confirmacion": {
        "formato": "texto",
        "asunto": "[Mayorista Lautin] Pedido N° {numero} — {cliente}",
        "cuerpo": ("Pedido N° {numero} — {cliente} (cliente {cliente_cod})\n"
                   "Fecha: {fecha}\nUsuario: {usuario}\n\n"
                   "Unidades: {unidades}\n"
                   "Subtotal (lista {lista_precios}, sin IVA): {subtotal}\n"
                   "Descuento cabecera {descuento_pct}%: -{descuento_monto}\n"
                   "TOTAL: {total}\n{lineas_iva}"
                   "Observaciones: {observaciones}\n\n"
                   "Detalle:\n{detalle}\n\n"
                   "El Excel del pedido va adjunto.\n\n— Mayorista Lautin"),
    },
    "procesado": {
        "formato": "texto",
        "asunto": "[Mayorista Lautin] Tu pedido N° {numero} fue procesado",
        "cuerpo": ("Pedido N° {numero} — {cliente} (cliente {cliente_cod})\n"
                   "Fecha del pedido: {fecha} · {unidades} u. · total {total}\n\n"
                   "El equipo de Lautin procesó tu pedido y ya está en preparación.\n"
                   "El detalle está en el Excel que recibiste al confirmarlo.\n\n— Mayorista Lautin"),
    },
    "modificado": {
        "formato": "texto",
        "asunto": "[Mayorista Lautin] Tu pedido N° {numero} fue modificado",
        "cuerpo": ("Pedido N° {numero} — {cliente} (cliente {cliente_cod})\n"
                   "Fecha del pedido: {fecha}\n\n"
                   "Lautin ajustó tu pedido. Qué cambió:\n{cambios}\n\n"
                   "Este es el detalle VIGENTE:\n\n{detalle}\n\n"
                   "Unidades: {unidades}\n"
                   "Subtotal (lista {lista_precios}, sin IVA): {subtotal}\n"
                   "Descuento cabecera {descuento_pct}%: -{descuento_monto}\n"
                   "TOTAL: {total}\n{lineas_iva}"
                   "\nSi algo no cierra, respondé este mail o contactá a Lautin.\n\n— Mayorista Lautin"),
    },
    "cancelado": {
        "formato": "texto",
        "asunto": "[Mayorista Lautin] Pedido N° {numero} cancelado",
        "cuerpo": ("Pedido N° {numero} — {cliente} (cliente {cliente_cod})\n"
                   "Fecha del pedido: {fecha} · {unidades} u. · total {total}\n\n"
                   "El pedido fue CANCELADO por {quien}.\n"
                   "Si fue un error, respondé este mail o contactá a Lautin.\n\n— Mayorista Lautin"),
    },
}


class _SafeDict(dict):
    def __missing__(self, key):  # variable desconocida → queda literal
        return "{" + key + "}"


def _fmt(n) -> str:
    return f"$ {float(n or 0):,.0f}".replace(",", ".")


def variables_pedido(pedido: dict, por: str = "") -> dict:
    """Variables disponibles en los templates, ya formateadas."""
    iva = float(pedido.get("iva_pct") or 0)
    lineas_iva = ""
    if iva > 0:
        lineas_iva = (f"IVA {iva:g}%: {_fmt(pedido.get('iva_monto', 0))}\n"
                      f"TOTAL c/IVA: {_fmt(pedido.get('total_con_iva', 0))}\n")
    detalle = "\n".join(
        f"  - {it['producto_cod']} {it['producto_nombre']} | {it['color']} | T {it['talle']} "
        f"| {it['cantidad']} u × {_fmt(it['precio_unit'])} = {_fmt(it.get('subtotal', 0))}"
        + (" [VARIANTE MANUAL — no existe en Aleph]" if it.get("manual") else "")
        for it in pedido.get("items", []))
    if por and por == pedido.get("usuario_email"):
        quien = f"el cliente ({por})"
    elif por:
        quien = f"el equipo de Lautin ({por})"
    else:
        quien = "Lautin"
    return {
        "numero": pedido.get("numero"), "cliente": pedido.get("cliente_nombre", ""),
        "cliente_cod": pedido.get("cliente_cod"), "usuario": pedido.get("usuario_email", ""),
        "fecha": pedido.get("fecha_str", ""), "unidades": pedido.get("unidades", 0),
        "lista_precios": pedido.get("lista_precios", ""),
        "contacto": (" ".join(filter(None, [pedido.get("contacto_nombre"),
                     f"<{pedido.get('contacto_email')}>" if pedido.get("contacto_email") else "",
                     pedido.get("contacto_telefono") or ""]))
                     or pedido.get("usuario_email", "")),
        "subtotal": _fmt(pedido.get("subtotal", 0)), "descuento_pct": f"{float(pedido.get('descuento_pct') or 0):g}",
        "descuento_monto": _fmt(pedido.get("descuento_monto", 0)), "total": _fmt(pedido.get("total", 0)),
        "iva_pct": f"{iva:g}", "iva_monto": _fmt(pedido.get("iva_monto", 0)),
        "total_con_iva": _fmt(pedido.get("total_con_iva", 0)), "lineas_iva": lineas_iva,
        "observaciones": pedido.get("observaciones") or "—", "detalle": detalle,
        "cambios": pedido.get("cambios_texto") or "—",
        "estado": pedido.get("estado", ""), "quien": quien,
    }


def template_de(evento: str) -> dict:
    """Template efectivo del evento: doc config/emails pisando los defaults."""
    import overrides

    base = dict(DEFAULT_TEMPLATES[evento])
    try:
        base.update({k: v for k, v in (overrides.get_emails_config().get(evento) or {}).items() if v})
    except Exception:  # noqa: BLE001 — sin Firestore (tests) → defaults
        pass
    return base


def render_email(evento: str, pedido: dict, por: str = "") -> dict:
    """→ {formato, asunto, cuerpo, texto_plano}. Si formato=html, texto_plano
    es el default en texto (fallback multipart); si texto, cuerpo==texto_plano."""
    tpl = template_de(evento)
    vs = _SafeDict(variables_pedido(pedido, por))
    asunto = tpl["asunto"].format_map(vs)
    cuerpo = tpl["cuerpo"].format_map(vs)
    if tpl.get("formato") == "html":
        plano = DEFAULT_TEMPLATES[evento]["cuerpo"].format_map(vs)
        return {"formato": "html", "asunto": asunto, "cuerpo": cuerpo, "texto_plano": plano}
    return {"formato": "texto", "asunto": asunto, "cuerpo": cuerpo, "texto_plano": cuerpo}


@lru_cache(maxsize=1)
def _smtp_creds() -> tuple[str, str]:
    payload = json.loads(config.get_secret(config.SMTP_SECRET_NAME, config.SMTP_SECRET_PROJECT))
    return payload["user"], payload["password"]


def _armar_mensaje(user: str, dest: list[str], r: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(dest)
    msg["Subject"] = r["asunto"]
    msg.set_content(r["texto_plano"])
    if r["formato"] == "html":
        msg.add_alternative(r["cuerpo"], subtype="html")
    return msg


def _destinatarios(pedido: dict) -> tuple[list[str], list[str]]:
    """(cliente, chimola). Destino Chimola administrable (config/global,
    fallback env). En DEV, `EMAIL_OVERRIDE_TO` redirige todo."""
    import overrides

    cliente = [pedido["usuario_email"]]
    chimola = overrides.pedidos_email_to()
    if config.EMAIL_OVERRIDE_TO:
        return [config.EMAIL_OVERRIDE_TO], []
    return cliente, chimola


def _enviar(pedido: dict, r: dict, adjunto: tuple[bytes, str] | None = None,
            solo_a: list[str] | None = None) -> dict:
    to, chimola = (_destinatarios(pedido) if solo_a is None else (solo_a, []))
    todos = to + chimola
    if not config.EMAIL_ENABLED:
        log.info("EMAIL_ENABLED=false; no envío a %s", todos)
        return {"enviado": False, "destinatarios": todos, "error": "deshabilitado"}
    try:
        user, password = _smtp_creds()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            for dest in (to, chimola):
                if not dest:
                    continue
                msg = _armar_mensaje(user, dest, r)
                if adjunto:
                    msg.add_attachment(adjunto[0], maintype=XLSX_MIME[0], subtype=XLSX_MIME[1],
                                       filename=adjunto[1])
                smtp.send_message(msg)
        log.info("Email '%s' enviado a %s", r["asunto"], todos)
        return {"enviado": True, "destinatarios": todos, "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("Fallo enviando email '%s'", r.get("asunto"))
        return {"enviado": False, "destinatarios": todos, "error": str(e)}


def enviar_confirmacion(pedido: dict, xlsx_bytes: bytes, filename: str) -> dict:
    """Pedido realizado: 1 mail al cliente + 1 a Chimola con el Excel adjunto."""
    return _enviar(pedido, render_email("confirmacion", pedido), adjunto=(xlsx_bytes, filename))


def enviar_cambio_estado(pedido: dict, nuevo: str, por: str) -> dict:
    """Cambio de estado (procesado/cancelado). Best-effort, nunca levanta."""
    evento = nuevo if nuevo in EVENTOS else "procesado"
    return _enviar(pedido, render_email(evento, pedido, por))


def enviar_prueba(evento: str, pedido: dict, destinatario: str) -> dict:
    """'Enviarme una prueba' del configurador (respeta EMAIL_OVERRIDE_TO)."""
    r = render_email(evento, pedido, por=destinatario)
    r["asunto"] = "[PRUEBA] " + r["asunto"]
    solo_a = [config.EMAIL_OVERRIDE_TO] if config.EMAIL_OVERRIDE_TO else [destinatario]
    return _enviar(pedido, r, solo_a=solo_a)


# --- helpers legacy (tests y compat) -----------------------------------------
def cuerpo_estado(pedido: dict, nuevo: str, por: str) -> str:
    """Texto plano del evento de estado con los defaults (usado en tests)."""
    evento = nuevo if nuevo in EVENTOS else "procesado"
    vs = _SafeDict(variables_pedido(pedido, por))
    return DEFAULT_TEMPLATES[evento]["cuerpo"].format_map(vs)


def texto_a_html(texto: str) -> str:
    """Conversión mínima texto→HTML (arranque para editar en modo html)."""
    esc = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    esc = re.sub(r"\n", "<br>\n", esc)
    return ("<div style=\"font-family: Georgia, 'Source Serif 4', serif; color:#201e1d; "
            "max-width:640px\">" + esc + "</div>")
