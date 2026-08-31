"""Carrito, confirmación de pedido, Excel, backup GCS, historial.

Pedido en Firestore `pedidos/{numero:06d}`:
  {numero, cliente_cod, cliente_nombre, usuario_email, lista_precios, descuento_pct,
   items: [{sku, ean, producto_cod, producto_nombre, color_cod, color, talle, cantidad,
            precio_unit, subtotal}],
   unidades, subtotal, descuento_monto, total, estado, observaciones,
   xlsx_gcs_path, xlsx_filename, email: {...}, created_at, confirmed_at}

`precio_unit` = precio de lista del cliente al momento del pedido (sin desc.
cabecera). El descuento se aplica al total. Se guarda todo para no depender
del catálogo actual.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import zoneinfo
from functools import lru_cache

import pandas as pd
import xlsxwriter
from google.cloud import firestore, storage

import config
import db
import email_notif
import stock as stock_mod
from catalog import aplicar_descuento

log = logging.getLogger(__name__)
TZ = zoneinfo.ZoneInfo(config.TZ)

ESTADOS = ("confirmado", "procesado", "cancelado")


@lru_cache(maxsize=1)
def _storage() -> storage.Client:
    return storage.Client(project=config.GCP_PROJECT)


# ---------------------------------------------------------------------------
# Carrito (persistido por usuario para sobrevivir refresh / cambio de device)
# ---------------------------------------------------------------------------
def cargar_carrito(email: str) -> list[dict]:
    snap = db.carrito_ref(email).get()
    return list((snap.to_dict() or {}).get("items", [])) if snap.exists else []


def guardar_carrito(email: str, items: list[dict]) -> None:
    db.carrito_ref(email).set({"items": items, "updated_at": dt.datetime.now(dt.timezone.utc)})


def vaciar_carrito(email: str) -> None:
    db.carrito_ref(email).delete()


def agregar_al_carrito(items: list[dict], nuevo: dict) -> list[dict]:
    """Suma cantidades si el SKU ya está, sin superar el stock conocido
    (sumar de a tandas no debe dejar el carrito por encima del stock).
    Devuelve la lista nueva (no muta)."""
    out = [dict(i) for i in items]
    for it in out:
        if it["sku"] == nuevo["sku"]:
            it["cantidad"] = int(it["cantidad"]) + int(nuevo["cantidad"])
            it["stock"] = nuevo.get("stock", it.get("stock"))
            if it.get("stock"):
                it["cantidad"] = min(it["cantidad"], int(it["stock"]))
            it["precio_unit"] = nuevo["precio_unit"]
            return out
    out.append(dict(nuevo))
    return out


# ---------------------------------------------------------------------------
# Totales
# ---------------------------------------------------------------------------
def calcular_totales(items: list[dict], descuento_pct: float, iva_pct: float = 0) -> dict:
    """Totales del pedido. Los precios de lista son SIN IVA (como en Aleph);
    `iva_pct` > 0 agrega las líneas informativas IVA y total con IVA
    (así el Excel cierra contra la NP del ERP)."""
    for it in items:
        it["cantidad"] = int(it["cantidad"])
        it["precio_unit"] = round(float(it["precio_unit"]), 2)
        it["subtotal"] = round(it["cantidad"] * it["precio_unit"], 2)
    subtotal = round(sum(i["subtotal"] for i in items), 2)
    total = aplicar_descuento(subtotal, descuento_pct)
    iva_pct = float(iva_pct or 0)
    return {
        "unidades": sum(i["cantidad"] for i in items),
        "subtotal": subtotal,
        "descuento_pct": float(descuento_pct or 0),
        "descuento_monto": round(subtotal - total, 2),
        "total": total,
        "iva_pct": iva_pct,
        "iva_monto": round(total * iva_pct / 100, 2),
        "total_con_iva": round(total * (1 + iva_pct / 100), 2),
    }


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def generar_excel(pedido: dict) -> bytes:
    """Hoja Resumen (cabecera + totales) + hoja Detalle (1 fila por variante)."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})
    hdr = wb.add_format({"bold": True, "bg_color": "#222222", "font_color": "#FFFFFF", "border": 1})
    money = wb.add_format({"num_format": "$ #,##0.00"})
    money_b = wb.add_format({"num_format": "$ #,##0.00", "bold": True})
    pct = wb.add_format({"num_format": "0.00\"%\""})
    intf = wb.add_format({"num_format": "0"})
    title = wb.add_format({"bold": True, "font_size": 14})

    # --- Resumen ---
    ws = wb.add_worksheet("Resumen")
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 48)
    ws.write(0, 0, f"Pedido mayorista N° {pedido['numero']}", title)
    filas = [
        ("Número de pedido", pedido["numero"]),
        ("Fecha", pedido["fecha_str"]),
        ("Código de cliente", pedido["cliente_cod"]),
        ("Cliente", pedido["cliente_nombre"]),
        ("CUIT", pedido.get("cliente_cuit") or ""),
        ("Usuario", pedido["usuario_email"]),
        ("Lista de precios", pedido["lista_precios"]),
        ("Estado", pedido["estado"]),
        ("Observaciones", pedido.get("observaciones") or ""),
    ]
    r = 2
    for k, v in filas:
        ws.write(r, 0, k, bold)
        ws.write(r, 1, v)
        r += 1
    r += 1
    ws.write(r, 0, "Unidades", bold); ws.write(r, 1, pedido["unidades"], intf); r += 1
    ws.write(r, 0, "Subtotal (precio de lista)", bold); ws.write(r, 1, pedido["subtotal"], money); r += 1
    ws.write(r, 0, "Descuento cabecera %", bold); ws.write(r, 1, pedido["descuento_pct"], pct); r += 1
    ws.write(r, 0, "Descuento $", bold); ws.write(r, 1, pedido["descuento_monto"], money); r += 1
    ws.write(r, 0, "TOTAL", bold); ws.write(r, 1, pedido["total"], money_b); r += 1
    iva = float(pedido.get("iva_pct") or 0)
    if iva > 0:
        ws.write(r, 0, f"IVA {iva:g}%", bold); ws.write(r, 1, pedido.get("iva_monto", 0), money); r += 1
        ws.write(r, 0, "TOTAL c/IVA", bold); ws.write(r, 1, pedido.get("total_con_iva", 0), money_b); r += 1

    # --- Detalle --- (la miniatura va PRIMERA, pedido del equipo)
    wd = wb.add_worksheet("Detalle")
    cols = [("Imagen", 9), ("Producto", 12), ("Descripción", 36), ("Color", 16), ("Cód. color", 10),
            ("Talle", 8), ("SKU", 20), ("EAN", 16), ("Cantidad", 10), ("Precio unit. lista", 16),
            ("Subtotal", 16), ("Foto", 10)]
    for c, (name, w) in enumerate(cols):
        wd.set_column(c, c, w)
        wd.write(0, c, name, hdr)
    for i, it in enumerate(pedido["items"], start=1):
        wd.write(i, 1, it["producto_cod"])
        # Las variantes manuales no existen en Aleph: marcarlas para que el
        # equipo no las busque en el ERP al cargar la NP (SPECS §3).
        nombre_linea = it["producto_nombre"] + (" (VARIANTE MANUAL — no existe en Aleph)"
                                                if it.get("manual") else "")
        wd.write(i, 2, nombre_linea)
        wd.write(i, 3, it["color"])
        wd.write(i, 4, str(it["color_cod"]))
        wd.write(i, 5, it["talle"])
        wd.write(i, 6, it["sku"])
        wd.write(i, 7, it.get("ean") or "")
        wd.write(i, 8, it["cantidad"], intf)
        wd.write(i, 9, it["precio_unit"], money)
        wd.write_formula(i, 10, f"=I{i + 1}*J{i + 1}", money, it["subtotal"])
        # Foto de la variante: miniatura en A + link público (best-effort:
        # el Excel del pedido JAMÁS falla por una foto).
        try:
            import fotos as _fotos
            fn = (_fotos.foto_variante_filename(it["producto_cod"], it.get("color"),
                                                solo_color=True)
                  if _fotos.tiene_fotos(it["producto_cod"]) else None)
            if fn:
                wd.write_url(i, 11, _fotos.url_foto_publica(it["producto_cod"], fn),
                             string="ver foto")
                mini = _fotos.miniatura_jpeg(it["producto_cod"], fn)
                if mini:
                    wd.set_row(i, 34)
                    wd.insert_image(i, 0, f"{it['sku']}.jpg",
                                    {"image_data": io.BytesIO(mini), "x_offset": 3,
                                     "y_offset": 3, "object_position": 1})
        except Exception:  # noqa: BLE001
            pass
    n = len(pedido["items"])
    wd.write(n + 2, 7, "Totales", bold)
    wd.write_formula(n + 2, 8, f"=SUM(I2:I{n + 1})", intf, pedido["unidades"])
    wd.write_formula(n + 2, 10, f"=SUM(K2:K{n + 1})", money_b, pedido["subtotal"])
    wd.write(n + 3, 7, f"Desc. {pedido['descuento_pct']:g}%", bold)
    wd.write(n + 3, 10, -pedido["descuento_monto"], money)
    wd.write(n + 4, 7, "TOTAL", bold)
    wd.write(n + 4, 10, pedido["total"], money_b)
    if float(pedido.get("iva_pct") or 0) > 0:
        wd.write(n + 5, 7, f"IVA {pedido['iva_pct']:g}%", bold)
        wd.write(n + 5, 10, pedido.get("iva_monto", 0), money)
        wd.write(n + 6, 7, "TOTAL c/IVA", bold)
        wd.write(n + 6, 10, pedido.get("total_con_iva", 0), money_b)
    wd.freeze_panes(1, 0)
    wd.autofilter(0, 0, max(n, 1), len(cols) - 1)

    wb.close()
    return buf.getvalue()


