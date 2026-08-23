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
existe (o es null), vale Aleph. Ningún override crea productos ni stock.

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
- Auditoría: todo override guarda `updated_at` + `updated_by` (email admin).

### 3.3 Criterios de aceptación
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

## 5. Pedidos (admin)

- Estados: `confirmado` → `procesado` | `cancelado` (solo admin cambia).
- Cada cambio agrega a `historial: [{estado, por, en}]`.
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
