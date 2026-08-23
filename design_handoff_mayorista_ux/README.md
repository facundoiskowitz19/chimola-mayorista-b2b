# Handoff: rediseño UX del mayorista B2B (Chimola / Lima / Lautin)

## Qué es esto

Rediseño de las pantallas de cliente y de la sección Administración de
`mayorista-b2b` (Streamlit 1.41 + BigQuery + Firestore, ver `README.md` y
`CLAUDE.md` del repo). Dos archivos HTML con las pantallas resueltas y este
documento con el detalle de cada cambio, por qué, dónde toca el código y cómo
implementarlo en Streamlit.

## Sobre los archivos de diseño

`Cliente.dc.html` y `Admin.dc.html` son **referencias de diseño hechas en
HTML**: prototipos que muestran la intención visual y de interacción. No son
código para copiar ni para servir. La tarea es **reproducir esas pantallas en
el entorno que ya existe** — Streamlit, con sus widgets nativos y el CSS que
`app.py` ya inyecta — no reemplazar Streamlit por HTML propio.

Abrilos en el navegador y navegá con las pestañas de arriba. `Cliente.dc.html`
tiene además una barra "Vista" con las 6 pantallas.

## Fidelidad

**Alta.** Colores, tipografía, tamaños, espaciado y estados están definidos.
La sección "Design tokens" tiene los valores exactos.

---

## Dos decisiones separadas — leelas antes de empezar

Los cambios se dividen en dos grupos independientes. Se pueden tomar por
separado y conviene hacerlo.

**1. Estructura y flujo (recomendado, sin discusión de marca).**
Navegación fuera del sidebar, click en el producto para editarlo, matriz de
talles, estados de error en línea, etc. No dependen de ningún color.

