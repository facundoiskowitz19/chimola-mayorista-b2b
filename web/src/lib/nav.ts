/* Helpers de navegación compartidos entre server y client (sin "use client"). */

/** Acepta solo rutas internas: empieza con "/" pero no con "//" (eso sería otro origen) y sin backslashes. */
export function destinoSeguro(next: string | null | undefined, porDefecto = "/h/marro"): string {
  if (!next) return porDefecto;
  if (!/^\/(?!\/)/.test(next) || next.includes("\\")) return porDefecto;
  if (next.startsWith("/auth/") || next.startsWith("/login")) return porDefecto;
  return next;
}
