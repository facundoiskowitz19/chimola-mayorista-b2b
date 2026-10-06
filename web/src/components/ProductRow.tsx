"use client";
/* Fila de 4 cards con flechas (secciones curadas de la home) + panel inline debajo. */
import Link from "next/link";
import { useCallback, useState } from "react";
import type { Card } from "@/lib/types";
import ProductCard from "./ProductCard";
import InlinePanel from "./InlinePanel";
import GalleryModal from "./GalleryModal";
import { Chevron } from "./Brand";

export default function ProductRow({ titulo, link, items, puedePedir = true }: { titulo: string; link?: string | null; items: Card[]; puedePedir?: boolean }) {
  const [desde, setDesde] = useState(0);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [galeria, setGaleria] = useState<string | null>(null);
  const cerrar = useCallback(() => setAbierta(null), []);
  const cerrarGal = useCallback(() => setGaleria(null), []);
  const VIS = 4;
  const visibles = items.slice(desde, desde + VIS);
  const puedeIzq = desde > 0, puedeDer = desde + VIS < items.length;

  if (!items.length) return null;
  return (
    <section className="relative mt-14">
      <div className="mb-5 flex items-end justify-between border-t-2 border-line-2 pt-7">
        <h2 className="font-brand text-[22px] font-bold">{titulo}</h2>
        {link && <Link href={link} className="whitespace-nowrap font-brand text-[12.5px] font-bold hover:underline">Ver todo <Chevron size={13} /></Link>}
      </div>
      <div className="relative">
        {puedeIzq && <button onClick={() => setDesde(Math.max(0, desde - VIS))} className="absolute -left-12 top-[150px] hidden text-ink-2 hover:text-ink lg:block" aria-label="Anterior"><Chevron dir="left" size={40} /></button>}
        {puedeDer && <button onClick={() => setDesde(desde + VIS)} className="absolute -right-12 top-[150px] hidden text-ink-2 hover:text-ink lg:block" aria-label="Siguiente"><Chevron size={40} /></button>}
        <div className="grid grid-cols-2 gap-[18px] md:grid-cols-4">
          {visibles.map((p) => (
            <ProductCard key={p.producto_cod} p={p} abierta={abierta === p.producto_cod} puedePedir={puedePedir}
              onCargar={(cod) => setAbierta(abierta === cod ? null : cod)} onGaleria={setGaleria} />
          ))}
          {abierta && visibles.some((c) => c.producto_cod === abierta) && <InlinePanel key={abierta} cod={abierta} onClose={cerrar} onGaleria={setGaleria} />}
        </div>
      </div>
      {galeria && <GalleryModal cod={galeria} onClose={cerrarGal} />}
    </section>
  );
}
