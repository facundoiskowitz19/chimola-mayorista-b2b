"use client";
/* Grilla del catálogo con scroll infinito (carga la página siguiente al acercarse al final). */
import { useEffect, useRef, useState } from "react";
import type { Catalogo, Card, HomeBloque } from "@/lib/types";
import { api } from "@/lib/client";
import CardsWithPanel from "./CardsWithPanel";

export default function CatalogGrid({ inicial, query, puedePedir, banner = null }: { inicial: Catalogo; query: string; puedePedir: boolean; banner?: HomeBloque | null }) {
  const [items, setItems] = useState<Card[]>(inicial.items);
  const [page, setPage] = useState(inicial.page);
  const [busy, setBusy] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const hayMas = page < inicial.pages;

  async function cargarMas() {
    if (busy || !hayMas) return;
    setBusy(true);
    try {
      const q = query.replace(/page=\d+/, `page=${page + 1}`);
      const d = await api<Catalogo>(`/catalogo?${q}`);
      setItems((x) => [...x, ...d.items.filter((n) => !x.some((e) => e.producto_cod === n.producto_cod))]);
      setPage(d.page);
    } finally { setBusy(false); }
  }

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hayMas) return;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) cargarMas(); }, { rootMargin: "700px" });
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, hayMas, busy]);

  if (!items.length) {
    return <div className="rounded bg-white p-10 text-center font-sans text-[14px] text-muted">No encontramos productos con esos filtros.</div>;
  }
  return (
    <div>
      <CardsWithPanel items={items} cols={3} puedePedir={puedePedir} banner={banner} />
      <div ref={sentinel} className="h-px" />
      <div className="mt-8 flex flex-col items-center gap-2">
        <span className="font-sans text-[12px] text-muted">Viste {items.length} de {inicial.total}</span>
        {hayMas && <button onClick={cargarMas} disabled={busy} className="btn btn-light">{busy ? "Cargando…" : "Mostrar más"}</button>}
      </div>
    </div>
  );
}
