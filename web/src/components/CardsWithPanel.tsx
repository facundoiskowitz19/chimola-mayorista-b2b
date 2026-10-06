"use client";
/* Grilla o fila de cards con el panel "Cargar cantidades" que se abre debajo de la fila. */
import { useCallback, useState } from "react";
import type { Card, HomeBloque } from "@/lib/types";
import ProductCard from "./ProductCard";
import InlinePanel from "./InlinePanel";
import GalleryModal from "./GalleryModal";
import { Chevron } from "./Brand";
import Link from "next/link";

export function BannerGrilla({ b }: { b: HomeBloque }) {
  return (
    <div className="relative col-span-full h-[82px] overflow-hidden bg-[#7f8fb1]">
      {b.img && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={b.img} alt="" className="absolute inset-0 h-full w-full object-cover" />
      )}
      <div className="absolute inset-0 flex items-center justify-between px-6">
        <span className="rounded-full bg-white px-2 py-[2px] font-brand text-[8px] font-bold uppercase">New!</span>
        <div className="text-center font-brand font-bold text-white drop-shadow"><span className="text-[11px]">{b.subtitulo}</span><br /><span className="text-[22px] uppercase leading-none">{b.titulo}</span></div>
        {b.link && <Link href={b.link} className="btn btn-light btn-sm">{b.cta || "Ver productos"} <Chevron size={14} /></Link>}
      </div>
    </div>
  );
}

export default function CardsWithPanel({ items, cols = 3, puedePedir = true, banner, bannerDespuesDeFila = 2 }: {
  items: Card[]; cols?: 3 | 4; puedePedir?: boolean; banner?: HomeBloque | null; bannerDespuesDeFila?: number;
}) {
  const [abierta, setAbierta] = useState<string | null>(null);
  const [galeria, setGaleria] = useState<string | null>(null);
  const cerrar = useCallback(() => setAbierta(null), []);
  const cerrarGal = useCallback(() => setGaleria(null), []);

  const filas: Card[][] = [];
  for (let i = 0; i < items.length; i += cols) filas.push(items.slice(i, i + cols));
  const gridCls = cols === 4 ? "grid-cols-2 md:grid-cols-4" : "grid-cols-2 md:grid-cols-3";

  return (
    <>
      <div className={`grid ${gridCls} gap-[18px]`}>
        {filas.map((fila, fi) => (
          <FilaFragment key={fi} fila={fila} abierta={abierta} setAbierta={setAbierta} setGaleria={setGaleria} puedePedir={puedePedir}
            cerrar={cerrar} banner={banner && fi === bannerDespuesDeFila - 1 ? banner : null} />
        ))}
      </div>
      {galeria && <GalleryModal cod={galeria} onClose={cerrarGal} />}
    </>
  );
}

function FilaFragment({ fila, abierta, setAbierta, setGaleria, puedePedir, cerrar, banner }: {
  fila: Card[]; abierta: string | null; setAbierta: (c: string | null) => void; setGaleria: (c: string) => void;
  puedePedir: boolean; cerrar: () => void; banner: HomeBloque | null;
}) {
  const abiertaAca = fila.some((c) => c.producto_cod === abierta);
  return (
    <>
      {fila.map((p) => (
        <ProductCard key={p.producto_cod} p={p} abierta={abierta === p.producto_cod} puedePedir={puedePedir}
          onCargar={(cod) => setAbierta(abierta === cod ? null : cod)} onGaleria={setGaleria} />
      ))}
      {abiertaAca && abierta && <InlinePanel key={abierta} cod={abierta} onClose={cerrar} onGaleria={setGaleria} />}
      {banner && <BannerGrilla b={banner} />}
    </>
  );
}
