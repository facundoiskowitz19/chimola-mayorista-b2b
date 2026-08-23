# mayorista-b2b — MVP

Sitio mayorista propio de Chimola/Lautin. Catálogo con fotos + carrito +
confirmación con **Excel del pedido** (email + backup GCS). Reemplaza al
WooCommerce actual.

**Stack**: Streamlit 1.41 + BigQuery (readonly) + Firestore + GCS + SMTP,
desplegado en Cloud Run.

| Ambiente | URL | Proyecto | Estado |
|---|---|---|---|
| DEV | https://mayorista-b2b-dev-vhnuyigzqa-uc.a.run.app | `chimola-deteccion` | ✅ vivo (2026-08-21) |
| PROD | — | `chimola-490015` | pendiente (ver PLAN.md §7) |

---

## Arquitectura

```
Cliente B2B (browser)
    ↓  login email+password → cookie JWT 24h
Streamlit (Cloud Run, session-affinity)
    ├─ BigQuery  franquicias_marts.v_stock_omnicanal + raw.stock (OC) + raw.articulosol (precios) + dwh.dim_cliente
    ├─ GCS       ecommerce-b2b-imagenes (fotos, signed URLs 1h)  /  chimola-mayorista-pedidos[-dev] (backup xlsx)
    ├─ Firestore usuarios · pedidos · carritos · login_attempts · contadores
    └─ SMTP      Gmail Workspace (secret email-smtp-credentials de chimola-490015)
```

Detalle de módulos y gotchas: **`CLAUDE.md`**.

---

## Flujo

1. **Login**: `usuarios/{email}` en Firestore (bcrypt). Al entrar se lee
   `dim_cliente` (razón social, lista de precios, descuento cabecera, CUIT).
2. **Catálogo**: solo variantes con stock **neto** en Ezeiza (restando OC).
   Filtros marca / temporada / rubro / subrubro (facetados), búsqueda por
   código / nombre / EAN / color, "solo con foto", 24 por página.
3. **Producto**: galería por color, precio de lista del cliente + precio con
   descuento, cantidades por variante (tope = stock).
4. **Carrito**: persistido por usuario; editable (`st.data_editor`);
   subtotal, descuento cabecera, total.
5. **Confirmar**: re-valida stock en BQ → numera (`contadores/pedidos`) →
   Excel (Resumen + Detalle) → `gs://<bucket>/YYYY-MM/pedido_<cliente>_<n>_<ts>.xlsx`
   → `pedidos/{n}` → email al cliente + a Chimola con el Excel adjunto.
6. **Mis pedidos**: historial + descarga del Excel (admin ve todos).

---

## Estructura

```
app.py               UI + router (login, catálogo, producto, carrito, mis pedidos)
config.py            env vars + Secret Manager
bq_client.py         cliente BQ con maximum_bytes_billed=1GB
catalog.py           query base + cache 30 min + precios por lista + filtros
stock.py             validación de stock en vivo
fotos.py             índice del bucket + parsing de nombres + signed URLs
db.py                Firestore (colecciones, numerador transaccional)
auth.py              bcrypt, JWT, rate limit, usuarios
pedidos.py           carrito, confirmar, Excel, backup, historial
email_notif.py       SMTP
static/              branding Lautin: logo + 2 banners del slider de lautin.com.ar (optimizados a 1600px)
scripts/seed_usuarios.py   usuarios de prueba → passwords en Secret Manager
deploy/setup_infra.sh      infra idempotente por env
deploy/deploy.sh           gcloud run deploy --source
tests/test_pure.py         lógica pura (sin GCP)
```

---

## Setup local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login      # cuenta con acceso a chimola-deteccion
cp .env.example .env                       # defaults DEV; opcional JWT_KEY local
streamlit run app.py
python -m pytest tests -q
```

Local con usuario ADC: BQ/Firestore/GCS funcionan; las fotos salen con URL
pública (no se pueden firmar sin SA) — en Cloud Run se firman.

---

## Deploy

**DEV primero, siempre.**

```bash
./deploy/setup_infra.sh dev    # una vez: SA, grants, bucket, Firestore+índice, secrets
./venv/bin/python scripts/seed_usuarios.py    # usuarios de prueba (passwords → Secret Manager)
./deploy/deploy.sh dev         # Cloud Run mayorista-b2b-dev
```

Para PROD: `./deploy/setup_infra.sh prod` y `PEDIDOS_EMAIL_TO=pedidos@lautin.com.ar ./deploy/deploy.sh prod`
(recién cuando DEV esté validado con una franquicia piloto — ver PLAN.md §7).

Usuarios de prueba DEV (passwords en `mayorista-seed-passwords` de `chimola-deteccion`):

```bash
gcloud secrets versions access latest --secret=mayorista-seed-passwords --project=chimola-deteccion
```

| Email | cliente_cod | Rol |
|---|---|---|
| franquicia_jujuy_test@lautin.com.ar | 2722 (lista 1, 20%) | cliente |
| franquicia_mendoza_test@lautin.com.ar | 2723 (lista 1, 30%) | cliente |
| admin@lautin.com.ar | — | admin (ve todos los pedidos) |

En DEV **todos los emails** van a `EMAIL_OVERRIDE_TO` (fiskowitz@lautin.com.ar).

---

## Verificación MVP (hecha en DEV el 2026-08-21)

1. ✅ Login con usuario de prueba (cliente 2722) → sidebar muestra razón social, lista 1, 20%.
2. ✅ Catálogo: 1.285 productos / 4.974 variantes con stock neto; 1.214 con foto.
3. ✅ Filtro por temporada (AW26 tiene 124 Chimola + 89 Lima con stock).
4. ✅ Buscar "M211" → Mochila Soft Rainbow (DDN25) con 16 fotos agrupadas por color.
5. ✅ Agregar unidades de M211 talle U (colores AQUA / LIGHT PINK / LIGHT PURPLE / RAINBOW — **no existe BEIGE**).
6. ✅ Precio unitario = `precio1` ($32.900; `precio_lista4` = $65.800 es PVP).
7. ✅ Descuento cabecera del cliente (20% Jujuy, no 30%) aplicado al total.
8. ✅ Confirmar → Excel generado, email enviado, backup en `gs://chimola-mayorista-pedidos-dev/2026-08/`.
9. ✅ "Mis pedidos" lista el pedido y permite re-descargar el Excel.

---

## Costos estimados

| Componente | Estimado |
|---|---|
| Cloud Run (min=0, max=3/5, 1 GiB) | $10-30/mes |
| BigQuery (1 query catálogo / 30 min + validaciones) | centavos/mes |
| GCS (listado fotos 1/h + backups) | $1-5/mes |
| Firestore | $0-5/mes |
| **Total** | **~$15-40/mes** |

---

## Fases siguientes

- **Fase 2**: integración con Aleph (pedido → NP automática).
- **Fase 3**: gestión de cuentas desde el sitio (alta, cambio de password).
- **Fase 4**: estados de pedido (procesado / enviado) + notificaciones.
- **Fase 5**: frontend Next.js si el uso lo amerita.
- **Fase 6**: pagos online.
