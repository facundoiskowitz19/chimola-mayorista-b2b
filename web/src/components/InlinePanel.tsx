"use client";
/* Panel "Cargar cantidades" que se abre debajo de la fila de cards. */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Producto } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { fichaDesdeDescripcion, money } from "@/lib/format";
import { CameraIcon, Chevron, XIcon } from "./Brand";
import Thumb from "./Thumb";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import VariantPicker, { esMatriz, type Cants } from "./VariantPicker";

function tituloRelacionados(p: Producto): string {
  const vis = p.relacionados.slice(0, 4);
  const fam = p.familia;
  const todosFamilia = !!fam && vis.length > 0 && vis.every((r) => new RegExp(`\\b${fam.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(r.nombre));
  return todosFamilia ? `Completá la línea “${fam}”:` : "Otros productos que te pueden interesar:";
}

export default function InlinePanel({ cod, onClose, onGaleria }: { cod: string; onClose: () => void; onGaleria?: (cod: string) => void }) {
  const [p, setP] = useState<Producto | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cants, setCants] = useState<Cants>({});
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const { agregar } = useCart();
  const { notify } = useToast();
  const ref = useRef<HTMLDivElement>(null);

  // Al abrirse debajo de la fila suele quedar fuera de la vista: lo traemos (sin tapar la card con el header fijo).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [p]);

  useEffect(() => {
    let vivo = true;
    api<Producto>(`/productos/${cod}`).then((d) => vivo && setP(d)).catch((e) => vivo && setErr(e.message));
    return () => { vivo = false; };
  }, [cod]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function onAgregar() {
    if (!p) return;
    const items = Object.entries(cants).filter(([, n]) => n > 0).map(([sku, cantidad]) => ({ sku, cantidad }));
    if (!items.length) return;
    setBusy(true);
    try {
      const c = await agregar(items);
      c.avisos.forEach((a) => notify(a, "aviso"));
      const n = c.agregadas ?? 0;
      if (n > 0) {
        notify(`Agregaste ${n} unidades de ${p.producto_nombre} al carrito.`);
        onClose();
      } else if (!c.avisos.length) notify("No se pudo agregar: sin disponibilidad para lo elegido.", "aviso");
    } catch (e) {
      notify(e instanceof ClientError ? e.message : "No se pudo agregar", "error");
    } finally { setBusy(false); }
  }

  const fotos = p?.fotos ?? [];
  const foto = fotos[idx]?.url;

  return (
    <div ref={ref} className="fade-in relative col-span-full bg-white px-8 pb-8 pt-5 outline outline-1 outline-line-2">
      <div className="flex items-center justify-between">
        <Link href={`/p/${cod}`} className="font-sans text-[12px] text-muted hover:text-ink">Ir a ficha de producto &gt;</Link>
        <button onClick={onClose} aria-label="Cerrar" className="text-ink"><XIcon size={22} /></button>
      </div>
      {err && <p className="mt-4 text-[13px] text-[#aa0b56]">{err}</p>}
      {!p && !err && <div className="mt-6 h-[260px] animate-pulse rounded bg-[#f1f1f1]" />}
      {p && (
        <>
          <div className="mt-2 flex flex-wrap items-start gap-x-4 gap-y-2">
            <button type="button" onClick={() => onGaleria?.(cod)} className="mt-1 text-faint hover:text-ink" aria-label="Ver fotos"><CameraIcon /></button>
            <div className="min-w-0 flex-1">
              <h3 className="font-brand text-[22px] font-bold leading-tight">{p.producto_nombre}</h3>
              <p className="card-meta mt-[2px]"><b>{p.producto_cod}</b> · {p.marca} {p.categoria} · {p.temporada} · {p.rubro}</p>
            </div>
            {(() => { const f0 = fichaDesdeDescripcion(p.descripcion); const f = { medidas: p.medidas || f0.medidas, materiales: p.materiales || f0.materiales }; return (f.medidas || f.materiales) ? (
              <div className="hidden max-w-[300px] font-sans text-[11px] leading-snug lg:block">
                {f.medidas && <div><b>Medidas:</b> {f.medidas}</div>}
                {f.materiales && <div><b>Materiales:</b> {f.materiales}</div>}
              </div>
            ) : null; })()}
            <div className="text-right">
              {p.pct_desc > 0 && p.precio_lista ? <div className="price-old">{money(p.precio_lista)}</div> : null}
              <div className="font-brand text-[18px] font-bold">{money(p.precio)}</div>
            </div>
          </div>
          <div className={`mt-5 grid gap-8 ${esMatriz(p) ? "lg:grid-cols-[260px_minmax(0,1fr)]" : "lg:grid-cols-[320px_minmax(0,1fr)]"}`}>
            <div>
              <div className="relative aspect-square w-full bg-white">
                {foto ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={foto} alt={p.producto_nombre} className="h-full w-full object-contain" />
                ) : <div className="flex h-full items-center justify-center text-faint">Sin foto</div>}
                {fotos.length > 1 && (
                  <>
                    <button onClick={() => setIdx((idx - 1 + fotos.length) % fotos.length)} className="absolute left-0 top-1/2 -translate-y-1/2 p-1 text-line-2 hover:text-ink" aria-label="Anterior"><Chevron dir="left" size={34} /></button>
                    <button onClick={() => setIdx((idx + 1) % fotos.length)} className="absolute right-0 top-1/2 -translate-y-1/2 p-1 text-line-2 hover:text-ink" aria-label="Siguiente"><Chevron size={34} /></button>
                  </>
                )}
              </div>
              {fotos.length > 1 && <p className="mt-1 text-center font-sans text-[11px] text-muted">{idx + 1} de {fotos.length}</p>}
            </div>
            <div className="min-w-0"><VariantPicker p={p} cants={cants} setCants={setCants} onAgregar={onAgregar} busy={busy} /></div>
          </div>
          {p.relacionados.length > 0 && (
            <div className="mt-8 border-t border-line pt-6">
              <h4 className="text-center font-brand text-[13px] font-bold">{tituloRelacionados(p)}</h4>
              <div className="mt-5 flex flex-wrap justify-center gap-6">
                {p.relacionados.slice(0, 4).map((r) => (
                  <Link key={r.producto_cod} href={`/p/${r.producto_cod}`} className="w-[150px] text-center">
                    <Thumb src={r.foto} alt={r.nombre} className="mx-auto h-[120px] w-[120px] object-contain" />
                    <div className="mt-2 font-brand text-[12px] font-bold leading-tight">{r.nombre}</div>
                    <div className="font-sans text-[12px]">{money(r.precio)}</div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

