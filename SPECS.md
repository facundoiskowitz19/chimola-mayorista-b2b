# SPECS — mayorista-b2b Fase 2 (admin total + compra rápida)

Estado: **aprobado 2026-08-23**. Este doc es la fuente de verdad funcional.
Arquitectura y gotchas técnicos: `CLAUDE.md`. Checklist de avance: `PLAN.md`.

---

## 1. Roles y permisos

| Rol | Puede |
|---|---|
| `cliente` | Ver catálogo publicado con SUS precios, armar carrito (detalle o compra rápida), confirmar pedidos, ver/repetir SUS pedidos. |
| `admin` | Todo lo anterior en modo lectura (sin poder pedir, no tiene cliente_cod) + **Administración**: catálogo, clientes/descuentos, pedidos de todos, configuración. |

El rol vive en `usuarios/{email}.rol`. No hay panel separado: el mismo sitio
muestra la sección "Administración" si `rol == admin`.

## 2. Fuentes de datos y precedencia

```
Aleph (ERP) ──sql-to-bq──▶ BigQuery (READONLY: productos, stock, precios, dim_cliente)
                                   ▲ fallback
Firestore (ADMINISTRABLE) ─────────┴─ overrides: pisan lo de BQ cuando existen
```

**Regla de oro**: BigQuery nunca se escribe desde el sitio. Todo lo que el
admin edita vive en Firestore y **pisa** el valor de Aleph; si el override no
existe (o es null), vale Aleph. Ningún override crea PRODUCTOS nuevos.
**Excepción (fase 6, E4)**: el admin puede crear **variantes manuales** de un
producto existente (`variantes_extra`, §3.5) — con stock y precio 100%
manuales, y marcadas en Excel/email porque Aleph no las conoce.

## 3. Catálogo administrable

### 3.1 Publicación
- `publicado = null` (default): **automático** — visible si stock neto > 0.
- `publicado = false`: oculto SIEMPRE (aunque tenga stock).
- `publicado = true`: visible, pero **solo si tiene stock neto > 0** (nunca se
  vende sin stock; el flag no inventa stock).
- Nivel producto (no variante): ocultar un producto oculta todas sus variantes.

### 3.2 Edición (overrides por producto)
- `nombre`, `descripcion`: pisan lo que viene de Aleph en catálogo, detalle,
  carrito, Excel y email.
- `precios: {lista → precio}`: pisa `articulosol.precio{N}` SOLO para esa
  lista. Ej: `{"1": 30000}` pisa lista 1; las demás listas siguen de Aleph.
  Precio override ≤ 0 no está permitido (la UI lo valida).
- `destacado`: los destacados aparecen primero en el grid del catálogo.
- `ub` (unidad de bulto, como el ACF `u.b` del Woo): cantidad mínima y múltiplo
  de compra por variante. La página de producto y la compra rápida fuerzan
  múltiplos de `ub`; null = libre.
- Auditoría: todo override guarda `updated_at` + `updated_by` (email admin).

### 3.3 Overrides por VARIANTE (`variantes: {sku: {...}}`)
- `stock`: **reemplaza** al stock neto de BQ (0 = no se vende). ⚠ Con stock
  manual el sitio deja de validar contra el stock real de Ezeiza — es
  responsabilidad del admin hasta quitar el override. La validación al
  confirmar (`stock.py`) usa el MISMO valor manual (consistencia).
- `oculta`: saca solo esa variante del catálogo (el producto sigue).
- `precios: {lista → precio}`: precio propio de la variante, pisa al del
  producto para esa lista.
- Todo editable desde el modal "Editar producto" del admin (tabla de variantes).

### 3.5 Variantes MANUALES (`variantes_extra: {sku: {...}}`) — fase 6, E4
- Variantes de un producto existente que **no existen en Aleph** (ej: un color
  nuevo). SKU generado `{prod}_{TALLE}_X{SLUGCOLOR}` (el prefijo `X` no puede
  chocar con un color_cod numérico de Aleph).
- `color`, `talle`, `stock` (>0) y `precios.1` (>0) obligatorios; `ean`
  opcional. Sin fallback a Aleph: stock y precio son 100% responsabilidad del
  admin, y la validación al confirmar usa ese stock manual.
- Se sintetizan en el catálogo heredando nombre/marca/temporada/rubro/fotos
  del producto; stock 0 las saca del catálogo del cliente.
- ⚠ Operativo: en el Excel y el email la línea sale marcada
  **"(VARIANTE MANUAL — no existe en Aleph)"** para que el equipo no la
  busque en el ERP al cargar la NP.
- Alta/edición/baja desde la ficha de producto (modo edición).

### 3.4 Criterios de aceptación
- Ocultar producto → desaparece del catálogo/compra rápida del cliente en ≤ 60 s
  (TTL del cache de overrides) sin redeploy.
- Editar precio lista 1 → el cliente con lista 1 ve el nuevo precio; un pedido
  confirmado guarda ese `precio_unit` en Firestore y en el Excel.
