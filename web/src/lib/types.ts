export type Seccion = "marro" | "indu" | "lima";

export interface Me {
  user: { email: string; rol: string; nombre: string; cliente_cod: number | null };
  cliente: {
    cliente_cod: number; nombre: string; lista_precios: number; descuento: number; cuit: string | null;
    contacto_nombre: string; contacto_email: string; contacto_telefono: string;
    localidad: string | null; provincia: string | null;
  } | null;
  puede_pedir: boolean;
  es_admin: boolean;
  es_franquicia: boolean;
}

export interface Swatch { color: string; hex: string; foto: string | null }

export interface Card {
  producto_cod: string; nombre: string; marca: string; temporada: string; rubro: string; categoria: string;
  seccion: Seccion; precio: number | null; precio_lista: number | null; pct_desc: number;
  foto: string | null; tiene_foto: boolean; colores: Swatch[]; destacado: boolean; n_variantes: number; stock?: number;
  /** Nombres visibles (alias del admin; si no hay alias, el valor de Aleph). */
  rubro_nombre?: string; temporada_nombre?: string; categoria_nombre?: string;
}
/** Alias de nombres por tipo: {categoria: {valor: nombre}, rubro: {...}, temporada: {...}}. */
export type Alias = Record<"categoria" | "rubro" | "temporada", Record<string, string>>;
export const aliasDe = (a: Alias | undefined, tipo: keyof Alias, valor: string) => a?.[tipo]?.[valor] || valor;

export interface Faceta { valor: string; n: number; hex?: string; nombre?: string; nuevo?: boolean; anterior?: boolean }

export interface Catalogo {
  seccion: Seccion | null; total: number; page: number; per_page: number; pages: number;
  items: Card[]; facetas: Record<string, Faceta[]>; precio_rango: { min: number | null; max: number | null };
  alias?: Alias;
}

export interface MenuSeccion {
  nombre: string; marca: string; temporadas: Faceta[]; tipos: Faceta[]; tendencias: Faceta[]; oportunidades: number; n: number;
  oportunidades_items?: { nombre: string; link: string }[];
  grupos?: { titulo: string; categoria: string; n: number; tipos: Faceta[] }[];
  /** Qué listas vienen del admin (true) vs. automáticas (false): temporadas/tipos/tendencias/grupos/oportunidades. */
  personalizado?: Partial<Record<"temporadas" | "tipos" | "tendencias" | "grupos" | "oportunidades", boolean>>;
}
export type Menu = Record<Seccion, MenuSeccion>;

export interface Variante {
  sku: string; ean: string | null; color_cod: string; color: string; talle: string;
  precio: number | null; precio_lista: number | null; pct_desc: number; es_manual: boolean; disponible: boolean; stock?: number;
}

export interface Producto {
  producto_cod: string; producto_nombre: string; marca: string; temporada: string; rubro: string; categoria: string;
  descripcion: string; ub: number | null; precio: number | null; precio_lista: number | null; pct_desc: number;
  medidas: string | null; materiales: string | null; descripcion_corta: string; peso_kg: number | null; medidas_origen: string | null;
  seccion: Seccion; colores: Swatch[]; talles: string[]; variantes: Variante[];
  rubro_nombre?: string; temporada_nombre?: string; categoria_nombre?: string;
  fotos: { url: string; filename: string; color: string; principal: boolean }[];
  relacionados: Card[]; familia: string | null;
}

export interface Curva { total_pedido: number; total_asignado: number; recortado: boolean; considera_carrito?: boolean; base?: "compras" | "stock"; items: { sku: string; color: string; talle: string; cantidad: number }[] }

export interface CartItem {
  sku: string; ean: string | null; producto_cod: string; producto_nombre: string; color_cod: string; color: string; talle: string;
  cantidad: number; precio_unit: number; precio_lista: number | null; pct_desc: number; manual: boolean; subtotal: number; foto: string | null;
  seccion: Seccion;
}
/** Lo que superaba lo disponible al agregar con `recortar: false`: nada se agregó, `maximo` es lo que todavía se puede sumar. */
export interface Ajuste { sku: string; producto_nombre: string; color: string; talle: string; pedido: number; maximo: number; en_carrito: number }
export interface Totales {
  unidades: number; subtotal: number; descuento_pct: number; descuento_monto: number; ahorro_descvta: number; total: number;
  iva_pct: number; iva_monto: number; total_con_iva: number;
}
export interface Carrito { items: CartItem[]; totales: Totales; avisos: string[]; minimo_unidades: number | null; minimo_monto: number | null; agregadas?: number; ajustes?: Ajuste[] }

export interface PedidoResumen {
  numero: number; fecha_str: string; confirmed_at: string; estado: string; unidades: number; total: number; total_con_iva: number;
  cliente_nombre: string; cliente_cod: number; xlsx_filename: string; observaciones: string; n_items: number;
}
export interface Pedido extends PedidoResumen {
  items: (CartItem & { subtotal: number })[]; subtotal: number; descuento_pct: number; descuento_monto: number; ahorro_descvta: number;
  iva_pct: number; iva_monto: number; contacto_nombre: string; contacto_email: string; contacto_telefono: string;
  historial?: { estado: string; por: string; en: string; detalle?: string }[]; puede_cancelar: boolean; odoo: boolean;
  email?: { enviado: boolean; destinatarios: string[]; error: string };
}

export interface HomeBloque { img: string; titulo: string; subtitulo?: string; cta?: string; link?: string; ancho?: "doble" | "simple"; tag?: string; kicker?: string; temporada?: string; rubro?: string; categoria?: string; oculto?: boolean }
export interface Home {
  seccion: Seccion; nombre: string; hero: HomeBloque[]; bloques: HomeBloque[]; banner_grilla: HomeBloque | null;
  secciones: { titulo: string; link: string | null; tipo: string; productos: Card[] }[];
}
