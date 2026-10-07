"use client";
import Link from "next/link";
import { useState } from "react";
import type { Card } from "@/lib/types";
import { money } from "@/lib/format";
import { CameraIcon, Chevron } from "./Brand";

export function Ribbon({ pct }: { pct: number }) {
  if (!pct) return null;
  return <span className={`ribbon ${pct <= 10 ? "ribbon-yellow" : "ribbon-red"}`}>{Math.round(pct)}%<br />OFF</span>;
}

export function Swatches({ colores, sel, onSel, size = 13 }: { colores: Card["colores"]; sel: string | null; onSel?: (c: string) => void; size?: number }) {
  return (
    <div className="flex flex-wrap items-center gap-[7px]">
      {colores.slice(0, 8).map((c) => (
        <button key={c.color} type="button" title={c.color} onMouseEnter={() => onSel?.(c.color)} onClick={() => onSel?.(c.color)}
          className="swatch" data-sel={sel === c.color} style={{ background: c.hex, width: size, height: size }} aria-label={c.color} />
      ))}
      {colores.length > 8 && <span className="font-sans text-[10px] text-muted">+{colores.length - 8}</span>}
    </div>
  );
}

export default function ProductCard({ p, abierta, onCargar, onGaleria, puedePedir = true }: {
  p: Card; abierta?: boolean; onCargar?: (cod: string) => void; onGaleria?: (cod: string) => void; puedePedir?: boolean;
}) {
  const [colorSel, setColorSel] = useState<string | null>(p.colores[0]?.color ?? null);
  const sw = p.colores.find((c) => c.color === colorSel);
  const foto = sw?.foto || p.foto;
  return (
    <article className={`relative flex h-full flex-col bg-white p-[14px] ${abierta ? "outline outline-2 outline-ink" : ""}`}>
      <Ribbon pct={p.pct_desc} />
      <button type="button" onClick={() => onGaleria?.(p.producto_cod)} className="absolute left-3 top-3 z-10 text-faint hover:text-ink" aria-label="Ver fotos">
        <CameraIcon />
      </button>
      <Link href={`/p/${p.producto_cod}`} className="block aspect-square w-full overflow-hidden bg-white">
        {foto ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={foto} alt={p.nombre} loading="lazy" className="h-full w-full object-contain transition-transform duration-300 hover:scale-[1.03]" />
        ) : (
          <div className="flex h-full w-full items-center justify-center font-sans text-[12px] text-faint">Sin foto</div>
        )}
      </Link>
      <div className="mt-3 flex items-center justify-between gap-2">
        <Swatches colores={p.colores} sel={colorSel} onSel={setColorSel} />
        <span className="truncate font-sans text-[10.5px] text-muted">{colorSel ? capital(colorSel) : ""}</span>
      </div>
      <h3 className="mt-2 card-title"><Link href={`/p/${p.producto_cod}`}>{p.nombre}</Link></h3>
      <p className="card-meta mt-[3px]"><b>{p.producto_cod}</b> · {p.marca} · {p.rubro}</p>
      <div className="mt-3 flex items-baseline gap-2">
        {p.pct_desc > 0 && p.precio_lista ? <span className="price-old">{money(p.precio_lista)}</span> : null}
        <span className="price">{money(p.precio)}</span>
      </div>
      <div className="mt-auto pt-3">
        {puedePedir && onCargar ? (
          <button type="button" onClick={() => onCargar(p.producto_cod)} className="btn btn-primary w-full justify-between !py-[10px]">
            <span>Cargar cantidades</span><Chevron size={15} />
          </button>
        ) : (
          <Link href={`/p/${p.producto_cod}`} className="btn btn-light w-full justify-between !py-[10px]"><span>Ver producto</span><Chevron size={15} /></Link>
        )}
      </div>
    </article>
  );
}

export function capital(s: string) {
  return s.toLowerCase().replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase());
}