- El admin ve badges de salud: sin foto / sin precio en la lista N / oculto.

## 4. Clientes y descuentos

- `clientes_overrides/{cliente_cod}`: `descuento_pct` y/o `lista_precios`
  pisan `dim_cliente.descuento` / `dim_cliente.lis_pre`. `notas` libre.
- La UI de admin muestra el valor **efectivo** y su origen (Aleph u Override).
- El descuento se aplica como hoy: % cabecera sobre el subtotal del pedido.
- Alta de usuario desde la UI: email + cliente_cod (+ rol) → password generada,
  visible UNA vez en pantalla y guardada en el secret `mayorista-seed-passwords`.
- Reset password y activar/desactivar usuario desde la UI.
- Criterio: override 25% para 2722 (Aleph=20) → carrito, Excel y email usan 25%.
- **Contacto por cliente (2026-08-25)**: `clientes_overrides.{cod}` guarda
  `contacto_nombre` / `contacto_email` / `cuit` (el CUIT pisa al de Aleph, con
  origen visible en la ficha). El CLIENTE los ve precargados y editables en el
  formulario de confirmación del carrito («si lo cambiás, queda guardado para
  la próxima»); el ADMIN los edita en la ficha del cliente. El pedido guarda
  `contacto_nombre`/`contacto_email`, el detalle del admin los muestra y las
  plantillas de email tienen la variable `{contacto}`. Talle se muestra como
  «Talle X» (nunca «T X»). El alta de usuario valida el email (antes un email
  vacío daba un 400 críptico de Firestore).

## 5. Pedidos: estados, cancelación y notificaciones

- Estados: `confirmado` → `procesado` | `cancelado`; `procesado` → `cancelado`.
- **Cancelación por el cliente**: puede cancelar SU pedido solo mientras esté
  `confirmado` (el equipo aún no lo tomó). Botón "Cancelar pedido" en Mis
  pedidos con confirmación. Un pedido `procesado` solo lo cancela el admin.
- Cada cambio agrega a `historial: [{estado, por, en}]`.
- **Emails por estado** (config `notificar_estados`, default ON): al pasar a
  `procesado` o `cancelado` se avisa por email al cliente + Chimola (el de
  cancelado dice si canceló el cliente o el equipo). El resultado queda en
  `pedidos/{n}.email_{estado}`. Además del email original de confirmación con
  el Excel adjunto. En DEV todo se redirige a `EMAIL_OVERRIDE_TO`.
- Filtros del listado admin: estado, cliente, rango de fechas.
- "Reenviar email" reenvía la confirmación con el Excel del backup GCS.
- El cliente ve el estado actual de sus pedidos en "Mis pedidos".

## 6. Configuración global (`config/global`)

| Campo | Efecto | Default (si no existe doc) |
|---|---|---|
| `pedidos_email_to` | destino del mail de pedidos de Chimola | env `PEDIDOS_EMAIL_TO` |
| `banner_texto` | aviso arriba del catálogo (ej: "Cierre de temporada 20/9") | vacío = no se muestra |
| `aplicar_descvta` | aplicar además el desc. por artículo de Aleph (`descvta`) como en el Woo | `false` |
| `minimo_pedido_unidades` | mínimo de unidades para confirmar | null = sin mínimo |
| `iva_pct` | % de IVA informativo: las listas de Aleph son SIN IVA (la NP del ERP lo suma; verificado con Kinderland: subtotal −desc +21% = total NP). Se muestra como líneas "IVA" y "Total c/IVA" en carrito, Excel y email. 0 = ocultar. | `21` |

`EMAIL_OVERRIDE_TO` (redirección DEV) sigue siendo env-only, no administrable.

## 7. Compra rápida (cliente)

Tres formas de cargar rápido, todas terminan en el MISMO carrito:

1. **Tabla con miniaturas**: buscador + filtros → tabla editable paginada con
   [miniatura, código, producto, color, talle, stock, precio, **cantidad**].
   Botón "Agregar al carrito" suma todas las filas con cantidad > 0.
2. **Repetir pedido**: en Mis pedidos, botón "Repetir" → carga el carrito con
   las mismas variantes al precio ACTUAL, ajustando a stock disponible y
   avisando qué quedó afuera o recortado.
3. **Pegar códigos**: textarea que acepta líneas `SKU,cantidad`, `EAN,cantidad`
   o `SKU<TAB>cantidad` (pegado desde Excel). Reporta líneas no reconocidas,
   sin stock o sin precio; agrega el resto.

- El **carrito** muestra miniatura de cada línea.
- Criterio: cargar 5 líneas desde la tabla + 1 por pegado + repetir un pedido
  → el carrito consolida por SKU (suma cantidades) y el total es correcto.

## 8. Fuera de alcance (fase 2)

Pagos online, integración automática con Aleph (NP), multi-idioma/moneda,
productos manuales fuera de Aleph, edición de stock, notificaciones push.

