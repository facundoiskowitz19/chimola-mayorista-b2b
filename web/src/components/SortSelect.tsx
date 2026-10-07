"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const OPCIONES = [
  ["destacados", "Lo nuevo primero"],
  ["precio_asc", "Menor precio"],
  ["precio_desc", "Mayor precio"],
  ["nombre", "Nombre A–Z"],
];

export default function SortSelect({ orden }: { orden: string }) {
  const router = useRouter(); const path = usePathname(); const sp = useSearchParams();
  return (
    <label className="flex items-center gap-2 font-sans text-[12px] font-bold">
      Ordenar por:
      <select value={orden} onChange={(e) => { const u = new URLSearchParams(sp.toString()); u.set("orden", e.target.value); router.push(`${path}?${u}`); }}
        className="rounded-sm border border-line-2 bg-white px-2 py-[6px] font-normal outline-none">
        {OPCIONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}
