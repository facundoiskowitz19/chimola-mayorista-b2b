import { notFound } from "next/navigation";
import { apiServer } from "@/lib/api";
import type { Catalogo, HomeBloque, Me } from "@/lib/types";
import { SECCIONES } from "@/lib/format";
import FilterRail from "@/components/FilterRail";
import CatalogGrid from "@/components/CatalogGrid";
import SortSelect from "@/components/SortSelect";

const FILTROS = ["categoria", "rubro", "marca", "temporada", "color", "talle"] as const;
export type Sel = Record<(typeof FILTROS)[number], string[]> & {
  q: string; solo_foto: boolean; solo_desc: boolean; precio_min: string; precio_max: string; orden: string;
};

function parse(sp: Record<string, string | string[] | undefined>): Sel {
  const arr = (k: string) => { const v = sp[k]; return v === undefined ? [] : Array.isArray(v) ? v : [v]; };
  const one = (k: string) => { const v = sp[k]; return (Array.isArray(v) ? v[0] : v) || ""; };
  return {
    categoria: arr("categoria"), rubro: arr("rubro"), marca: arr("marca"), temporada: arr("temporada"), color: arr("color"), talle: arr("talle"),
    q: one("q"), solo_foto: one("solo_foto") !== "0", solo_desc: one("solo_desc") === "1",
    precio_min: one("precio_min"), precio_max: one("precio_max"), orden: one("orden") || "destacados",
  };
}

export function queryDe(sel: Sel, seccion: string, page = 1, per_page = 24): string {
  const u = new URLSearchParams();
  if (seccion !== "todo") u.set("seccion", seccion);
  FILTROS.forEach((f) => sel[f].forEach((v) => u.append(f, v)));
  if (sel.q) u.set("q", sel.q);
  if (!sel.solo_foto) u.set("solo_foto", "false");
  if (sel.solo_desc) u.set("solo_desc", "true");
  if (sel.precio_min) u.set("precio_min", sel.precio_min);
  if (sel.precio_max) u.set("precio_max", sel.precio_max);
  u.set("orden", sel.orden); u.set("page", String(page)); u.set("per_page", String(per_page));
  return u.toString();
}

type SP = Record<string, string | string[] | undefined>;

export default async function CatalogoPage({ params, searchParams }: { params: Promise<{ seccion: string }>; searchParams: Promise<SP> }) {
  const { seccion } = await params;
  if (seccion !== "todo" && !SECCIONES[seccion]) notFound();
  const sel = parse(await searchParams);
  const [cat, me, ban] = await Promise.all([
    apiServer<Catalogo>(`/catalogo?${queryDe(sel, seccion)}`), apiServer<Me>("/auth/me"),
    seccion === "todo" ? Promise.resolve(null) : apiServer<{ banner_grilla: HomeBloque | null }>(`/home/${seccion}/banner`).catch(() => null),
  ]);

  let titulo = seccion === "todo" ? "Todo el catálogo" : SECCIONES[seccion].nombre;
  if (sel.q) titulo = `Resultados para “${sel.q}”`;
  else if (sel.temporada.length === 1) titulo = sel.temporada[0];
  else if (sel.rubro.length === 1) titulo = sel.rubro[0];
  else if (sel.categoria.length === 1) titulo = sel.categoria[0];
  else if (sel.solo_desc) titulo = `Oportunidades · ${titulo}`;

  return (
    <div className="container-lt pb-10 pt-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-baseline gap-4">
          <h1 className="font-brand text-[28px] font-extrabold">{titulo}</h1>
          <span className="hidden h-6 w-px bg-line-2 sm:block" />
          <span className="font-sans text-[13px]">{cat.total} producto{cat.total === 1 ? "" : "s"} encontrado{cat.total === 1 ? "" : "s"}</span>
        </div>
        <SortSelect orden={sel.orden} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[200px_1fr]">
        <FilterRail seccion={seccion} sel={sel} facetas={cat.facetas} rango={cat.precio_rango} />
        <CatalogGrid key={queryDe(sel, seccion)} inicial={cat} query={queryDe(sel, seccion)} puedePedir={me.puede_pedir} banner={ban?.banner_grilla ?? null} />
      </div>
    </div>
  );
}