def nombre_archivo(pedido: dict) -> str:
    ts = pedido["confirmed_at"].astimezone(TZ).strftime("%Y%m%d_%H%M%S")
    return f"pedido_{pedido['cliente_cod']}_{pedido['numero']}_{ts}.xlsx"


def gcs_path(pedido: dict) -> str:
    return f"{pedido['confirmed_at'].astimezone(TZ):%Y-%m}/{pedido['xlsx_filename']}"


def subir_backup(path: str, data: bytes) -> str:
    blob = _storage().bucket(config.BUCKET_PEDIDOS).blob(path)
    blob.upload_from_string(data, content_type=email_notif.XLSX_MIME[0] + "/" + email_notif.XLSX_MIME[1])
    return f"gs://{config.BUCKET_PEDIDOS}/{path}"


def descargar_backup(gcs_uri: str) -> bytes:
    assert gcs_uri.startswith("gs://")
    bucket, _, path = gcs_uri[5:].partition("/")
    return _storage().bucket(bucket).blob(path).download_as_bytes()


# ---------------------------------------------------------------------------
# Confirmar
# ---------------------------------------------------------------------------
class StockInsuficiente(Exception):
    def __init__(self, problemas: list[dict]):
        super().__init__("Stock insuficiente")
        self.problemas = problemas


