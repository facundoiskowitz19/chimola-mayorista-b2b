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

## Arquitectura (implementada — MVP vivo en DEV desde 2026-08-21)

Decisión tomada: **Streamlit** (monolito UI + backend en el mismo proceso).
Migrable a Next.js después reusando los módulos Python como API.

```
Navegador ──cookie JWT (24h)──▶ Streamlit (Cloud Run, --session-affinity)
                                  │
   app.py (UI + router)           ├─ catalog.py  → BQ readonly: v_stock_omnicanal + raw.stock (OC) + raw.articulosol (precio1..10)
   auth.py (bcrypt + JWT + rate   ├─ stock.py    → re-consulta BQ al confirmar (anti oversell)
            limit en Firestore)   ├─ fotos.py    → GCS ecommerce-b2b-imagenes (índice 1 list/h + signed URLs V4 via signBlob)
   db.py (Firestore)              ├─ pedidos.py  → Firestore `pedidos` + Excel (xlsxwriter) + backup GCS
   config.py (env + secrets)      └─ email_notif.py → SMTP Gmail (secret `email-smtp-credentials` de chimola-490015)
```

**DEV vivo**: https://mayorista-b2b-dev-vhnuyigzqa-uc.a.run.app
(`chimola-deteccion`, service `mayorista-b2b-dev`, SA `sa-mayorista-dev@`).

### Módulos

| Archivo | Qué hace |
|---|---|
| `app.py` | Páginas login / catálogo / producto / carrito / mis pedidos. Sesión en `st.session_state` + cookie JWT (`st.context.cookies` para leer, JS via `components.html` para escribir). |
| `catalog.py` | Query base (1 fila/variante con stock neto Ezeiza). Cache process-wide TTL 30 min. Precio = `precio{N}` de `raw.articulosol` según `dim_cliente.lista_precios`. Filtros/facetas/búsqueda en pandas. |
| `stock.py` | `validar_stock(items)` → misma CTE sin cache. |
| `fotos.py` | Índice de todo el prefijo del bucket (1 listado, cache 1h), parsing de nombres `"M211 AQUA (1).jpg"` → agrupado por color (misma convención que Woo), signed URLs cacheadas 50 min. Fallback a URL pública si no puede firmar (local). |
| `pedidos.py` | Carrito persistido en `carritos/{email}`; `confirmar_pedido()` = validar stock → numerador (`contadores/pedidos`, transacción) → Excel → GCS → Firestore → email → vaciar carrito. |
| `auth.py` | bcrypt, JWT HS256, rate limit 5 intentos/15 min por email (`login_attempts`). |
| `overrides.py` | **Fase 2.** Capa administrable en Firestore que PISA lo de BQ: `catalogo_overrides` (publicado/destacado/nombre/descripcion/precios por lista), `clientes_overrides` (descuento/lista), `config/global`. Cache 60 s, auditoría `updated_by`. Specs en `SPECS.md`. |
| `admin_ui.py` | **Fase 3.** Administración estilo wp-admin: nav con contadores, Inicio (KPIs `_kpis`), Catálogo (pills + selección multi-fila + lote + modal de producto con variantes editables: stock manual/oculta/precio por variante + U.B.), Clientes (efectivos batch + modales), Pedidos (click en fila, badges, timeline), Config (+IVA %). Solo escribe overrides, nunca BQ. Gotcha: los `st.dialog` se abren SOLO desde botones (no desde on_select, se reabrirían en cada rerun). |
| `compra_rapida.py` | **Fase 2.** Helpers puros de compra rápida: parser de códigos pegados (SKU/EAN,cant) y armado de items. La página vive en `app.py`. |
| `scripts/seed_usuarios.py` | Crea usuarios de prueba; passwords en Secret Manager `mayorista-seed-passwords`. |
| `deploy/setup_infra.sh <env>` | Infra idempotente (SA, grants, bucket, Firestore + índice, secrets). |
| `deploy/deploy.sh <env>` | `gcloud run deploy --source=.` con env vars + secret JWT. |

