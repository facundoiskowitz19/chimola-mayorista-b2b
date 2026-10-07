"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import type { Producto } from "@/lib/types";
import { ClientError } from "@/lib/client";
import { fichaDesdeDescripcion, money } from "@/lib/format";
import { Chevron } from "./Brand";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import VariantPicker, { type Cants } from "./VariantPicker";
import { Ribbon } from "./ProductCard";
import GalleryModal from "./GalleryModal";
import ProductRow from "./ProductRow";

export default function Ficha({ p, puedePedir }: { p: Producto; puedePedir: boolean }) {
  const [idx, setIdx] = useState(0);
  const [desdeThumb, setDesdeThumb] = useState(0);
  const [cants, setCants] = useState<Cants>({});
  const [busy, setBusy] = useState(false);
  const [gal, setGal] = useState(false);
  const { agregar } = useCart();
  const { notify } = useToast();
  const cerrarGal = useCallback(() => setGal(false), []);
  const fotos = p.fotos;
  const THUMBS = 4;

  async function onAgregar() {
    const items = Object.entries(cants).filter(([, n]) => n > 0).map(([sku, cantidad]) => ({ sku, cantidad }));
    if (!items.length) return;
    setBusy(true);
    try {
      const c = await agregar(items);
      c.avisos.forEach((a) => notify(a, "aviso"));
      notify(`Agregaste ${c.agregadas ?? 0} unidades al carrito.`);
      setCants({});
    } catch (e) { notify(e instanceof ClientError ? e.message : "No se pudo agregar", "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className="container-lt pb-10 pt-8">
      <nav className="font-sans text-[12px] text-muted">
        <Link href={`/h/${p.seccion}`} className="hover:text-ink">{p.marca === "Lima" ? "LIMA" : p.categoria}</Link> › <Link href={`/c/${p.seccion}?rubro=${encodeURIComponent(p.rubro)}`} className="hover:text-ink">{p.rubro}</Link> › <span className="text-ink">{p.producto_nombre}</span>
      </nav>
      <div className="mt-6 grid gap-10 lg:grid-cols-[460px_minmax(0,1fr)]">
        <div>
          <div className="relative aspect-square w-full bg-white">
            <Ribbon pct={p.pct_desc} />
            {fotos[idx] ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={fotos[idx].url} alt={p.producto_nombre} onClick={() => setGal(true)} className="h-full w-full cursor-zoom-in object-contain" />
            ) : <div className="flex h-full items-center justify-center text-faint">Sin foto</div>}
            {fotos.length > 1 && (
              <>
                <button onClick={() => setIdx((idx - 1 + fotos.length) % fotos.length)} className="absolute left-1 top-1/2 -translate-y-1/2 text-line-2 hover:text-ink" aria-label="Anterior"><Chevron dir="left" size={40} /></button>
                <button onClick={() => setIdx((idx + 1) % fotos.length)} className="absolute right-1 top-1/2 -translate-y-1/2 text-line-2 hover:text-ink" aria-label="Siguiente"><Chevron size={40} /></button>
              </>
            )}
          </div>
          {fotos.length > 1 && (
            <div className="mt-4 flex items-center gap-2">
              <button onClick={() => setDesdeThumb(Math.max(0, desdeThumb - THUMBS))} disabled={desdeThumb === 0} className="text-line-2 hover:text-ink disabled:opacity-30" aria-label="Anteriores"><Chevron dir="left" size={28} /></button>
              <div className="grid flex-1 grid-cols-4 gap-3">
                {fotos.slice(desdeThumb, desdeThumb + THUMBS).map((f, k) => {
                  const i = desdeThumb + k;
                  return (
                    <button key={f.filename} onClick={() => setIdx(i)} className={`border-b-[3px] bg-white p-1 pb-2 ${i === idx ? "border-ink" : "border-transparent"}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={f.url} alt="" className="aspect-square w-full object-contain" />
                    </button>
                  );
                })}
              </div>
              <button onClick={() => setDesdeThumb(desdeThumb + THUMBS)} disabled={desdeThumb + THUMBS >= fotos.length} className="text-line-2 hover:text-ink disabled:opacity-30" aria-label="Siguientes"><Chevron size={28} /></button>
            </div>
          )}
        </div>
        <div>
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="font-brand text-[32px] font-extrabold leading-tight">{p.producto_nombre}</h1>
              <p className="card-meta mt-1 text-[12px]"><b>{p.producto_cod}</b> · {p.marca} · {p.temporada} · {p.rubro}</p>
            </div>
            <div className="text-right">
              {p.pct_desc > 0 && p.precio_lista ? <div className="price-old">{money(p.precio_lista)}</div> : null}
              <div className="font-brand text-[20px] font-bold">{money(p.precio)}</div>
              {p.pct_desc > 0 && <div className="font-brand text-[11px] font-bold text-red">{Math.round(p.pct_desc)}% OFF</div>}
            </div>
          </div>
          {(() => { const f0 = fichaDesdeDescripcion(p.descripcion); const f = { ...f0, corto: p.descripcion_corta || f0.corto, medidas: p.medidas || f0.medidas, materiales: p.materiales || f0.materiales }; return (
            <div className="mt-5">
              {f.corto && <p className="font-brand text-[16px] font-bold leading-snug">{f.corto}</p>}
              <dl className="mt-4 space-y-1 font-sans text-[12px]">
                {f.medidas && <div><dt className="inline font-bold">Medidas: </dt><dd className="inline">{f.medidas}</dd></div>}
                {f.materiales && <div><dt className="inline font-bold">Materiales: </dt><dd className="inline">{f.materiales}</dd></div>}
                {p.ub && p.ub > 1 && <div><dt className="inline font-bold">Unidad de bulto: </dt><dd className="inline">{p.ub} u.</dd></div>}
              </dl>
              {f.completa && f.completa.length > f.corto.length + 20 && (
                <details className="mt-3"><summary className="cursor-pointer font-sans text-[12px] text-muted hover:text-ink">Ver descripción completa</summary><p className="mt-2 font-sans text-[13px] leading-relaxed text-ink-2">{f.completa}</p></details>
              )}
            </div>
          ); })()}
          <div className="mt-8">
            {puedePedir ? (
              <VariantPicker p={p} cants={cants} setCants={setCants} onAgregar={onAgregar} busy={busy} />
            ) : (
              <table className="vt"><thead><tr><th>Variante</th><th>Talles</th></tr></thead>
                <tbody>{p.colores.map((c) => <tr key={c.color}><td><span className="inline-flex items-center gap-2"><span className="swatch" style={{ background: c.hex }} />{c.color}</span></td><td>{p.variantes.filter((v) => v.color === c.color).map((v) => v.talle).join(" · ")}</td></tr>)}</tbody></table>
            )}
          </div>
        </div>
      </div>
      {p.relacionados.length > 0 && <ProductRow titulo="Productos relacionados que te pueden interesar" items={p.relacionados} puedePedir={puedePedir} />}
      {gal && <GalleryModal cod={p.producto_cod} onClose={cerrarGal} />}
    </div>
  );
}
