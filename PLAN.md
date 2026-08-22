# PLAN.md — checklist MVP mayorista-b2b

Orden sugerido de implementación. Todo en DEV primero, después PROD.

## 0. Setup infra (una vez en DEV)

- [ ] Crear SA `sa-mayorista-dev@chimola-deteccion.iam.gserviceaccount.com`.
- [ ] Grants:
    - `roles/bigquery.jobUser` a nivel proyecto.
    - `roles/bigquery.dataViewer` en datasets `franquicias_marts`, `franquicias_dwh`.
    - `roles/storage.objectViewer` en bucket `ecommerce-b2b-imagenes`.
    - `roles/storage.objectAdmin` en bucket nuevo `chimola-mayorista-pedidos-dev`.
    - `roles/datastore.user` (Firestore) — o si prefieren, Postgres en Cloud SQL.
- [ ] Crear bucket `gs://chimola-mayorista-pedidos-dev/` para backup pedidos.
- [ ] Habilitar Firestore Native mode en `chimola-deteccion`.
- [ ] Secret Manager: `mayorista-smtp-creds`, `mayorista-jwt-key`, `mayorista-admin-password`.
- [ ] Definir dominio (opcional): `mayorista-dev.lautin.com.ar` con custom domain.

## 1. Modelo de datos Firestore

Colecciones a crear:

- **`usuarios`**: `{email, password_hash, cliente_cod, nombre_display, rol, activo, created_at}`.
    - `rol`: 'cliente' o 'admin' (Chimola).
    - Índice único en `email`.
- **`pedidos`**: `{id, cliente_cod, usuario_email, items: [{sku, producto_cod, talle, color_cod, cantidad, precio_unit, subtotal}], subtotal, desc_cabecera_pct, total, estado, xlsx_gcs_path, created_at, confirmed_at}`.
    - `estado`: 'carrito', 'confirmado', 'procesado', 'cancelado'.
    - Índice por `cliente_cod` + `created_at DESC`.

## 2. Backend Python

### 2.1 `auth.py`
- [ ] `hash_password(pwd) -> str` (bcrypt).
- [ ] `verify_password(pwd, hash) -> bool`.
- [ ] `create_jwt(user_dict, ttl_hours=24) -> str`.
- [ ] `verify_jwt(token) -> dict|None`.
- [ ] `login(email, password) -> jwt|None` con rate limit básico.

### 2.2 `catalog.py`
- [ ] Query BQ base: 1 fila por variante con producto/color/talle/stock/precio.
    - Fuente: `franquicias_marts.v_stock_omnicanal` filtrado por `stock_ezeiza > 0`.
    - Ver `data_catalog.yaml` para el SQL sugerido.
- [ ] `list_productos(filtros: dict, cliente_cod: int) -> list` con paginación.
- [ ] `get_producto(producto_cod: str, cliente_cod: int) -> dict` con variantes + fotos.
- [ ] Cache de catálogo (TTL 30 min).

### 2.3 `stock.py`
- [ ] `validar_stock(items: list) -> dict` que re-consulta BQ al momento de
      confirmar (evita oversell entre login y confirm).

### 2.4 `fotos.py`
- [ ] `listar_fotos_producto(producto_cod) -> list[signed_url]` desde
      `gs://ecommerce-b2b-imagenes/catalogo/fotos_productos/<PROD>/`.
- [ ] Signed URLs con TTL 1 hora, generar on-demand.
- [ ] Fallback a placeholder si el producto no tiene fotos.

### 2.5 `pedidos.py`
- [ ] `crear_pedido(cliente_cod, items) -> pedido_id` (estado='carrito').
- [ ] `actualizar_carrito(pedido_id, items)`.
- [ ] `confirmar_pedido(pedido_id) -> {pedido, xlsx_bytes, xlsx_path}` con
      validación de stock previa.
- [ ] `listar_pedidos(cliente_cod) -> list`.
- [ ] Excel generator: hoja Resumen (cliente, fecha, total) + hoja Detalle
      (1 fila por variante) con formato tipo el de reintegros.

