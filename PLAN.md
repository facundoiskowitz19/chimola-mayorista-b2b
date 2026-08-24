# PLAN.md — checklist mayorista-b2b

Estado al **2026-08-23**: MVP + **Fase 2 (admin total + compra rápida)**
completos y validados end-to-end en DEV
(https://mayorista-b2b-dev-vhnuyigzqa-uc.a.run.app). Specs funcionales en
`SPECS.md`. Falta definir cosas con Chimola (§8) y promover a PROD (§7).

## Fase 5 — Notificaciones y cancelación (2026-08-24) ✅

- [x] Emails por cambio de estado (procesado/cancelado) al cliente + Lautin,
      con toggle `notificar_estados` en Admin → Config y auditoría en
      `pedidos/{n}.email_{estado}`.
- [x] Cancelación por el cliente mientras el pedido esté `confirmado` (botón
      con confirmación en Mis pedidos; guardas en `pedidos.puede_cancelar`).
- [x] Fix pestaña Clientes (NUMERIC vs ARRAY<INT64>) y columna "Editar →" con
      deep-link `?prod=COD` en el catálogo del admin. Tests 22/22.

## Fase 4 — Rediseño Broadsheet (handoff Claude Design, 2026-08-23) ✅

- [x] Identidad nueva (decisión del usuario): Source Serif 4 + papel + cian
      interactivo + magenta solo errores; sin emojis. Ver SPECS §10.
- [x] Cliente: nav horizontal sin sidebar, facetas + chips con ×, carga de
      cantidades en línea desde la card, matriz color×talle, carrito con
      filas propias (miniatura, × por fila, avisos de ajuste inline), pegado
      con reconciliación (contadores + tabla por línea), pedidos maestro-detalle.
- [x] Admin: click en el producto abre el editor como PANTALLA (no modal),
      selección múltiple con barra contextual, override vs Aleph explícito
      (vacío = usa Aleph), publicación con captions, salud accionable, aviso
      de stock manual por variante con números reales.
- [x] `resolver_pegado` devuelve incidencias estructuradas; `precios` y
      `variantes` se reemplazan completos en Firestore. Tests 20/20.

## Fase 3 — Admin UX estilo wp-admin/Woo (2026-08-23) ✅

- [x] Nav del admin con contadores (`st.segmented_control`): Inicio · Catálogo ·
      Clientes · Pedidos (n sin procesar) · Config. Badge también en el sidebar.
- [x] **Inicio**: KPIs (sin procesar, pedidos/$/unidades/clientes del mes),
      salud del catálogo, top productos del mes.
- [x] **Catálogo**: pills con contadores (Todos/Publicados/Ocultos/Destacados/
      Sin foto/Con override), tabla con selección multi-fila + acciones en lote
      (ocultar/auto/destacar, confirmación modal si >10), paginación ‹ › y
      **editor de producto en modal**: nombre/descr/precios L1-4/publicación/
      destacado/**múltiplo U.B.** + tabla de **variantes editable** (stock
      manual, oculta, precio manual por variante).
- [x] Overrides por variante en `overrides.py` + `stock.py` (la validación al
      confirmar respeta el stock manual). U.B. forzado en producto y compra rápida.
- [x] **Pedidos**: pills por estado, click en fila abre detalle con badge de
      color, timeline del historial e items con miniaturas.
- [x] **Clientes**: tabla con valores efectivos (desc/lista + origen) vía
      `catalog.get_clientes()` batch; edición y alta en modales.
- [x] **IVA informativo** (hallazgo del relevamiento Woo: listas sin IVA; la NP
      suma 21% — verificado con Kinderland): config `iva_pct` (default 21),
      líneas IVA/Total c/IVA en carrito, Excel y email.
- [x] Tests 20/20. Relevamiento del Woo documentado (curva completa/u.b.,
      descuento por cliente, sin estados custom, backorders).

## Fase 2 (2026-08-23) ✅

- [x] `overrides.py` + Firestore: `catalogo_overrides` (publicar/ocultar/
      destacar + nombre/descripcion/precios por lista), `clientes_overrides`
      (descuento %/lista con fallback a Aleph), `config/global` (email
      pedidos, banner, descvta, mínimo). Cache 60 s + auditoría updated_by.
- [x] Admin UI (`admin_ui.py`, tabs): Catálogo (tabla editable con miniaturas
      + lote + edición fina), Clientes (overrides, alta, reset password,
      activar/desactivar), Pedidos (filtros, estados con historial, reenviar
      email), Config.
- [x] Compra rápida (`compra_rapida.py` + página): tabla editable con
      miniaturas y cantidades, pegar códigos SKU/EAN, repetir pedido.
- [x] Miniaturas en el carrito. Banner administrable. Mínimo de pedido.
- [x] Tests 15/15 (`tests/test_fase2.py`) + e2e local (cliente y admin).

## 0. Setup infra DEV ✅

- [x] SA `sa-mayorista-dev@chimola-deteccion.iam.gserviceaccount.com`.
- [x] `roles/bigquery.jobUser` + `roles/bigquery.readSessionUser` (BQ Storage
      API para `to_dataframe`) a nivel proyecto + READER (access entry) en
      `franquicias_marts`, `franquicias_dwh`, `franquicias_raw`, `central_raw`
      (`bq add-iam-policy-binding` requiere allowlist → se hace por API).
- [x] `roles/storage.objectViewer` en `gs://ecommerce-b2b-imagenes` (PROD).
- [x] Bucket `gs://chimola-mayorista-pedidos-dev` + `objectAdmin`.
- [x] Firestore Native `(default)` en us-central1 + índice compuesto
      `pedidos(cliente_cod ASC, confirmed_at DESC)`.
- [x] `roles/iam.serviceAccountTokenCreator` sobre sí misma (signed URLs).
- [x] Secrets: `mayorista-jwt-key` (DEV), accessor a `email-smtp-credentials`
      (PROD), `mayorista-seed-passwords` (DEV).
- [ ] Dominio custom (opcional, post-MVP).

Todo reproducible con `./deploy/setup_infra.sh dev`.

## 1. Modelo Firestore ✅

- `usuarios/{email}`: `{email, password_hash, cliente_cod, nombre_display, rol, activo, created_at, last_login_at}`.
- `pedidos/{numero:06d}`: cabecera + `items[]` + totales + `estado` +
  `xlsx_gcs_path` + `email{enviado,destinatarios,error}` + `observaciones`.
- `carritos/{email}`: `{items[], updated_at}`.
- `login_attempts/{email}`: `{ventana_desde, intentos}`.
- `contadores/pedidos`: `{valor}` (numerador transaccional).

## 2. Backend Python ✅

- [x] `auth.py`: bcrypt, JWT 24h, rate limit 5/15min, login con error genérico.
- [x] `catalog.py`: query base con stock neto (OC) + precios `precio1..10`,
      cache 30 min, filtros facetados, búsqueda, agregación por producto.
- [x] `stock.py`: `validar_stock()` en vivo al confirmar.
- [x] `fotos.py`: índice del bucket (1 listado/h), parsing por color, signed
      URLs V4 (signBlob) con fallback a URL pública, placeholder.
- [x] `pedidos.py`: carrito persistido, numerador, Excel (Resumen + Detalle
      con fórmulas), backup GCS, Firestore, historial.
- [x] `email_notif.py`: 1 mail al cliente + 1 a Chimola, Excel adjunto,
      `EMAIL_OVERRIDE_TO` para DEV. Nunca rompe el pedido si falla.

## 3. UI Streamlit ✅

- [x] Login, Catálogo (grid 4 col, paginado 24), Producto (galería por color,
      cantidades por variante), Carrito (`data_editor`, totales, confirmar en
      `st.form`), Mis pedidos (tabla + detalle + descarga), sidebar con
      usuario/cliente/nav/logout. Admin: "Refrescar catálogo".
- [x] Impronta Lautin (Lato, paleta del WP, top bar, header con logo + tabs
      Chimola/Lima, hero del slider, login con banner, footer) — assets en `static/`.
- [ ] Favicon/ícono propio (hoy emoji 🛍️) y logos de marca Chimola/Lima en SVG.

## 4. Docker + deploy ✅

- [x] `requirements.txt`, `Dockerfile`, `.streamlit/config.toml`, `.env.example`.
- [x] `./deploy/deploy.sh dev` → `mayorista-b2b-dev` (session-affinity, 1Gi, max 3).

## 5. Semillas ✅

- [x] `franquicia_jujuy_test@` (2722), `franquicia_mendoza_test@` (2723),
      `admin@lautin.com.ar` (admin). Passwords en `mayorista-seed-passwords`.

## 6. Verificación end-to-end ✅ (local contra DEV + Cloud Run DEV)

- [x] Login OK → razón social, lista 1, desc 20%.
- [x] Catálogo 1.285 productos con fotos (signed URLs en Cloud Run).
- [x] Filtros y búsqueda "M211".
- [x] Agregar M211 U AQUA ×3 → carrito → total con 20%.
- [x] Confirmar → Excel + email + backup GCS + Firestore + historial.
- [x] Tests unitarios `pytest tests` (8 passed).

## 7. Promoción a PROD (pendiente)

- [ ] Validar DEV con el equipo de Chimola (1 semana, usuarios de prueba).
- [ ] `./deploy/setup_infra.sh prod` (SA `sa-mayorista@chimola-490015`, bucket
      `chimola-mayorista-pedidos`, Firestore Native en 490015, índice, secret JWT).
- [ ] `PEDIDOS_EMAIL_TO=<definir> ./deploy/deploy.sh prod`.
- [ ] Sembrar usuarios reales (1 por franquicia → `dim_pv.cliente_cod_titular`).
- [ ] Piloto con 1 franquicia (ej. Jujuy) antes de abrir al resto.
- [ ] Deprecar el pipeline Woo cuando el sitio esté adoptado.

## 8. Definiciones con Chimola (pendiente)

- [ ] Email destino de pedidos (`pedidos@lautin.com.ar`?). Hoy DEV → fiskowitz.
- [ ] Formato exacto del Excel (hoy: Resumen + Detalle con SKU/EAN/cantidad/precio lista/subtotal).
- [ ] ¿Aplicar `articulosol.descvta` (desc. por artículo, ej. 10% M211) además
      del descuento cabecera? Hoy NO se aplica (el Woo sí lo usa como sale_price).
- [ ] Confirmar listas/descuentos por cliente en `dim_cliente` (franquicias =
      lista 1; Jujuy 20%, Mendoza 30%, Villa María 28%, resto 20%).
- [ ] ¿Mínimo de compra / múltiplos por bulto (`articulosol.bulto`)?
- [ ] Proceso manual Excel → NP en Aleph (documentar paso a paso).