class MinimoMontoNoAlcanzado(Exception):
    """El subtotal a precio de lista (sin IVA ni descuento) no llega al mínimo."""
    def __init__(self, minimo: float, subtotal: float):
        super().__init__(f"Mínimo de compra ${minimo:,.0f}; subtotal ${subtotal:,.0f}")
        self.minimo, self.subtotal = minimo, subtotal


def resumen_cambios(orig: list[dict], nuevos: list[dict]) -> str:
    """PURA: texto con lo modificado y lo quitado entre dos versiones de items."""
    de = {str(i["sku"]): i for i in nuevos}
    lineas = []
    for it in orig:
        n = de.get(str(it["sku"]))
        etiqueta = (f"{it['producto_cod']} {it.get('producto_nombre', '')} | "
                    f"{it.get('color', '')} | T {it.get('talle', '')}")
        if n is None:
            lineas.append(f"  - QUITADO: {etiqueta} (eran {it['cantidad']} u)")
        elif int(n["cantidad"]) != int(it["cantidad"]):
            lineas.append(f"  - {etiqueta}: {it['cantidad']} u → {n['cantidad']} u")
    return "\n".join(lineas)


def confirmar_pedido(usuario: dict, cliente: dict, items: list[dict], observaciones: str = "") -> tuple[dict, bytes]:
    """Valida stock en vivo → numera → Excel → backup GCS → Firestore → email.
    Devuelve (pedido, xlsx_bytes). Levanta StockInsuficiente si no alcanza."""
    if not items:
        raise ValueError("El carrito está vacío")
    items = [dict(i) for i in items if int(i.get("cantidad", 0)) > 0]
    import overrides
    minimo = overrides.get_config().get("minimo_pedido_unidades")
    unidades = sum(int(i["cantidad"]) for i in items)
    if minimo and unidades < int(minimo):
        raise MinimoNoAlcanzado(int(minimo), unidades)
    # Mínimo en $: sobre el subtotal a PRECIO DE LISTA (sin IVA ni descuento
    # cabecera) — con el descuento aplicado el total puede quedar menor.
    minimo_m = overrides.get_config().get("minimo_pedido_monto")
    if minimo_m:
        sub_lista = round(sum(int(i["cantidad"]) * float(i["precio_unit"]) for i in items), 2)
        if sub_lista < float(minimo_m):
            raise MinimoMontoNoAlcanzado(float(minimo_m), sub_lista)
    problemas = stock_mod.validar_stock(items)
    if problemas:
        raise StockInsuficiente(problemas)

    ahora = dt.datetime.now(dt.timezone.utc)
    numero = db.proximo_numero_pedido()
    tot = calcular_totales(items, cliente.get("descuento", 0), iva_pct=overrides.get_config().get("iva_pct") or 0)
    pedido = {
        "numero": numero,
        "cliente_cod": int(cliente["cliente_cod"]),
        "cliente_nombre": cliente.get("nombre_display") or cliente.get("nombre") or "",
        "cliente_cuit": cliente.get("cuit") or "",
        "contacto_nombre": cliente.get("contacto_nombre") or "",
        "contacto_email": cliente.get("contacto_email") or "",
        "contacto_telefono": cliente.get("contacto_telefono") or "",
        "usuario_email": usuario["email"],
        "lista_precios": int(cliente.get("lista_precios") or 1),
        "items": [{k: it.get(k) for k in ("sku", "ean", "producto_cod", "producto_nombre", "color_cod",
                                          "color", "talle", "cantidad", "precio_unit", "subtotal", "manual")}
                  for it in items],
        **tot,
        "estado": "confirmado",
        "observaciones": (observaciones or "").strip(),
        "created_at": ahora,
        "confirmed_at": ahora,
        "fecha_str": ahora.astimezone(TZ).strftime("%d/%m/%Y %H:%M"),
        "env": config.APP_ENV,
    }
    pedido["xlsx_filename"] = nombre_archivo(pedido)
    xlsx = generar_excel(pedido)
    try:
        pedido["xlsx_gcs_path"] = subir_backup(gcs_path(pedido), xlsx)
    except Exception as e:  # noqa: BLE001 — el pedido vale igual; se loguea
        log.exception("Fallo backup GCS del pedido %s", numero)
        pedido["xlsx_gcs_path"] = None
        pedido["backup_error"] = str(e)

    db.pedidos_col().document(f"{numero:06d}").set(pedido)
    log.info("Pedido %s confirmado: cliente=%s total=%s items=%d", numero, pedido["cliente_cod"],
             pedido["total"], len(items))

    pedido["email"] = email_notif.enviar_confirmacion(pedido, xlsx, pedido["xlsx_filename"])
    db.pedidos_col().document(f"{numero:06d}").update({"email": pedido["email"]})
    vaciar_carrito(usuario["email"])
    return pedido, xlsx


