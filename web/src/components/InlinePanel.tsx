"use client";
/* Panel "Cargar cantidades" que se abre debajo de la fila de cards. */
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Producto } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { CameraIcon, Chevron, XIcon } from "./Brand";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import VariantPicker, { esMatriz, type Cants } from "./VariantPicker";

export default function InlinePanel({ cod, onClose, onGaleria }: { cod: string; onClose: () => void; onGaleria?: (cod: string) => void }) {
  const [p, setP] = useState<Producto | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cants, setCants] = useState<Cants>({});
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const { agregar } = useCart();
  const { notify } = useToast();

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
      if (c.avisos.length) c.avisos.forEach((a) => notify(a, "aviso"));
      notify(`Agregaste ${c.agregadas ?? 0} unidades de ${p.producto_nombre} al carrito.`);
      onClose();
    } catch (e) {
      notify(e instanceof ClientError ? e.message : "No se pudo agregar", "error");
    } finally { setBusy(false); }
  }

  const fotos = p?.fotos ?? [];
  const foto = fotos[idx]?.url;

  return (
    <div className="fade-in relative col-span-full bg-white px-8 pb-8 pt-5 outline outline-1 outline-line-2">
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
              {p.descripcion && <p className="mt-3 font-sans text-[12px] leading-snug text-ink-2">{p.descripcion}</p>}
            </div>
            <div className="min-w-0"><VariantPicker p={p} cants={cants} setCants={setCants} onAgregar={onAgregar} busy={busy} /></div>
          </div>
          {p.relacionados.length > 0 && (
            <div className="mt-8 border-t border-line pt-6">
              <h4 className="text-center font-brand text-[13px] font-bold">Otros productos {p.familia ? <>&ldquo;{p.familia}&rdquo;</> : "relacionados"} que te pueden interesar:</h4>
              <div className="mt-5 flex flex-wrap justify-center gap-6">
                {p.relacionados.slice(0, 4).map((r) => (
                  <Link key={r.producto_cod} href={`/p/${r.producto_cod}`} className="w-[150px] text-center">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={r.foto || ""} alt={r.nombre} className="mx-auto h-[120px] w-[120px] object-contain" />
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

