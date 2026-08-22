# mayorista-b2b — MVP

Sitio mayorista propio de Chimola/Lautin. Catálogo + carrito + export Excel
del pedido. Reemplaza al WooCommerce actual.

**Stack propuesto (MVP)**: Streamlit + FastAPI (opcional) + BigQuery + GCS +
Cloud Run.

---

## Arquitectura MVP

```
Cliente B2B (browser)
    ↓  Auth (email + password)
Streamlit App (Cloud Run)
    ↓
    ├─ BigQuery (catálogo + stock + precios + dim_cliente)
    ├─ GCS bucket ecommerce-b2b-imagenes (signed URLs para fotos)
    ├─ Firestore (pedidos + sesiones + credenciales usuarios)
    └─ SMTP (email confirmación)
```

---

## Flujo del MVP

1. **Login**: usuario ingresa email + password. Backend valida contra la
   colección `usuarios` (Firestore), que tiene `cliente_cod` asociado.
2. **Home**: catálogo browseable con filtros (marca, temporada, rubro,
   subrubro, texto libre). Cards con foto + nombre + precio + stock indicativo.
3. **Producto**: detalle con galería de fotos, dropdown para elegir color +
   talle. Muestra stock por variante. Botón "agregar al carrito" con cantidad.
4. **Carrito**: lista de items con imagen chica, precio unit, cantidad
   editable, subtotal. Total del pedido con descuento cabecera del cliente
   aplicado. Botón "confirmar pedido".
5. **Confirmación**: valida stock en vivo antes de confirmar. Genera Excel
   con formato acordado. Guarda backup en GCS
   (`gs://chimola-mayorista-pedidos/YYYY-MM/pedido_<cliente>_<timestamp>.xlsx`).
   Envía email a cliente + a `pedidos@lautin.com.ar` (o a definir).
6. **Historial**: pantalla "mis pedidos" — lista fecha + total + botón
   descargar Excel.

---

## Estructura sugerida

```
mayorista-b2b/
├── CLAUDE.md            contexto para el próximo agente
├── README.md            (este archivo)
├── PLAN.md              checklist ordenado del MVP
├── data_catalog.yaml    diccionario de datos con foco en catálogo B2B
├── app.py               Streamlit UI + routing (login, catálogo, prod, carrito, historial)
├── auth.py              login, hash password, sesión
├── catalog.py           queries BQ para catálogo (con filtros + cache)
├── stock.py             validador de stock al confirmar (para evitar oversell)
├── fotos.py             signed URLs de GCS + fallback
├── pedidos.py           lógica de armar pedido, generar Excel, guardar en Firestore
├── email_notif.py       envío SMTP al confirmar
├── requirements.txt
├── Dockerfile
└── .streamlit/
    └── config.toml
```

---

## Setup local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login

# secrets de dev (crear archivo local, gitignoreado)
cp .env.example .env
# editar .env con SMTP_USER, SMTP_PASS, JWT_SECRET, FIRESTORE_PROJECT

streamlit run app.py
```

---

## Deploy

**DEV primero.** Ver `CLAUDE.md` sección "Ambientes: DEV primero, siempre".

```bash
# One-time setup DEV
gcloud iam service-accounts create sa-mayorista-dev --project=chimola-deteccion
# grants BQ (readonly), GCS (read fotos, write pedidos), Firestore, Secret Manager

# Guardar secrets
echo -n "..." | gcloud secrets create mayorista-smtp-creds --data-file=- --project=chimola-deteccion
echo -n "..." | gcloud secrets create mayorista-jwt-key --data-file=- --project=chimola-deteccion

# Deploy DEV
gcloud run deploy mayorista-b2b-dev \
  --project=chimola-deteccion --region=us-central1 \
  --source=. --allow-unauthenticated \
  --service-account=sa-mayorista-dev@chimola-deteccion.iam.gserviceaccount.com \
  --set-secrets=SMTP_CREDS=mayorista-smtp-creds:latest,JWT_KEY=mayorista-jwt-key:latest \
  --memory=1Gi --max-instances=5

# Después de validar DEV → replicar en PROD (chimola-490015).
```

---

## Verificación MVP

1. Login con usuario de prueba `franquicia_jujuy_test@lautin.com.ar` (cliente_cod 2722).
2. Catálogo carga con al menos 500 productos y sus fotos (via signed URL).
3. Filtrar por temporada AW26 → resultados correctos.
4. Buscar "M211" → aparece Mochila Soft Rainbow con fotos.
5. Agregar 3 uds del M211 talle U color BEIGE al carrito.
6. Precio en carrito respeta la lista del cliente (lista 4 default).
7. Descuento cabecera del cliente (30% para Jujuy) se aplica al total.
8. Confirmar pedido → Excel se genera → email llega → backup queda en GCS.
9. Pantalla "mis pedidos" muestra el pedido recién confirmado.

---

## Costos estimados MVP

| Componente | Estimado |
|---|---|
| Cloud Run (min=0, max=5, 1 GiB) | $10-30/mes |
| BigQuery | centavos/mes con cache |
| GCS (signed URLs + backups pedidos) | $1-5/mes |
| Firestore (pedidos + usuarios) | $0-5/mes |
| SMTP (Gmail Workspace, uso existente) | $0 |
| **Total** | **~$15-40/mes** |

---

## Fases siguientes (post-MVP)

- **Fase 2**: integración automática con Aleph — el pedido se convierte en NP
  directamente en el ERP (evita procesamiento manual).
- **Fase 3**: cuentas gestionadas desde el sitio (alta, cambio password, etc.).
- **Fase 4**: notificaciones push, historial rico con seguimiento de estado.
- **Fase 5**: migrar frontend a Next.js si el uso amerita mejor UX.
- **Fase 6**: pagos online.