## 9. Modelo de datos Firestore (completo tras fase 2)

```
usuarios/{email}             {password_hash, cliente_cod, nombre_display, rol, activo, ...}
pedidos/{numero:06d}         {..., estado, historial: [{estado, por, en}]}
carritos/{email}             {items[], updated_at}
login_attempts/{email}       {ventana_desde, intentos}
contadores/pedidos           {valor}
catalogo_overrides/{prod}    {publicado, destacado, nombre, descripcion, precios{lista:precio}, updated_at, updated_by}
clientes_overrides/{cod}     {descuento_pct, lista_precios, notas, updated_at, updated_by}
config/global                {pedidos_email_to, banner_texto, aplicar_descvta, minimo_pedido_unidades, updated_at, updated_by}
```

## 10. Identidad visual y UX v2 (handoff 2026-08-23)

Rediseño aplicado desde `design_handoff_mayorista_ux/` (Claude Design):
- **Identidad "Broadsheet"** (decisión del usuario: reemplaza a la de Lautin):
  Source Serif 4, fondo papel `#f3f2f2`, texto `#201e1d`, **cian `#0088b0`**
  para todo lo interactivo (hover `#1186ac`, pressed `#006786`, tinte
  `#e9f8ff`), **magenta `#d6006c`/`#aa0b56`** SOLO para errores/cancelado,
  radio 2px, kickers 12px `letter-spacing:.14em`. Sin emojis en la UI.
- **Estructura**: sidebar eliminado (nav horizontal + facetas arriba de la
  grilla), chips de filtros activos con ×, carga de cantidades EN LÍNEA desde
  la card, matriz color × talle (stock arriba, cantidades abajo), carrito con
  filas propias (miniatura, × por fila, avisos de ajuste en la fila), pegado
  con reconciliación (contadores + tabla por línea), pedidos maestro-detalle,
  admin: click en el producto abre el **editor como pantalla** (checkbox solo
  para lote con barra contextual), override vs Aleph explícito por lista
  (campo vacío = usa Aleph; se eliminó el convenio del 0), publicación con
  consecuencias escritas, salud del catálogo accionable, aviso de stock manual
  por variante con los dos números.
- Los mocks (`Cliente.dc.html` / `Admin.dc.html`) y el README del handoff son
  la referencia de fidelidad; tokens en `_ds/broadsheet-*/styles.css`.

## 11. Catálogo v2 y taxonomía (fase 8, 2026-08-24)

- **Taxonomía** (nombres de Aleph invertidos respecto del uso): el campo
  `rubro` trae los tipos (Billeteras, Mochilas...) y `tipo_producto` las
  categorías (Marroquineria, Textil, Indumentaria...). En el sitio:
  **Categoría** ← `tipo_producto` · **Tipo de producto** ← `rubro`;
  `subrubro` (siempre NULL) se eliminó. Ambos se normalizan
  (mayúsculas/acentos → un solo valor; vacío → "Otros").
- **Catálogo cliente**: rail izquierdo de filtros (Categoría, Tipo de
  producto, Marca, Temporada y Talle como pills multi; Color como
  multiselect), buscador arriba del rail, chips de filtros activos sobre el
  grid. Color/talle filtran a nivel VARIANTE (el producto aparece si alguna
  variante matchea). Grid de 3 columnas.
- **Click en la imagen** de una card → ficha del producto (link `?p=COD`;
  navegación completa: la sesión se rearma por cookie y el carrito persiste
  en Firestore).
- **Sin paginado**: el grid acumula de a `ITEMS_POR_PAGINA` con «Mostrar
  más — viste X de Y» (Streamlit no expone eventos de scroll; es el
  equivalente nativo del scroll infinito).
- **Admin — acciones masivas por alcance**: los filtros del catálogo admin
  (búsqueda, marca, temporada, categoría, tipo de producto, pill) definen el
  conjunto; el expander «Acciones masivas sobre todo lo filtrado» aplica
  ocultar / automático / destacar / quitar destacado a TODO el conjunto, con
  confirmación cuando son más de 10. `overrides.set_masivo()` escribe en
  batches de 400 (límite Firestore 500) y solo acepta publicado/destacado.


## 12. Privacidad de stock (2026-08-25)

El stock remanente NUNCA se muestra a usuarios no-admin, en ninguna vista:
sin tabla "Stock disponible" en la matriz, sin "N u." en las cards, sin
columna Stock en compra rápida, sin números de stock en ningún mensaje.
Cuando un cliente pide más de lo disponible, la cantidad se acota al máximo
y se le avisa con un mensaje EFÍMERO (st.toast, unos segundos):
"estás superando la cantidad disponible — lo ajustamos al máximo posible".
Los toasts diferidos viajan por `st.session_state._toasts` y se disparan al
inicio del run siguiente (sobreviven al st.rerun). El admin sigue viendo
stock en todas las vistas (matriz con leyenda, cards, tablas del admin).