class MinimoNoAlcanzado(Exception):
    def __init__(self, minimo: int, unidades: int):
        super().__init__(f"Mínimo {minimo} unidades (tenés {unidades})")
        self.minimo, self.unidades = minimo, unidades


# ---------------------------------------------------------------------------
# Repetir pedido / estados (SPECS §5 y §7.2)
# ---------------------------------------------------------------------------
def repetir_pedido(pedido: dict, df_publicadas) -> tuple[list[dict], list[str]]:
    """Items para el carrito a partir de un pedido viejo, con precio ACTUAL y
    recortado al stock disponible. → (items, avisos)."""
    por_sku = {r["sku"]: r for _, r in df_publicadas.iterrows()}
    items, avisos = [], []
    for it in pedido["items"]:
        v = por_sku.get(it["sku"])
        if v is None:
            avisos.append(f"{it['sku']} ({it['producto_nombre']} {it['color']} Talle {it['talle']}): "
                          "ya no está disponible")
            continue
        if pd.isna(v["precio"]):
            avisos.append(f"{it['sku']}: sin precio en tu lista, consultá a Chimola")
            continue
        cant = min(int(it["cantidad"]), int(v["stock"]))
        if cant <= 0:
            avisos.append(f"{it['sku']}: sin disponibilidad hoy")
            continue
        if cant < int(it["cantidad"]):
            # Nunca revelar el stock: solo que se superó la cantidad disponible.
            avisos.append(f"{it['sku']}: pediste {it['cantidad']} u. y supera la cantidad "
                          f"disponible — se cargó {cant}")
        items.append({"sku": v["sku"], "ean": v["ean"], "producto_cod": v["producto_cod"],
                      "producto_nombre": v["producto_nombre"], "color_cod": str(v["color_cod"]),
                      "color": v["color"], "talle": v["talle"], "cantidad": cant,
                      "precio_unit": float(v["precio"]), "stock": int(v["stock"])})
    return items, avisos


