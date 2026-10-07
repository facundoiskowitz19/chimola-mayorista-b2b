"use client";
/* Visualizador / selector de fotos: grilla de miniaturas clickeables. */
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Muted } from "./ui";

export interface Foto { filename: string; url: string }

export function FotoGrid({ fotos, value, onChange, size = 84, permitirNinguna = false }: {
  fotos: Foto[]; value: string | null; onChange: (f: Foto | null) => void; size?: number; permitirNinguna?: boolean;
}) {
  if (!fotos.length) return <Muted>Sin fotos.</Muted>;
  return (
    <div className="flex flex-wrap gap-2">
      {permitirNinguna && (
        <button type="button" onClick={() => onChange(null)} style={{ width: size, height: size }}
          className={`flex items-center justify-center rounded-sm border bg-white font-sans text-[11px] text-muted ${!value ? "border-ink ring-2 ring-ink" : "border-line"}`}>Automática</button>
      )}
      {fotos.map((f) => (
        <button key={f.filename} type="button" title={f.filename} onClick={() => onChange(f)} style={{ width: size, height: size }}
          className={`relative overflow-hidden rounded-sm border bg-white ${value === f.filename || value === f.url ? "border-ink ring-2 ring-ink" : "border-line hover:border-ink"}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={f.url} alt={f.filename} className="h-full w-full object-contain" />
        </button>
      ))}
    </div>
  );
}

interface ProductoFotos { producto_cod: string; efectivo: { nombre: string }; fotos: { files: string[]; urls: Record<string, string> } }

/* Buscar un producto y elegir una de sus fotos (devuelve la URL pública). */
export function FotoDeProducto({ onElegir, onCerrar }: { onElegir: (url: string) => void; onCerrar: () => void }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ producto_cod: string; nombre: string; foto: string | null }[]>([]);
  const [prod, setProd] = useState<ProductoFotos | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(async () => {
      const r = await api<{ items: { producto_cod: string; nombre: string; foto: string | null }[] }>(`/admin/catalogo?q=${encodeURIComponent(q.trim())}&per_page=8&solo_foto=1`);
      setRes(r.items.filter((i) => i.foto));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function abrir(cod: string) { setProd(await api<ProductoFotos>(`/admin/productos/${cod}`)); }

  const fotos: Foto[] = prod ? prod.fotos.files.map((fn) => ({ filename: fn, url: prod.fotos.urls[fn] })) : [];
  return (
    <div className="rounded border border-line bg-[#fafafa] p-3">
      <div className="flex items-center gap-2">
        <input className="input" autoFocus value={q} onChange={(e) => { setQ(e.target.value); setProd(null); }} placeholder="Buscar producto por código o nombre…" />
        <button type="button" onClick={onCerrar} className="btn btn-light btn-sm">Cerrar</button>
      </div>
      {!prod && res.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {res.map((r) => (
            <button key={r.producto_cod} type="button" onClick={() => abrir(r.producto_cod)} className="flex items-center gap-2 rounded-sm border border-line bg-white px-2 py-1 font-sans text-[12px] hover:border-ink">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={r.foto || ""} alt="" className="h-[28px] w-[28px] object-contain" /><b>{r.producto_cod}</b> {r.nombre}
            </button>
          ))}
        </div>
      )}
      {prod && (
        <div className="mt-3">
          <Muted className="mb-2"><b className="text-ink">{prod.producto_cod}</b> · {prod.efectivo.nombre} · {fotos.length} fotos — click para usar</Muted>
          <FotoGrid fotos={fotos} value={null} onChange={(f) => f && onElegir(f.url)} />
        </div>
      )}
    </div>
  );
}
