export function money(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return "$" + Math.round(n).toLocaleString("es-AR");
}

export function pct(n: number | null | undefined): string {
  if (!n) return "";
  return `${Math.round(n)}%`;
}

export function titulo(s: string | null | undefined): string {
  if (!s) return "";
  return s.toLowerCase().replace(/(^|\s|-)\p{L}/gu, (m) => m.toUpperCase());
}

export const SECCIONES: Record<string, { nombre: string; marca: string }> = {
  marro: { nombre: "Marroquinería", marca: "Chimola" },
  indu: { nombre: "Indumentaria", marca: "Chimola" },
  lima: { nombre: "LIMA", marca: "Lima" },
};


/** La descripción de Aleph es un párrafo largo tipo "… Medida: 18 cm alto × 12.5 cm ancho Variantes: … Composición: 100% algodón …".
 *  Para la ficha (vista 16 de Vale) se separa en: frase corta en negrita, Medidas y Materiales. */
export function fichaDesdeDescripcion(desc: string | null | undefined): { corto: string; medidas: string | null; materiales: string | null; completa: string } {
  const d = (desc || "").replace(/\s+/g, " ").trim();
  if (!d) return { corto: "", medidas: null, materiales: null, completa: "" };
  const CORTE = "(?=\\s(?:Variantes?|Caracter[ií]sticas|Colores|Talles?|Materiales?|Composici[oó]n|Medidas?|¿Qu[eé])\\b|\\.\\s|$)";
  let med = d.match(new RegExp("Medidas?:?\\s*(.+?)" + CORTE, "i"));
  if (!med) med = d.match(/((?:(?:Ancho|Alto|Profundidad|Largo|Di[aá]metro|Capacidad):?\s*\d[\d.,]*\s*(?:cm|mm|lts?|ml)\s*)+)/i);
  const mat = d.match(new RegExp("(?:Materiales?|Composici[oó]n):?\\s*(.+?)" + CORTE, "i"));
  const corto = d.split(/(?<=[.!?])\s/)[0].replace(/\s*(Medidas?|Caracter[ií]sticas|Ancho:|Alto:).*$/i, "").trim();
  return { corto, medidas: med ? med[1].trim().replace(/[.,;]$/, "") : null, materiales: mat ? mat[1].trim().replace(/[.,;]$/, "") : null, completa: d };
}