ESTADOS_SIGUIENTES = {"confirmado": ["procesado", "cancelado"], "procesado": ["cancelado"], "cancelado": []}


def cambiar_estado(numero: int, nuevo: str, por: str, notificar: bool | None = None) -> dict:
    """Cambia el estado (solo transiciones válidas), registra historial y
    notifica por email al cliente + Chimola (config `notificar_estados`)."""
    import overrides

    ref = db.pedidos_col().document(f"{int(numero):06d}")
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"Pedido {numero} no existe")
    actual = snap.get("estado")
    if nuevo not in ESTADOS_SIGUIENTES.get(actual, []):
        raise ValueError(f"Transición inválida: {actual} → {nuevo}")
    evento = {"estado": nuevo, "por": por, "en": dt.datetime.now(dt.timezone.utc)}
    ref.update({"estado": nuevo, "historial": firestore.ArrayUnion([evento])})
    log.info("Pedido %s: %s → %s por %s", numero, actual, nuevo, por)
    pedido = {**snap.to_dict(), "estado": nuevo}
    if notificar is None:
        notificar = bool(overrides.get_config().get("notificar_estados", True))
    if notificar:
        res = email_notif.enviar_cambio_estado(pedido, nuevo, por)
        ref.update({f"email_{nuevo}": res})
        pedido[f"email_{nuevo}"] = res
    return pedido


def items_modificados(items: list[dict], cantidades: dict[str, int]) -> list[dict]:
    """PURA: aplica nuevas cantidades por SKU (<=0 elimina la línea) y recalcula
    subtotales. ValueError si el pedido quedaría vacío."""
    out = []
    for it in items:
        q = int(cantidades.get(str(it["sku"]), it["cantidad"]))
        if q <= 0:
            continue
        out.append({**it, "cantidad": q, "subtotal": round(float(it["precio_unit"]) * q, 2)})
    if not out:
        raise ValueError("El pedido quedaría vacío — cancelalo en su lugar.")
    return out


