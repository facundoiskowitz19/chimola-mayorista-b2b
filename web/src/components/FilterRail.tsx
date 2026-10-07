"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import type { Faceta } from "@/lib/types";
import type { Sel } from "@/app/(shop)/c/[seccion]/page";
import { Chevron, XIcon } from "./Brand";
import { capital } from "./ProductCard";

type FK = "categoria" | "rubro" | "marca" | "temporada" | "color" | "talle";
const GRUPOS: { key: FK; titulo: string; abierto: boolean }[] = [
  { key: "rubro", titulo: "Tipo de producto", abierto: true },
  { key: "color", titulo: "Color", abierto: true },
  { key: "talle", titulo: "Talle", abierto: false },
  { key: "temporada", titulo: "Temporada", abierto: false },
  { key: "categoria", titulo: "Categoría", abierto: false },
  { key: "marca", titulo: "Marca", abierto: false },
];

export default function FilterRail({ seccion, sel, facetas, rango }: {
  seccion: string; sel: Sel; facetas: Record<string, Faceta[]>; rango: { min: number | null; max: number | null };
}) {
  const router = useRouter(); const path = usePathname(); const sp = useSearchParams();
  const [abiertos, setAbiertos] = useState<Record<string, boolean>>(Object.fromEntries(GRUPOS.map((g) => [g.key, g.abierto || sel[g.key].length > 0])));
  const [pmin, setPmin] = useState(sel.precio_min); const [pmax, setPmax] = useState(sel.precio_max);

  function navegar(mut: (u: URLSearchParams) => void) {
    const u = new URLSearchParams(sp.toString());
    mut(u);
    router.push(`${path}?${u.toString()}`);
  }
  function toggle(k: string, v: string) {
    navegar((u) => { const vals = u.getAll(k); u.delete(k); (vals.includes(v) ? vals.filter((x) => x !== v) : [...vals, v]).forEach((x) => u.append(k, x)); });
  }

  const chips: { key: string; label: string; quitar: (u: URLSearchParams) => void }[] = [];
  (["categoria", "rubro", "marca", "temporada", "color", "talle"] as const).forEach((k) => sel[k].forEach((v) =>
    chips.push({ key: `${k}:${v}`, label: k === "talle" ? `Talle ${v}` : k === "color" ? capital(v) : v, quitar: (u) => { const vals = u.getAll(k).filter((x) => x !== v); u.delete(k); vals.forEach((x) => u.append(k, x)); } })));
  if (sel.q) chips.push({ key: "q", label: `“${sel.q}”`, quitar: (u) => u.delete("q") });
  if (sel.solo_foto) chips.push({ key: "solo_foto", label: "Sólo con foto", quitar: (u) => u.set("solo_foto", "0") });
  if (sel.solo_desc) chips.push({ key: "solo_desc", label: "Sólo ofertas", quitar: (u) => u.delete("solo_desc") });
  if (sel.precio_min || sel.precio_max) chips.push({ key: "precio", label: `$${sel.precio_min || "0"} – $${sel.precio_max || "∞"}`, quitar: (u) => { u.delete("precio_min"); u.delete("precio_max"); } });

  const mostrarGrupo = (k: FK) => {
    if (k === "marca" && seccion !== "todo") return false;
    if (k === "categoria" && seccion === "indu") return false;
    return (facetas[k as string] || []).length > 1 || sel[k].length > 0;
  };

  return (
    <aside className="text-[13px]">
      <div className="flex items-center justify-between border-b-2 border-ink pb-2">
        <h2 className="font-brand text-[15px] font-bold">Tu Selección</h2>
        {chips.length > 0 && <button onClick={() => router.push(path)} className="font-sans text-[11px] hover:underline">Borrar todos</button>}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {chips.length === 0 && <span className="font-sans text-[12px] text-muted">Sin filtros</span>}
        {chips.map((c) => (
          <button key={c.key} onClick={() => navegar(c.quitar)} className="chip hover:bg-[#d6d6d6]">{c.label} <XIcon size={11} /></button>
        ))}
      </div>

      <h2 className="mt-8 border-b-2 border-ink pb-2 font-brand text-[15px] font-bold">Refina tu búsqueda</h2>

      {GRUPOS.filter((g) => mostrarGrupo(g.key)).map((g) => (
        <div key={g.key} className="border-b border-line-2 py-3">
          <button onClick={() => setAbiertos({ ...abiertos, [g.key]: !abiertos[g.key] })} className="flex w-full items-center justify-between">
            <span className="kicker text-[11px]">{g.titulo}</span><Chevron dir={abiertos[g.key] ? "up" : "down"} size={16} />
          </button>
          {abiertos[g.key] && (
            <ul className="mt-3 space-y-[7px]">
              {(facetas[g.key as string] || []).slice(0, g.key === "color" ? 24 : 40).map((f) => {
                const on = sel[g.key].includes(f.valor);
                return (
                  <li key={f.valor}>
                    <button onClick={() => toggle(g.key as string, f.valor)} className="flex w-full items-center gap-[10px] text-left font-sans text-[12px] hover:text-ink">
                      {g.key === "color"
                        ? <span className="swatch !h-[11px] !w-[11px]" data-sel={on} style={{ background: f.hex }} />
                        : <span className="cb !h-[15px] !w-[15px] text-[10px]" data-on={on}>{on && "✓"}</span>}
                      <span className={on ? "font-medium" : "text-ink-2"}>{g.key === "color" ? capital(f.valor) : g.key === "talle" ? `Talle ${f.valor}` : f.valor}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ))}

      <div className="border-b border-line-2 py-3">
        <button onClick={() => setAbiertos({ ...abiertos, precio: !abiertos.precio })} className="flex w-full items-center justify-between">
          <span className="kicker text-[11px]">Precio</span><Chevron dir={abiertos.precio ? "up" : "down"} size={16} />
        </button>
        {abiertos.precio !== false && (
          <form onSubmit={(e) => { e.preventDefault(); navegar((u) => { if (pmin) u.set("precio_min", pmin); else u.delete("precio_min"); if (pmax) u.set("precio_max", pmax); else u.delete("precio_max"); }); }}
            className="mt-3 grid grid-cols-[1fr_1fr_28px] gap-2">
            <label className="font-sans text-[11px]">Desde<input value={pmin} onChange={(e) => setPmin(e.target.value.replace(/\D/g, ""))} placeholder={rango.min ? `$${Math.round(rango.min)}` : "$"} className="input mt-1 !px-2 !py-[6px] !text-[12px]" /></label>
            <label className="font-sans text-[11px]">Hasta<input value={pmax} onChange={(e) => setPmax(e.target.value.replace(/\D/g, ""))} placeholder={rango.max ? `$${Math.round(rango.max)}` : "$"} className="input mt-1 !px-2 !py-[6px] !text-[12px]" /></label>
            <button type="submit" className="mt-auto flex h-[31px] items-center justify-center rounded-sm bg-[#bdbdbd] text-white hover:bg-ink" aria-label="Aplicar precio"><Chevron size={16} /></button>
          </form>
        )}
      </div>

      <div className="border-b border-line-2 py-3">
        <span className="kicker text-[11px]">Tipo de publicación</span>
        <ul className="mt-3 space-y-[7px] font-sans text-[12px]">
          <li><button onClick={() => navegar((u) => sel.solo_foto ? u.set("solo_foto", "0") : u.delete("solo_foto"))} className="flex items-center gap-[10px]"><span className="cb !h-[15px] !w-[15px] text-[10px]" data-on={sel.solo_foto}>{sel.solo_foto && "✓"}</span>Sólo con foto</button></li>
          <li><button onClick={() => navegar((u) => sel.solo_desc ? u.delete("solo_desc") : u.set("solo_desc", "1"))} className="flex items-center gap-[10px]"><span className="cb !h-[15px] !w-[15px] text-[10px]" data-on={sel.solo_desc}>{sel.solo_desc && "✓"}</span>Sólo ofertas</button></li>
        </ul>
      </div>
    </aside>
  );
}
