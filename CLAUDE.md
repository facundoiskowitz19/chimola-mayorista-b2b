# mayorista-b2b

Sitio mayorista propio de Chimola/Lautin para que **franquicias + clientes B2B**
armen pedidos vieron catálogo con fotos y stock en vivo. **Reemplaza al
WooCommerce actual** (`~/Desktop/Projects/Chimola/B2B - woocommerce/`), que
seguía vivo pero es pesado de mantener.

**Alcance MVP**: catálogo con fotos → carrito → confirmación → **export Excel**
del pedido. Sin pagos online, sin integración a Aleph automática todavía. El
equipo de Chimola procesa el Excel manualmente (por ahora).

---

## Contexto del ecosistema

Ya existen 3 proyectos hermanos que este consume:

| Proyecto | Rol | Ubicación |
|---|---|---|
| `sql-to-bq-franquicias` | Pipeline ERP Aleph → BigQuery. Fuente de todo. | `~/Desktop/Projects/Chimola/sql-to-bq-franquicias/` |
| `B2B - woocommerce/generacion_de_catalogo_woocommerce` | Sincroniza catálogo + stock + imágenes a WordPress (deprecable cuando este esté vivo). Sube fotos al bucket. | `~/Desktop/Projects/Chimola/B2B - woocommerce/` |
| `jarvis` | Asistente conversacional sobre la misma data (starter kit, sin desarrollar). | `~/Desktop/Projects/Chimola/jarvis/` |

**Fuentes que consumimos**:
- **BigQuery** (`chimola-490015.franquicias_marts` + `franquicias_dwh`):
  productos, stock, dim_cliente, dim_pv, precios.
- **GCS bucket `ecommerce-b2b-imagenes/catalogo/fotos_productos/<PROD>/`**:
  fotos ya normalizadas por el pipeline Woo. 1919 productos con fotos hoy.

**Fuentes que producimos**:
- **Excel** con cada pedido (formato definido por Chimola).
- **GCS `gs://<bucket-pedidos>/`** como backup de cada pedido generado.
- **Email** al equipo Chimola + al cliente mayorista.

---

## Alcance MVP (Fase 1)

### Funcionalidad
1. **Login** por email + password (cuentas gestionadas por Chimola).
   Cada cliente B2B tiene un `cliente_cod` de `dim_cliente` asociado.
2. **Catálogo browseable**: filtros por marca, temporada, rubro, subrubro,
   con búsqueda por SKU/nombre. Cards con foto principal + info + precio.
3. **Detalle de producto**: galería de fotos, variantes por color/talle con
   stock por variante (solo depósito Ezeiza para B2B).
4. **Carrito**: agregar/quitar variantes con cantidades. Total en vivo.
5. **Confirmar pedido**: valida stock + genera Excel + guarda backup en GCS
   + envía email al cliente y a Chimola.
6. **Mis pedidos**: historial simple (fecha, total, Excel adjunto para
   re-descargar).

### Fuera del MVP
- Pagos online (Mercado Pago, tarjeta).
- Integración automática con Aleph (crear NP directo desde el pedido).
- Alta/gestión de clientes desde el sitio (Chimola los da de alta a mano).
- Multi-idioma, multi-moneda.
- Notificaciones push, chat.

---

## Arquitectura (propuesta a validar con el próximo agente)

```
Navegador
   ↓  Auth: email + password (o Google OAuth si es email @lautin.com.ar interno)
Frontend (Next.js o Streamlit según decisión)
   ↓
Backend API (Python: FastAPI o mismo Streamlit)
   ↓  ├─ BQ readonly (catálogo, stock, precios, cliente)
   ↓  ├─ GCS signed URLs (fotos, expiración corta)
   ↓  ├─ Firestore o Postgres chico (pedidos, sesiones)
   ↓  └─ SMTP (emails de confirmación)
Cloud Run (chimola-490015)
```

### Decisión pendiente: Streamlit vs Next.js