### Gotchas aprendidos (leer antes de tocar)

- **`v_stock_omnicanal.sku` es el EAN**, no el SKU del sitio. El SKU
  `{producto_cod}_{TALLE}_{color_cod}` se arma en la query (`catalog.py`).
- **Franquicias usan lista 1, no 4** (`dim_cliente.lista_precios=1` para
  2720/2721/2722/2723/2735/2739). `precio_lista4` es el precio de venta al
  público del POS. `dim_producto` solo expone la 4 → por eso la query va a
  `raw.articulosol.precio1..precio10`. Descuentos reales hoy: Jujuy 20%,
  Mendoza 30%, Santa Fe 20%, Corrientes 20%, Nine 20%, Villa María 28%.
- **`dim_cliente.activo` es FALSE para las franquicias** (tienen
  `baja='1900-01-01'`, artefacto de Aleph). No filtrar por `activo`.
- **`articulosol.descvta`** (desc. por artículo, ej. 10% en M211) NO se
  aplica en el sitio — pendiente de definir con Chimola (el Woo lo usa como
  `sale_price`).
- **Stock neto**: 1.572 productos con `stock_ezeiza>0` → 1.285 con stock
  neto tras restar OC (`raw.stock` deposito=1, anclado a `fecha_snapshot`
  de `v_stock_central_actual`). `v_stock_central_actual` NO tiene columna
  `oc_pendiente` (el data_catalog original estaba equivocado).
- **Fotos**: 1.911 carpetas en el bucket; 1.214 de los 1.285 productos con
  stock tienen foto. El bucket hoy es **público** (`allUsers` objectViewer,
  lo usa el Woo) — igual firmamos URLs para no depender de eso.
- **Streamlit interrumpe el script** cuando llega otro evento de widget en
  medio de un run largo. Por eso la confirmación va en `st.form` y el estado
  se guarda en `session_state` ANTES de cerrar el spinner.
- **`st.context.cookies` es del handshake del websocket**: borrar la cookie
  por JS no la saca de ahí hasta el refresh → flag `logged_out` en sesión.
- **`bq add-iam-policy-binding` requiere allowlist** → los grants de dataset
  se hacen por API (`access_entries` READER) en `setup_infra.sh`.
- **Firestore `listar_pedidos`** (where cliente_cod + order by confirmed_at)
  necesita índice compuesto (lo crea `setup_infra.sh`).
- Cloud Run necesita `--session-affinity` (websockets de Streamlit).
- **`st.number_input` explota si `value > max_value`** (StreamlitValueAboveMaxError).
  En el carrito la cantidad guardada puede superar el stock actual (se sumó de
  a tandas o el stock bajó) → SIEMPRE `value=min(cantidad, tope)` + aviso;
  `pedidos.agregar_al_carrito` también capea la suma al stock conocido.
- **Columnas: máximo UN nivel de anidamiento** (StreamlitAPIException). Desde
  el rail de filtros (fase 8) el grid del catálogo vive dentro de la columna
  `main` → dentro del panel inline solo se permite un `st.columns` más; los
  botones del panel van al nivel del container, NUNCA dentro de `pdet`.
- **`get_producto()` debe incluir `producto_cod`/`producto_nombre`/`es_manual`
  en cada variante**: `compra_rapida.item_desde_variante` los exige (KeyError
  al agregar desde la matriz si faltan).
- **Las listas mayoristas de Aleph son SIN IVA**: la NP del ERP suma 21%
  (verificado: NP Kinderland = subtotal − desc + 21%). El sitio lo muestra como
  líneas informativas (config `iva_pct`, default 21) en carrito/Excel/email.
- **Overrides por variante** (`catalogo_overrides.{prod}.variantes.{sku}`):
  stock manual REEMPLAZA al neto BQ (y `stock.py` lo respeta al confirmar —
  el sitio deja de proteger contra oversell en esa variante), `oculta` la saca
  del catálogo, `precios{lista}` pisa al producto. `ub` (producto) = múltiplo
  mínimo de compra, como el ACF `u.b` del Woo.