def modificar_pedido(numero: int, cantidades: dict[str, int], por: str,
                     notificar: bool = True) -> dict:
    """Admin: cambia cantidades / quita líneas de un pedido CONFIRMADO (nunca
    procesado ni cancelado), recalcula totales, regenera el Excel (mismo
    archivo en GCS), registra `modificado` en el historial y avisa al cliente."""
    ref = db.pedidos_col().document(f"{int(numero):06d}")
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"Pedido {numero} no existe")
    p = snap.to_dict()
    if p.get("estado") != "confirmado":
        raise ValueError("Solo se puede modificar un pedido en estado confirmado "
                         "(los procesados ya están en preparación).")
    nuevos = items_modificados(p["items"], cantidades)
    if [(i["sku"], i["cantidad"]) for i in nuevos] == [(i["sku"], i["cantidad"]) for i in p["items"]]:
        raise ValueError("No hay cambios para guardar — las cantidades quedaron igual.")
    p["cambios_texto"] = resumen_cambios(p["items"], nuevos)
    p["items"] = nuevos
    tot = calcular_totales(p["items"], float(p.get("descuento_pct") or 0),
                           float(p.get("iva_pct") or 0))
    p.update({k: tot[k] for k in ("unidades", "subtotal", "descuento_monto", "total",
                                  "iva_monto", "total_con_iva")})
    evento = {"estado": "modificado", "por": por, "en": dt.datetime.now(dt.timezone.utc),
              "detalle": p["cambios_texto"]}
    xlsx = generar_excel(p)
    try:
        p["xlsx_gcs_path"] = subir_backup(gcs_path(p), xlsx)
    except Exception as e:  # noqa: BLE001 — el Excel se puede regenerar on-demand
        log.warning("Backup del pedido modificado %s: %s", numero, e)
    ref.update({"items": p["items"], "unidades": p["unidades"], "subtotal": p["subtotal"],
                "descuento_monto": p["descuento_monto"], "total": p["total"],
                "iva_monto": p["iva_monto"], "total_con_iva": p["total_con_iva"],
                "xlsx_gcs_path": p.get("xlsx_gcs_path"),
                "historial": firestore.ArrayUnion([evento])})
    log.info("Pedido %s modificado por %s", numero, por)
    if notificar:
        res = email_notif.enviar_modificacion(p, xlsx, p.get("xlsx_filename") or f"pedido_{numero}.xlsx", por)
        ref.update({"email_modificado": res})
        p["email_modificado"] = res
    return p


def puede_cancelar(pedido: dict, usuario: dict) -> bool:
    """El cliente puede cancelar SU pedido solo mientras el equipo no lo procesó
    (estado 'confirmado'). Los admin cancelan por su lado sin este límite."""
    if not pedido or not usuario:
        return False
    if pedido.get("estado") != "confirmado":
        return False
    if usuario.get("rol") == "admin":
        return False   # el admin usa la sección Administración
    return int(pedido.get("cliente_cod", -1)) == int(usuario.get("cliente_cod") or -2)


def cancelar_por_cliente(numero: int, usuario: dict) -> dict:
    pedido = get_pedido(numero)
    if not puede_cancelar(pedido, usuario):
        raise ValueError("Este pedido ya fue tomado por Lautin y no se puede cancelar desde acá — contactalos por WhatsApp.")
    return cambiar_estado(numero, "cancelado", usuario["email"])


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------
def listar_pedidos(cliente_cod: int | None = None, limit: int = 200) -> list[dict]:
    """Pedidos del cliente (o todos si cliente_cod=None → admin), más recientes primero."""
    q = db.pedidos_col()
    if cliente_cod is not None:
        q = q.where(filter=firestore.FieldFilter("cliente_cod", "==", int(cliente_cod)))
    q = q.order_by("confirmed_at", direction=firestore.Query.DESCENDING).limit(limit)
    return [d.to_dict() for d in q.stream()]


_conteo_cache: dict = {"data": None, "ts": 0.0}


def contar_por_estado(force: bool = False) -> dict[str, int]:
    """{estado: cantidad} vía agregación count() de Firestore (barato), cache 60 s."""
    import time
    if not force and _conteo_cache["data"] is not None and time.time() - _conteo_cache["ts"] < 60:
        return _conteo_cache["data"]
    out = {}
    for estado in ESTADOS:
        agg = db.pedidos_col().where(filter=firestore.FieldFilter("estado", "==", estado)).count()
        out[estado] = int(agg.get()[0][0].value)
    _conteo_cache.update(data=out, ts=time.time())
    return out


def get_pedido(numero: int) -> dict | None:
    snap = db.pedidos_col().document(f"{int(numero):06d}").get()
    return snap.to_dict() if snap.exists else None
