"use client";
/* Una temporada (colección de Aleph) vista como una categoría más: sus productos, acciones en lote y banner por sección. */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ClientError } from "@/lib/client";
import type { HomeBloque } from "@/lib/types";
import { useToast } from "@/components/Toast";
import Thumb from "@/components/Thumb";
import { Check, H1, Kicker, Muted, Panel, Pills, Spinner } from "./ui";
import BloqueForm from "./BloqueForm";
import LoteBar from "./LoteBar";

interface Item { producto_cod: string; nombre: string; categoria: string; rubro: string; marca: string; stock: number; publicado: boolean | null; destacado: boolean; editado: boolean; sin_foto: boolean; foto: string | null }
interface Res { temporada: string; items: Item[]; n: number; opciones_categoria: string[]; opciones_rubro: string[] }
interface Banners { banners: Record<string, HomeBloque | null>; secciones: Record<string, string> }

export default function TemporadaAdmin({ valor }: { valor: string }) {
  const [d, setD] = useState<Res | null>(null);
  const [bans, setBans] = useState<Banners | null>(null);
  const [sec, setSec] = useState("marro");
  const secRef = useRef<string | null>(null);
  const [ban, setBan] = useState<HomeBloque | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [soloSinFoto, setSoloSinFoto] = useState(false);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const elegirSec = (k: string, b: Record<string, HomeBloque | null>) => { secRef.current = k; setSec(k); setBan(b[k]); };

  const cargar = useCallback(async () => {
    const [d0, b0] = await Promise.all([api<Res>(`/admin/temporadas/${encodeURIComponent(valor)}`), api<Banners>(`/admin/temporadas/${encodeURIComponent(valor)}/banner`)]);
    setD(d0); setBans(b0);
    const sec0 = secRef.current || (["marro", "indu", "lima"] as const).find((k) => b0.banners[k])
      || (d0.items.length && d0.items.every((i) => i.marca === "Lima") ? "lima" : d0.items.length && d0.items.every((i) => i.categoria === "Indumentaria" || i.categoria === "Pijamas") ? "indu" : "marro");
    elegirSec(sec0, b0.banners);
  }, [valor]);
  useEffect(() => { secRef.current = null; cargar(); }, [cargar]);

  async function guardarBanner(v: HomeBloque | null) {
    if (v && !v.img && !v.titulo?.trim()) { notify("El banner necesita una imagen o un título", "error"); return; }
    setBusy(true);
    try { await api(`/admin/temporadas/${encodeURIComponent(valor)}/banner`, { method: "PUT", json: { seccion: sec, banner: v } }); notify(v ? "Banner de la temporada guardado" : "Banner quitado"); await cargar(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  if (!d || !bans) return <><Link href="/admin/categorias" className="font-sans text-[12px] text-muted hover:text-ink">← Categorías</Link><H1>{valor}</H1><Spinner /></>;
  const items = soloSinFoto ? d.items.filter((i) => i.sin_foto) : d.items;
  const sinFoto = d.items.filter((i) => i.sin_foto).length;
  const todosSel = items.length > 0 && items.every((i) => sel.has(i.producto_cod));
  return (
    <>
      <Link href="/admin/categorias" className="font-sans text-[12px] text-muted hover:text-ink">← Categorías</Link>
      <H1 right={<Link href={`/c/${sec}?temporada=${encodeURIComponent(valor)}`} target="_blank" className="btn btn-light btn-sm">Ver en el sitio ›</Link>}>{valor}<span className="ml-2 font-sans text-[14px] font-normal text-muted">temporada</span></H1>
      <Muted className="-mt-3">{d.n} productos{sinFoto > 0 && <>, <b className="text-[#aa0b56]">{sinFoto} sin foto</b> (no se muestran en la grilla del cliente)</>}. La temporada viene de Aleph y no se edita; desde acá podés ocultar, destacar o reclasificar sus productos en lote y ponerle un banner. El nombre que ve el cliente en el menú se cambia en <Link href="/admin/menu" className="underline">Menú</Link>.</Muted>

      <Panel className="mt-5">
        <Kicker>Banner de la temporada (arriba del catálogo)</Kicker>
        <Muted className="mt-1">Lo ve el cliente al entrar a «{valor}» desde el menú. Por sección del header.</Muted>
        <div className="mt-3"><Pills value={sec} onChange={(k) => elegirSec(k, bans.banners)} options={Object.entries(bans.secciones).map(([k, n]) => ({ value: k, label: n + (bans.banners[k] ? " ·" : "") }))} /></div>
        <div className="mt-3">
          {ban ? (
            <>
              <BloqueForm b={ban} onChange={setBan} conKicker previewAspect="1125/300" sugerido="1600 × 420 px" />
              <div className="mt-3 flex gap-2">
                <button disabled={busy} onClick={() => guardarBanner(ban)} className="btn btn-primary btn-sm">{busy ? "Guardando…" : "Guardar banner"}</button>
                <button disabled={busy} onClick={() => guardarBanner(null)} className="btn btn-ghost btn-sm text-[#aa0b56]">Quitar banner</button>
                <button disabled={busy} onClick={() => setBan(bans.banners[sec])} className="btn btn-light btn-sm">Descartar cambios</button>
              </div>
            </>
          ) : <button onClick={() => setBan({ img: "", titulo: valor, kicker: "", cta: "Ver productos", link: `/c/${sec}?temporada=${encodeURIComponent(valor)}` })} className="btn btn-light btn-sm">+ Crear banner para {bans.secciones[sec]}</button>}
        </div>
      </Panel>

      <LoteBar sel={sel} todos={items.map((i) => i.producto_cod)} onDone={async () => { setSel(new Set()); await cargar(); }} onClear={() => setSel(new Set())}
        opcionesCategoria={d.opciones_categoria} opcionesRubro={d.opciones_rubro} />

      <Panel className="mt-4 !p-0">
        <div className="flex items-center justify-between px-4 py-2"><Check checked={soloSinFoto} onChange={setSoloSinFoto} label="Solo sin foto" /><span className="font-sans text-[12px] text-muted">{items.length} productos</span></div>
        <table className="w-full font-sans text-[13px]">
          <thead><tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-3 py-3"><Check checked={todosSel} onChange={(v) => setSel(v ? new Set(items.map((i) => i.producto_cod)) : new Set())} /></th><th className="py-3" colSpan={2}>Producto</th><th className="py-3">Categoría / tipo</th><th className="py-3 pr-6 text-right">Stock</th><th className="py-3">Publicación</th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.producto_cod} className={`border-b border-line hover:bg-[#fafafa] ${sel.has(i.producto_cod) ? "bg-[#f3fbff]" : ""}`}>
                <td className="px-3 py-2"><Check checked={sel.has(i.producto_cod)} onChange={(v) => { const s = new Set(sel); if (v) s.add(i.producto_cod); else s.delete(i.producto_cod); setSel(s); }} /></td>
                <td className="w-[56px] py-2"><Thumb src={i.foto} className="h-[44px] w-[44px] object-contain" /></td>
                <td className="py-2"><Link href={`/admin/catalogo/${i.producto_cod}`} className="font-bold hover:underline">{i.nombre}</Link><div className="card-meta"><b>{i.producto_cod}</b> · {i.marca}{i.destacado && <span className="ml-2 text-ink">★ destacado</span>}{i.sin_foto && <span className="ml-2 text-[#aa0b56]">sin foto</span>}{i.editado && <span className="ml-2 text-[#006786]">editado</span>}</div></td>
                <td className="py-2"><Link href={`/admin/categorias/${encodeURIComponent(i.categoria)}`} className="hover:underline">{i.categoria}</Link> <span className="text-muted">/</span> <Link href={`/admin/tipos/${encodeURIComponent(i.rubro)}`} className="hover:underline">{i.rubro}</Link></td>
                <td className="py-2 pr-6 text-right">{i.stock}</td>
                <td className="py-2">{i.publicado === false ? <span className="text-[#aa0b56]">Oculto</span> : i.publicado === true ? "Publicado" : <span className="text-muted">Automático</span>}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-muted">Sin productos.</td></tr>}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