### 2.6 `email_notif.py`
- [ ] `enviar_confirmacion(pedido, xlsx_bytes)` — 1 email al cliente + 1 a
      `pedidos@lautin.com.ar` (o a definir), con Excel adjunto.
- [ ] Reusar el mismo secret SMTP del pipeline (`email-smtp-credentials`).

## 3. UI Streamlit

- [ ] `app.py` con routing por `st.session_state.page` o `streamlit-option-menu`.
- [ ] Página **Login**: form email + password, mensaje de error genérico.
- [ ] Página **Catálogo**: sidebar con filtros (marca, temporada, rubro,
      subrubro, buscar), grid de cards con foto + nombre + precio + stock.
      Paginación (30 por página).
- [ ] Página **Producto**: galería de fotos (`st.image` con carrusel), variantes
      en tabla (color x talle) con stock, input cantidad, botón agregar.
- [ ] Página **Carrito**: tabla editable con `st.data_editor`, subtotales por
      línea, total con desc cabecera del cliente. Botón confirmar.
- [ ] Página **Mis pedidos**: tabla con fecha, total, botón download Excel.
- [ ] Header con logo + email logueado + botón logout.
- [ ] Footer con contacto.

## 4. Docker + deploy

- [ ] `requirements.txt`:
    ```
    streamlit==1.38.0
    google-cloud-bigquery==3.25.0
    google-cloud-storage==2.18.2
    google-cloud-firestore==2.16.0
    google-cloud-secret-manager==2.20.0
    bcrypt==4.2.0
    pyjwt==2.9.0
    xlsxwriter==3.2.0
    pandas==2.2.3
    ```
- [ ] `Dockerfile` python:3.11-slim + gunicorn/streamlit.
- [ ] `.streamlit/config.toml` con tema + `[server] port = $PORT`.
- [ ] `.env.example` con las vars públicas de referencia.
- [ ] Deploy DEV: `gcloud run deploy mayorista-b2b-dev ...`.

## 5. Datos iniciales (semillas)

- [ ] Crear 3 usuarios de prueba en Firestore (uno por franquicia grande):
    - `franquicia_jujuy_test@lautin.com.ar` → cliente_cod=2722
    - `franquicia_mendoza_test@lautin.com.ar` → cliente_cod=2723
    - `admin@lautin.com.ar` (rol admin, ve todos los pedidos)
- [ ] Passwords iniciales generadas + guardadas en Secret Manager para dar
      al equipo de prueba.

## 6. Verificación end-to-end

- [ ] Login con `franquicia_jujuy_test` → ok.
- [ ] Catálogo carga 500+ productos con fotos.
- [ ] Filtrar por temporada 'AW26' → resultados correctos.
- [ ] Buscar 'M211' → aparece con fotos.
- [ ] Agregar 3 uds M211 talle U color BEIGE → carrito lo refleja.
- [ ] Precio unitario = precio_lista4 del producto.
- [ ] Descuento cabecera 30% (Jujuy) aplicado al total.
- [ ] Confirmar → Excel generado y descargable.
- [ ] Email llega a `franquicia_jujuy_test@lautin.com.ar` y a `pedidos@...`.
- [ ] Backup GCS: `gs://chimola-mayorista-pedidos-dev/2026-08/pedido_2722_<ts>.xlsx`.
- [ ] Pantalla "mis pedidos" lista el pedido recién creado.

## 7. Promoción a PROD

- [ ] Replicar toda la infra en `chimola-490015` con SA `sa-mayorista@...`.
- [ ] Bucket `chimola-mayorista-pedidos` (sin `-dev`).
- [ ] Firestore Native en `chimola-490015`.
- [ ] Deploy `mayorista-b2b`.
- [ ] Compartir URL con 1 franquicia piloto (ej: Jujuy) para 1 semana de
      testing real antes de abrir al resto.

## 8. Comunicación al equipo Chimola

- [ ] Definir email `pedidos@lautin.com.ar` (o el que corresponda) para
      recibir Excels.
- [ ] Definir formato exacto del Excel con Chimola (columnas, totales, etc.).
- [ ] Documentar cómo se procesa un pedido en Aleph (paso a paso).
- [ ] Definir política de precios y descuentos por cliente (validar con
      cliente_cod correctos en dim_cliente).