| | Streamlit | Next.js + shadcn/ui |
|---|---|---|
| Tiempo MVP | 2 semanas | 4-6 semanas |
| Feel | App interna | Sitio comercial |
| Carrito UX | Funciona pero limitado | Fluido, tipo shopping habitual |
| Deploy | Cloud Run simple | Cloud Run OK, un poco más laburo |
| Recomendado si | El uso lo hacen internos, prioridad velocidad | El sitio es para franquicias/clientes con expectativa de "sitio comercial" |

**Recomendación inicial**: Streamlit para el MVP. Si funciona y el equipo lo
adopta, se puede migrar a Next.js después con la misma API/BD.

---

## Reglas de negocio críticas

Las mismas del ecosistema — copiadas de `sql-to-bq-franquicias/CLAUDE.md`:

1. **Precios**: cada cliente tiene `dim_cliente.lista_precios` (mayoría usa
   lista 4). Precios de esa lista se traen de `dim_producto.precio_lista4`
   (para la 4) o campos análogos.
2. **Descuento cabecera**: `dim_cliente.descuento` (%) se aplica al total
   del pedido. Es la negociación por cliente. Refleja el `pordscto` que después
   va a la NP en Aleph.
3. **Stock disponible para B2B**: solo depósito Ezeiza (`stock_ezeiza` en
   `v_stock_omnicanal`). Si un producto solo tiene stock en sucursal, NO se
   ofrece al mayorista. El pipeline Woo actual ya aplica esta regla.
4. **Variantes**: cada SKU es `{producto_cod}_{talle}_{color_cod}`. La misma
   convención que usa el Woo para no romper cross-referencia.
5. **Ezeiza incluye OC**: `stock_ezeiza` de la vista suma OC pendiente de
   recibir. El pipeline Woo hoy la resta para publicar solo físico. **Este
   sitio debe hacer lo mismo** — pedir solo lo que hay físico.
6. **Cliente_cod vs franquicia**: `dim_pv.cliente_cod_titular` mapea PV →
   cliente B2B. Un usuario logueado con el email de la franquicia debe estar
   ligado a ese `cliente_cod`, así los pedidos tienen el titular correcto.

---

## Ambientes: DEV primero, siempre

| | DEV | PROD |
|---|---|---|
| Proyecto GCP | `chimola-deteccion` | `chimola-490015` |
| BQ | mismas vistas que PROD | fuente de verdad |
| Cloud Run service | `mayorista-b2b-dev` | `mayorista-b2b` |
| SA | `sa-mayorista-dev@...` | `sa-mayorista@...` |
| Dominio | dev cloud run URL | (definir cuando se elija) |
| Datos de prueba | Usuarios ficticios + emails a fiskowitz | Cuentas reales |

Regla: todo cambio se prueba en DEV con clientes de prueba antes de
promover a PROD.

---

## Seguridad y auth

- **Auth**: email + password. Password hasheada con `bcrypt` (o `argon2`).
- **Sesión**: cookie firmada (JWT) con TTL 24h.
- **Rate limit** en login (evitar bruteforce).
- **SA readonly en BQ** (`roles/bigquery.dataViewer` + `jobUser`).
- **Signed URLs para fotos**: TTL corto (ej: 1 hora), no exponer el bucket
  público.
- **Secrets** en Secret Manager: SMTP creds, JWT signing key, hash del salt
  master, credentials para envío emails.
- **HTTPS** garantizado por Cloud Run.

---

## Cómo trabajar acá

1. Leer `README.md` (arquitectura + deploy).
2. Leer `data_catalog.yaml` (reusar el de `jarvis/` con foco en catálogo B2B).
3. Leer `PLAN.md` (checklist MVP).
4. Preguntar lo que no esté claro antes de escribir código.
5. Coordinar con el pipeline hermano si se necesita una vista nueva en BQ.

## Referencias

- `sql-to-bq-franquicias/CLAUDE.md` — modelo de datos completo.
- `B2B - woocommerce/generacion_de_catalogo_woocommerce/CLAUDE.md` — cómo se
  arma el catálogo hoy y cómo viven las fotos en el bucket.
- `jarvis/data_catalog.yaml` — diccionario de datos ya curado (reutilizable).
