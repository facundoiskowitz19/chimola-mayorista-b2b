"use client";
/* Popup de imágenes (ícono de cámara en la card). */
import { useEffect, useState } from "react";
import type { Producto } from "@/lib/types";
import { api } from "@/lib/client";
import { Chevron, Chimola, Lima, XIcon } from "./Brand";
import { Swatches, capital } from "./ProductCard";

export default function GalleryModal({ cod, onClose }: { cod: string; onClose: () => void }) {
  const [p, setP] = useState<Producto | null>(null);
  const [idx, setIdx] = useState(0);
  const [color, setColor] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    api<Producto>(`/productos/${cod}`).then((d) => vivo && setP(d)).catch(() => vivo && setErr("No se pudieron cargar las fotos."));
    return () => { vivo = false; };
  }, [cod]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // En captura y frenando el evento: si el popup se abrió desde el panel inline, Esc cierra solo el popup.
        e.stopImmediatePropagation();
        onClose();
        return;
      }
      if (!p) return;
      if (e.key === "ArrowRight") setIdx((i) => (i + 1) % p.fotos.length);
      if (e.key === "ArrowLeft") setIdx((i) => (i - 1 + p.fotos.length) % p.fotos.length);
    };
    window.addEventListener("keydown", onKey, true);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey, true); document.body.style.overflow = ""; };
  }, [p, onClose]);

  function elegirColor(c: string) {
    setColor(c);
    if (!p) return;
    const sw = p.colores.find((x) => x.color === c);
    const i = p.fotos.findIndex((f) => sw?.foto && f.url === sw.foto);
    if (i >= 0) setIdx(i);
  }

  const fotos = p?.fotos ?? [];
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/55 p-4" onClick={onClose}>
      <div className="fade-in relative w-[min(1120px,96vw)] bg-white px-10 pb-8 pt-7" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute right-6 top-6" aria-label="Cerrar"><XIcon size={26} /></button>
        {p && (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 pr-10">
            {p.marca === "Lima" ? <Lima className="text-[26px]" /> : <Chimola className="text-[28px]" />}
            <div>
              <div className="font-brand text-[17px] font-bold leading-tight">{p.producto_nombre}</div>
              <div className="card-meta"><b>{p.producto_cod}</b> · {p.marca} · {p.rubro}</div>
            </div>
            {p.medidas && <div className="hidden items-center gap-2 border-l border-line pl-6 font-sans text-[13px] md:flex"><b>Medidas:</b> {p.medidas}</div>}
            <div className="ml-auto flex items-center gap-3 border-l border-line pl-6 font-sans text-[13px]">
              <b>Variantes:</b> <Swatches colores={p.colores} sel={color} onSel={elegirColor} size={16} />
              <span className="text-muted">{color ? capital(color) : ""}</span>
            </div>
          </div>
        )}
        <div className="relative mt-5 flex h-[min(58vh,560px)] items-center justify-center">
          {fotos[idx] ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={fotos[idx].url} alt="" className="max-h-full max-w-full object-contain" />
          ) : err ? <p className="font-sans text-[13px] text-[#aa0b56]">{err}</p>
          : p ? <p className="font-sans text-[13px] text-muted">Sin fotos</p>
          : <div className="h-full w-full animate-pulse bg-[#f1f1f1]" />}
          {fotos.length > 1 && (
            <>
              <button onClick={() => setIdx((idx - 1 + fotos.length) % fotos.length)} className="absolute left-0 top-1/2 -translate-y-1/2 text-line-2 hover:text-ink" aria-label="Anterior"><Chevron dir="left" size={44} /></button>
              <button onClick={() => setIdx((idx + 1) % fotos.length)} className="absolute right-0 top-1/2 -translate-y-1/2 text-line-2 hover:text-ink" aria-label="Siguiente"><Chevron size={44} /></button>
            </>
          )}
        </div>
        {fotos.length > 1 && (
          <div className="no-scrollbar mt-5 flex justify-center gap-4 overflow-x-auto">
            {fotos.map((f, i) => (
              <button key={f.filename} onClick={() => setIdx(i)} className={`shrink-0 border-b-[3px] pb-2 ${i === idx ? "border-ink" : "border-transparent"}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={f.url} alt="" className="h-[64px] w-[64px] object-contain" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
