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