- Del relevamiento del Woo actual (2026-08-23): los mayoristas compran por
  **curva completa** (variación `curva-completa` con mínimos `u.b`), descuento
  % por cliente como fee negativo, checkout sin pago, sin estados de pedido
  custom, backorders forzados (stock no bloquea), pedidos partidos en paquetes
  (Order Splitter) — esto último queda como candidato de fase futura.

### Identidad visual — Broadsheet (handoff Claude Design, 2026-08-23)

- **Reemplazó a la identidad Lautin/Lato** (decisión del usuario). Fuente única
  del look: `design_handoff_mayorista_ux/` (mocks `Cliente.dc.html` /
  `Admin.dc.html`, README con los 15 cambios, tokens en `_ds/.../styles.css`).
- Tokens: **Source Serif 4**, papel `#f3f2f2`, texto `#201e1d`, cian `#0088b0`
  interactivo (pressed `#006786`, tinte `#e9f8ff`), magenta `#d6006c` SOLO
  errores/cancelado, radio 2px, kickers uppercase 12px ls .14em. Sin emojis.
- Estructura: **sin sidebar** (nav horizontal `st.container(key="lt_nav")` con
  subrayado cian por CSS dinámico), facetas + chips, panel de carga en línea
  en el catálogo, matriz color×talle (`matriz_variantes`), carrito con filas
  `st.columns` + callbacks, admin con editor de producto como pantalla
  (`adm_prod` en session_state, ya NO es `st.dialog`).
- Gotchas nuevos: los chips mutan keys de widgets SOLO vía `on_click` callbacks
  (correr antes del script); `st.dataframe` single-row → abrir el editor
  requiere bump de la key de la tabla para limpiar la selección al volver;
  `st.number_input(value=None, placeholder=...)` es el patrón "vacío = usa
  Aleph" (se eliminó el convenio del 0); en `set_catalogo_override` los maps
  `precios` y `variantes` se REEMPLAZAN completos (update, no merge).
- Assets en `static/` bajados del sitio público (no hizo falta SFTP):
  `logo_lautin.png`, `banner_1.jpg` (Chimola "ØN THE GO_"), `banner_2.jpg`
  (Lima AW26). Si Lautin cambia el slider, reemplazar los jpg (máx 1600px).
- El selector de marca del header (`st.segmented_control`, key `hdr_marca`) se
  sincroniza con el filtro `f_marca` del sidebar vía callback, y elige el banner.
- **CSS scoping en Streamlit 1.41**: TODO bloque vertical lleva
  `stVerticalBlockBorderWrapper`, no solo los `border=True` → para estilar
  las cards se usa `st.container(key="card_<cod>")` (clase `st-key-card_<cod>`)
  y el selector `div[class*="st-key-card_"]`. No usar reglas genéricas sobre
  el wrapper (pintan el sidebar).
- `st.image(path)` para banners (media server eficiente); base64 solo para el
  logo en HTML.

---

## Reglas de negocio críticas

Las mismas del ecosistema — copiadas de `sql-to-bq-franquicias/CLAUDE.md`:

1. **Precios**: cada cliente tiene `dim_cliente.lista_precios` (las
   franquicias usan **lista 1**; la 4 es precio al público del POS). El
   precio de esa lista se trae de `raw.articulosol.precio{N}` (N = 1..10).
   Si la lista del cliente tiene precio 0 para un producto → "sin precio",
   no se puede pedir. El `precio_unit` queda guardado en el pedido.
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

---

## Referencias al ecosistema

- **Mapa maestro**: `~/Desktop/Projects/Chimola/CLAUDE.md` — inventario de todos los proyectos hermanos.
- **Inventario detallado**: `~/Desktop/Projects/Chimola/ECOSYSTEM.md`.
- **Convenciones compartidas** (DEV first, secrets, region, git): `~/Desktop/Projects/Chimola/CONVENTIONS.md`.
- **Skills operativas** desde la carpeta padre: `/status`, `/deploy`, `/logs`, `/costos`, `/git-status`.
