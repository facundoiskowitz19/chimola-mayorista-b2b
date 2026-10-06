"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import type { Card } from "@/lib/types";
import { money } from "@/lib/format";
import { Chimola, Lima, SearchIcon, XIcon } from "./Brand";

interface Res { nombres: string[]; productos: Card[]; total?: number }

export default function SearchBox() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Res | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(async () => {
      try { setRes(await api<Res>(`/buscar?q=${encodeURIComponent(q.trim())}`)); setOpen(true); } catch { /* ignorar */ }
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function ir(texto: string) {
    setOpen(false);
    router.push(`/c/todo?q=${encodeURIComponent(texto)}`);
  }

  return (
    <div ref={box} className="relative z-[70]">
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) ir(q.trim()); }}
        className={`flex h-[42px] w-[230px] items-center gap-2 bg-white pl-5 pr-3 md:w-[290px] ${open && res ? "rounded-t-[21px]" : "rounded-full"}`}>
        <input value={q} onChange={(e) => { setQ(e.target.value); if (e.target.value.trim().length < 2) { setRes(null); setOpen(false); } }} onFocus={() => res && setOpen(true)}
          placeholder="Encontrá lo que buscás" className="w-full bg-transparent font-sans text-[13.5px] outline-none placeholder:text-faint" />
        {q ? <button type="button" onClick={() => { setQ(""); setRes(null); setOpen(false); }} aria-label="Limpiar"><XIcon size={16} /></button> : null}
        <button type="submit" aria-label="Buscar" className="text-ink"><SearchIcon /></button>
      </form>
      {open && res && (
        <div className="fade-in absolute right-0 top-full z-[70] w-[290px] overflow-hidden rounded-b-[18px] bg-white shadow-xl">
          {res.nombres.map((n) => (
            <button key={n} onClick={() => ir(n)} className="block w-full border-t border-line px-6 py-[10px] text-left font-sans text-[13.5px] text-ink-2 hover:bg-[#f5f5f5]">{n}</button>
          ))}
          {res.productos.map((p) => (
            <Link key={p.producto_cod} href={`/p/${p.producto_cod}`} onClick={() => setOpen(false)}
              className="flex items-center gap-4 border-t border-line px-6 py-3 hover:bg-[#f5f5f5]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.foto || ""} alt="" className="h-[64px] w-[64px] rounded-sm bg-white object-contain" />
              <div className="min-w-0">
                {p.marca === "Lima" ? <Lima className="text-[12px]" /> : <Chimola className="text-[12px]" />}
                <div className="truncate font-sans text-[13px]">{p.nombre}</div>
                <div className="price text-[13px]">{money(p.precio)}</div>
              </div>
            </Link>
          ))}
          {res.nombres.length === 0 && res.productos.length === 0 && <div className="px-6 py-4 font-sans text-[13px] text-muted">Sin resultados</div>}
        </div>
      )}
    </div>
  );
}