**2. Identidad visual.**
Los mocks usan un sistema editorial (serif Source Serif 4 sobre papel #f3f2f2,
cian como color interactivo). Eso **reemplaza** la identidad que hoy tiene el
sitio, tomada de lautin.com.ar (Lato, negro #1C1C1A, #AC9B91). Es una decisión
de marca, no técnica. Si se decide mantener Lautin, aplicá el grupo 1 con los
colores y la tipografía actuales: la estructura no cambia.

---

## Cambios de la parte cliente

### 1. Navegación y filtros salen del sidebar

**Hoy** (`app.py` → `sidebar()`): el sidebar tiene la navegación (Catálogo,
Compra rápida, Carrito, Mis pedidos, Administración) y además, dentro de
`page_catalogo()`, un bloque `with st.sidebar:` con los filtros. Dos cosas
distintas compitiendo por la misma columna, y los filtros aparecen y
desaparecen según la página.

**Propuesta**: navegación como fila horizontal debajo del header; filtros como
barra de facetas arriba de la grilla; sidebar eliminado.

**Cómo**: `st.segmented_control` o una fila de `st.columns` con botones para la
nav. Filtros con `st.columns([2,1,1,1,1])` + `st.text_input` /
`st.multiselect`. Para ocultar el sidebar: `initial_sidebar_state="collapsed"`
en `st.set_page_config` y CSS `[data-testid="stSidebar"] {display:none}`.

**Dificultad**: baja. Todo widget nativo.

### 2. Chips de filtros activos

**Hoy**: los filtros activos solo se ven abriendo cada multiselect. Hay un
botón "Limpiar filtros".

**Propuesta**: fila de chips con los filtros aplicados, cada uno con × para
quitarlo individualmente, y el contador de resultados a la derecha.

**Cómo**: los chips son `st.button` chicos en `st.columns` (uno por filtro
activo) que hacen `st.session_state.pop(f"f_{campo}")` + `st.rerun()`. El
estilo pill sale por CSS.

**Dificultad**: baja.

### 3. Matriz color × talle en la ficha de producto

Es el cambio de mayor impacto para quien carga pedidos.

**Hoy** (`page_producto()`): por cada color se dibujan `st.number_input` en
filas de 4 columnas, con el label `f"T {talle} · stock {stock}"`. Con la curva
completa de indumentaria (4 al 16) son 6 inputs por color, cada uno con su
label largo: la pantalla se vuelve una lista vertical enorme y no se puede
comparar stock entre talles.

**Propuesta**: una tabla con los colores como filas y los talles como
columnas. En cada casilla la cantidad a pedir; debajo, en chico, el stock
disponible. Casilla sin stock = deshabilitada. Total de unidades y monto con
descuento al pie, junto al botón.

**Cómo en Streamlit**: pivotear las variantes y usar `st.data_editor` con
`index=color` y una columna por talle
(`df.pivot(index="color", columns="talle", values="cantidad")`), todas
`st.column_config.NumberColumn(min_value=0, step=1)`. El stock no se puede
poner *debajo* de cada celda en un `data_editor`; dos opciones honestas:

- una tabla de stock (read-only, mismo pivot) arriba de la editable — dos
  tablas alineadas, simple y nativo;
- el stock en el `help` de cada columna + validación al agregar al carrito
  (recorte a stock, ya implementado en `pedidos.agregar_al_carrito`).

Recomiendo la primera. La celda deshabilitada por falta de stock tampoco es
nativa: validar al confirmar y mostrar el aviso, que es lo que ya hace
`resolver_pegado`.

**Dificultad**: media. Nativo pero requiere pivot y volver a mapear a SKU al
guardar.

### 4. Cargar cantidades desde la grilla del catálogo

**Hoy**: cada producto obliga a `ir("producto", ...)`, cargar, volver. Para un
pedido de 20 productos son 40 navegaciones.

**Propuesta**: la card se expande en línea con la matriz de variantes y el
botón de agregar, sin salir del catálogo. Es lo que ya hace el retail
(chimola.com.ar carga al carrito desde la card con color y talle).

**Cómo**: `st.expander` dentro de la card, o `st.session_state.card_abierta` +
un bloque condicional después de la fila de la grilla. Ojo con el costo: un
`expander` por card con `data_editor` adentro es pesado; abrir de a una.

**Dificultad**: media.

### 5. Carrito: quitar por fila, no columna de checkbox

**Hoy** (`page_carrito()`): la columna `quitar` es un `CheckboxColumn` y el
borrado se aplica en el siguiente rerun. Tildar algo y esperar no comunica que
se borró.

**Propuesta**: × al final de cada fila, borrado inmediato. Miniatura, código y
color en una sola celda de producto. Panel de totales sticky a la derecha.

**Cómo**: `st.data_editor` no soporta un botón por fila. Dos caminos:
`st.column_config.CheckboxColumn` (lo actual) o armar el carrito con
`st.columns` fila por fila y un `st.button("×", key=sku)`. Con carritos de
hasta ~50 líneas la segunda es viable y da el control real.

**Dificultad**: media.

### 6. Error de stock cambiado, en la fila afectada

**Hoy**: `StockInsuficiente` muestra `st.error` + un `st.dataframe(e.problemas)`
suelto y después ajusta el carrito. El usuario ve una tabla de problemas
separada de la tabla del carrito y tiene que cruzarlas a mano.

**Propuesta**: banner arriba diciendo cuántas variantes cambiaron y qué se
ajustó, y en la fila del carrito afectada una línea en magenta: "Ajustado de
10 a 6 u. — es todo el stock disponible".

**Cómo**: guardar `e.problemas` en `st.session_state` al ajustar el carrito y,
al dibujar cada fila, si el SKU está en ese dict, agregar el texto. Requiere el
carrito dibujado con `st.columns` (cambio 5) o una columna extra "Aviso" en el
`data_editor`.

**Dificultad**: baja, una vez hecho el cambio 5.

### 7. Pegado de códigos: reconciliación en vez de pila de warnings

**Hoy** (`page_compra_rapida`): `for a in avisos: st.warning(a)` — seis cajas
amarillas apiladas, sin distinguir "se agregó", "se ajustó" y "no existe".

**Propuesta**: tres contadores (agregadas / ajustadas / sin reconocer) y una
tabla con una fila por línea leída, con el motivo al lado y la cantidad final,
en el color que corresponde.

**Cómo**: `resolver_pegado` (en `compra_rapida.py`) ya tiene toda la
información; hoy la aplana a strings. Cambiar la firma para devolver
`(items, incidencias)` donde cada incidencia es
`{"linea": n, "codigo": str, "tipo": "ok"|"ajustada"|"no_encontrada"|"sin_precio", "pedido": int, "cargado": int, "detalle": str}`
y renderizar eso. Ese cambio también mejora los tests (`tests/test_pure.py`).

**Dificultad**: baja en UI, requiere tocar `compra_rapida.py`.

### 8. Mis pedidos: maestro-detalle

**Hoy** (`page_pedidos`): `st.dataframe` + un `st.selectbox` con los números de
pedido para elegir el detalle. Dos controles para una sola intención.

**Propuesta**: `st.dataframe(on_select="rerun", selection_mode="single-row")` y
el detalle debajo de la fila seleccionada. "Repetir pedido" como acción
primaria. El estado como tag de color, no texto plano.

**Dificultad**: baja. `_sec_pedidos()` en `admin_ui.py` ya lo hace así — copiar
ese patrón.

---

## Cambios de la parte Administración

### 9. Click en el producto abre el editor  ← el pedido explícito

**Hoy** (`admin_ui.py` → `_sec_catalogo`): la tabla es
`st.dataframe(..., on_select="rerun", selection_mode="multi-row")` y editar
requiere tildar el checkbox de una fila y después apretar "✏️ Editar", que está
`disabled=len(sel_cods) != 1`. No se puede hacer click en un producto y
editarlo.

**Propuesta**: el nombre del producto es la acción. Un click abre el editor.
Los checkbox quedan solo para lote.

**Cómo (dos opciones, en orden de preferencia):**

1. **Dos modos de tabla.** Por defecto `selection_mode="single-row"`: al
   seleccionar una fila se abre el editor directo (sin botón intermedio). Un
   toggle "Selección múltiple" cambia a `multi-row` y ahí sí aparece la barra
   de lote. Es la más nativa y la más barata.
2. **Columna de link.** Agregar una columna con
   `st.column_config.LinkColumn` que apunte a `?prod=M211`, y leer
   `st.query_params` para abrir el editor. Da el click sobre el nombre tal cual
   está en el mock y además hace el editor linkeable/compartible.

**Dificultad**: baja (opción 1), media (opción 2).

### 10. El editor de producto deja de ser un modal

**Hoy**: `@st.dialog("Editar producto", width="large")` con nombre,
descripción, 4 precios, publicación, destacado, U.B. y la tabla de variantes
adentro. Es demasiado contenido para un diálogo: hay scroll interno, no se
puede comparar con la lista y no es linkeable.

**Propuesta**: pantalla propia con breadcrumb "← Catálogo", el producto como
título, y las acciones (Guardar / Descartar / Quitar overrides) al pie, sobre
una regla.

**Cómo**: `st.session_state.adm_prod = cod` y en `page_admin()` rutear a
`_editar_producto(cod)` como sección en vez de invocar el `@st.dialog`. La
función ya está escrita: solo hay que sacarle el decorador y agregarle el
botón de volver.

**Dificultad**: baja. Es el cambio de mejor relación costo/beneficio del admin.

### 11. Override vs Aleph explícito en cada campo

**Hoy**: los precios son `number_input` con `value=override o 0` y el valor de
Aleph escondido en el `help`. "0 = usar Aleph" es un convenio invisible: un
precio en 0 se lee como precio cero, no como "sin override".

**Propuesta**: una fila por lista con tres columnas — **Aleph** (solo lectura),
**Manual** (editable, vacío = usa Aleph) y el estado escrito al costado ("Manual
— pisa a Aleph para lista 1" / "Usa Aleph"). La casilla con override se tiñe
con el color interactivo. Mismo criterio para nombre y descripción: el valor de
Aleph debajo del campo, con un link "volver a Aleph".

**Cómo**: `st.columns` por lista con `st.markdown` para el valor de Aleph y
`st.number_input(value=None)` para el manual — `value=None` con
`min_value=0.0` permite el campo vacío de verdad y elimina el convenio del 0.
El teñido de la casilla no es alcanzable con widget nativo; alcanza con la
etiqueta de estado al costado.

**Dificultad**: media. Cambia el contrato con
`overrides.set_catalogo_override` (mandar `None` en lugar de filtrar `> 0`).

### 12. Publicación con la consecuencia escrita

**Hoy**: `st.radio` horizontal con `PUB_LABELS` = "⚪ Auto / 🟢 Publicado /
🙈 Oculto". Nadie sabe de memoria que "Publicado" **igual** exige stock > 0 y
que "Auto" es "visible si hay stock" (SPECS §3.1).

**Propuesta**: tres opciones apiladas, cada una con su regla en una línea:
"Automático — visible si tiene stock", "Publicado — visible, siempre con
stock", "Oculto — nunca visible".

**Cómo**: `st.radio` con `captions=[...]`. Es soporte nativo, cambio de una
línea.

**Dificultad**: baja.

### 13. Barra de lote solo cuando hay selección

**Hoy**: seis botones siempre visibles, casi siempre deshabilitados
(`disabled=not sel_cods`), más la paginación en la misma fila de 7 columnas.

**Propuesta**: sin selección no hay barra. Con selección aparece una barra con
"N productos seleccionados", las acciones y "Deseleccionar". La paginación se
separa a su propia fila.

**Cómo**: `if sel_cods:` alrededor del bloque. Trivial y saca ruido de la
pantalla más usada del admin.

**Dificultad**: baja.

### 14. Advertencia de stock manual en la fila que la causa

**Hoy**: un `st.markdown` general arriba de la tabla de variantes: "⚠ Con stock
manual el sitio deja de validar contra el stock real". No dice en qué variante
ni con qué números.

**Propuesta**: el aviso nombra el SKU y los dos valores: "M211_U_101 tiene
stock manual (30 u.) sobre un stock real de 24. Mientras esté en manual, el
sitio deja de validar contra el stock de Aleph y puede vender más de lo que
hay."

**Cómo**: después del `data_editor` de variantes, recorrer las filas con
`stock_manual` no nulo y emitir un aviso por cada una comparando contra
`stock_bq[sku]` (ya está calculado en `_editar_producto`).

**Dificultad**: baja.

### 15. Salud del catálogo accionable

**Hoy** (`_sec_inicio`): cinco `st.metric` con "Ocultos", "Sin foto", "Sin
precio L1", "Con overrides". Son números muertos: para actuar hay que ir al
catálogo y reconstruir el filtro a mano.

**Propuesta**: cada número con un link que abre el catálogo con ese filtro
rápido ya aplicado.

**Cómo**: los filtros rápidos ya existen como `st.pills` en `_sec_catalogo`
(`adm_pill`). Un botón que haga
`st.session_state.update(adm_nav="catalogo", adm_pill="Sin foto")` + `st.rerun()`.

**Dificultad**: baja.

---

## Orden de implementación sugerido

Por relación impacto / costo:

1. **10** editor de producto como pantalla (saca el `@st.dialog`)
2. **9** click en el producto para editar
3. **13** barra de lote condicional
4. **12** publicación con captions
5. **15** salud del catálogo accionable
6. **14** aviso de stock manual por variante
7. **1** + **2** nav y filtros fuera del sidebar
8. **8** maestro-detalle en Mis pedidos
9. **7** reconciliación del pegado (toca `compra_rapida.py`)
10. **11** override vs Aleph explícito (toca el contrato de overrides)
11. **3** matriz color × talle
12. **5** + **6** carrito con filas propias y aviso en línea
13. **4** carga en línea desde la grilla

Los primeros seis son casi todos de una tarde y arreglan lo que más molesta.

## Lo que Streamlit nativo no da

Sé de entrada qué no va a salir igual al mock, para no perder tiempo:

- **Botón por fila dentro de una tabla.** `st.data_editor` no lo tiene. O
  checkbox, o construir las filas con `st.columns`.
- **Contenido secundario dentro de una celda** (el stock debajo de la cantidad,
  la miniatura junto al código y el color en la misma celda). Se resuelve con
  tablas apiladas o con filas hechas a mano.
- **Sticky.** El panel de totales del carrito fijo al hacer scroll necesita CSS
  sobre el contenedor de la columna (`position:sticky`), y es frágil entre
  versiones de Streamlit.
- **Estado de celda teñido** según si tiene override. No hay estilo por celda
  editable; usar una columna de estado en texto.
- **Hover.** Todo lo que en el mock reacciona al hover se puede pintar por CSS
  sobre `.stButton > button`, pero no dentro de tablas.

Nada de esto es bloqueante: en todos los casos hay un equivalente nativo que
conserva la intención. Evitá reemplazar tablas por HTML propio con
`unsafe_allow_html` — pierde la edición y la selección, que es justo lo que
estas pantallas necesitan.

## Design tokens

Del sistema usado en los mocks (`_ds/broadsheet-.../styles.css`). Si se
mantiene la identidad Lautin, reemplazá la columna de color y la tipografía y
dejá el resto.

**Color**

| Rol | Valor |
|---|---|
| Fondo | `#f3f2f2` |
| Texto | `#201e1d` |
| Interactivo (acento) | `#0088b0` · hover `#1186ac` · pressed `#006786` |
| Tinte de acento | `#e9f8ff` (fondo) · `#cbeeff` (pressed) |
| Alerta / segundo acento | `#d6006c` · texto `#aa0b56` · tinte `#fff1f4` |
| Neutros | 100 `#f8f4f4` · 200 `#eae7e7` · 300 `#d7d3d3` · 400 `#bab6b6` · 500 `#9b9797` · 600 `#7d7979` · 700 `#605d5d` · 800 `#444141` · 900 `#2d2b2b` |
| Divisor | `#201e1d` al 16% |

Uso: cian para todo lo interactivo; magenta solo para error, cancelado y
acciones destructivas. Nunca los dos en el mismo componente.

**Tipografía**: Source Serif 4 (400 / 600). Título de pantalla 52px/0.95,
título de sección 32px, título de ítem 18–20px, cuerpo 16–17px, dato de tabla
16px, etiqueta de columna 14px, kicker 12px con `letter-spacing:0.14em` en
mayúsculas. Sin sans en la interfaz.

**Espaciado**: 5 / 10 / 15 / 20 / 30 / 40 px. **Radio**: 2px.
**Foco**: `outline: 2px solid #0088b0; outline-offset: 2px`.

**Estado (tags)**: confirmado = tinte cian + `#006786`; procesado = `#eae7e7` +
`#444141`; cancelado = tinte magenta + `#aa0b56`. Mayúsculas, 13px, radio 2px.

## Assets

- `static/logo_lautin.png` — del repo, sin cambios.
- Las imágenes son **placeholders rayados** con una etiqueta de qué va ahí
  (`foto M211`, `banner temporada`). En la app real van las fotos firmadas del
  bucket (`fotos.foto_principal`, `fotos.fotos_producto`).
- Iconos: los mocks no usan ninguno. Si hacen falta, el sistema pide Phosphor
  en peso duotone. Los emojis de los labels actuales (📚 ⚡ 🛒 📦 🛠) se
  eliminan.

## Datos de los mocks

Los productos, colores, precios y clientes son **de muestra**, armados con el
vocabulario real de chimola.com.ar (Mochila Moscú, Pouch Snack, Bandolera Rina,
colores BLACK / VISON / NACHOS, talles U y 4–16). Los precios mayoristas son
inventados. No los tomes como datos.

## Archivos

- `Cliente.dc.html` — login, catálogo, producto, compra rápida, carrito, mis
  pedidos. Barra "Vista" arriba para navegar.
- `Admin.dc.html` — inicio, catálogo, editor de producto, pedidos, clientes.
  Pestañas arriba; en Catálogo, click en el nombre abre el editor.
- `_ds/broadsheet-.../styles.css` — tokens y clases del sistema visual.
- `support.js`, `static/` — runtime y assets para que los HTML abran solos.

Archivos del repo que toca cada cambio: `app.py` (`sidebar`, `page_catalogo`,
`page_producto`, `page_carrito`, `page_pedidos`, `page_compra_rapida`),
`admin_ui.py` (`_sec_inicio`, `_sec_catalogo`, `_editar_producto`,
`_sec_pedidos`), `compra_rapida.py` (`resolver_pegado`), `overrides.py`
(`set_catalogo_override`).
