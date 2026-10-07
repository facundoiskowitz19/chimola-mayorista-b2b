"use client";
/* Una categoría del admin: sus productos (de Aleph, reclasificados o agregados) y alta/baja de productos. */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import Thumb from "@/components/Thumb";
import { H1, Kicker, Muted, Panel, Pills, Spinner } from "./ui";
import BloqueForm from "./BloqueForm";
import type { HomeBloque } from "@/lib/types";

interface Item { producto_cod: string; nombre: string; rubro: string; marca: string; stock: number; publicado: boolean | null; origen: "aleph" | "manual" | "extra"; categoria_principal: string; foto: string | null }
interface Res { categoria: string; items: Item[]; n: number }

const ORIGEN = { aleph: { l: "Aleph", cls: "text-muted" }, manual: { l: "principal (manual)", cls: "text-[#006786]" }, extra: { l: "adicional", cls: "text-[#006786]" } };

export default function CategoriaAdmin({ nombre }: { nombre: string }) {
  const [d, setD] = useState<Res | null>(null);
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ producto_cod: string; nombre: string; foto: string | null }[]>([]);
  const [busy, setBusy] = useState(false);
  const [banners, setBanners] = useState<{ banners: Record<string, HomeBloque | null>; secciones: Record<string, string> } | null>(null);
  const [sec, setSec] = useState<string>("marro");
  const [ban, setBan] = useState<HomeBloque | null>(null);
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    const [d0, b0] = await Promise.all([api<Res>(`/admin/categorias/${encodeURIComponent(nombre)}`), api<{ banners: Record<string, HomeBloque | null>; secciones: Record<string, string> }>(`/admin/categorias/${encodeURIComponent(nombre)}/banner`)]);
    setD(d0); setBanners(b0);
    const primera = (["marro", "indu", "lima"] as const).find((k) => b0.banners[k]) || (d0.items.some((i) => i.marca === "Lima") && !d0.items.some((i) => i.marca === "Chimola") ? "lima" : (nombre === "Indumentaria" || nombre === "Pijamas") ? "indu" : "marro");
    setSec(primera); setBan(b0.banners[primera]);
  }, [nombre]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(async () => {
      const r = await api<{ items: { producto_cod: string; nombre: string; foto: string | null }[] }>(`/admin/catalogo?q=${encodeURIComponent(q.trim())}&per_page=8`);
      setRes(r.items);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function agregar(cod: string) {
    setBusy(true);
    try { await api(`/admin/categorias/${encodeURIComponent(nombre)}/productos`, { method: "POST", json: { producto_cod: cod } }); notify(`${cod} agregado a ${nombre}`); setQ(""); setRes([]); await cargar(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }
  async function quitar(cod: string) {
    setBusy(true);
    try { await api(`/admin/categorias/${encodeURIComponent(nombre)}/productos/${cod}`, { method: "DELETE" }); notify(`${cod} quitado de ${nombre}`); await cargar(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  async function guardarBanner(valor: HomeBloque | null) {
    setBusy(true);
    try { await api(`/admin/categorias/${encodeURIComponent(nombre)}/banner`, { method: "PUT", json: { seccion: sec, banner: valor } }); notify(valor ? "Banner de la categoría guardado" : "Banner quitado"); await cargar(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  if (!d) return <><Link href="/admin/categorias" className="font-sans text-[12px] text-muted hover:text-ink">← Categorías</Link><H1>{nombre}</H1><Spinner /></>;
  const ya = new Set(d.items.map((i) => i.producto_cod));
  return (
    <>
      <Link href="/admin/categorias" className="font-sans text-[12px] text-muted hover:text-ink">← Categorías</Link>
      <H1 right={<Link href={`/c/todo?categoria=${encodeURIComponent(nombre)}`} target="_blank" className="btn btn-light btn-sm">Ver en el sitio ›</Link>}>{nombre}</H1>
      <Muted className="-mt-3">{d.n} productos. Un producto puede estar en varias categorías: la <b>principal</b> viene de Aleph (o la cambiás en su ficha) y las <b>adicionales</b> las sumás acá. Quitar desde acá solo saca las adicionales.</Muted>

      <Panel className="mt-5">
        <div className="relative">
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Agregar producto a esta categoría: buscá por código o nombre…" />
          {q.trim().length >= 2 && res.length > 0 && (
            <div className="absolute z-20 mt-1 w-full border border-line bg-white shadow-lg">
              {res.map((r) => (
                <button key={r.producto_cod} type="button" disabled={busy || ya.has(r.producto_cod)} onClick={() => agregar(r.producto_cod)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left font-sans text-[12.5px] hover:bg-[#f5f5f5] disabled:opacity-40">
                  <Thumb src={r.foto} className="h-[32px] w-[32px] object-contain" /><b>{r.producto_cod}</b> {r.nombre}{ya.has(r.producto_cod) && <span className="ml-auto text-muted">ya está</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </Panel>

      {banners && (
        <Panel className="mt-4">
          <Kicker>Banner de la categoría (arriba del catálogo)</Kicker>
          <Muted className="mt-1">Lo ve el cliente al entrar a esta categoría desde el menú, un bloque de la home o el rail. Es por sección del header: elegí en cuál aplica (una categoría puede tener productos en más de una). Imagen ideal 1600×420.</Muted>
          <div className="mt-3"><Pills value={sec} onChange={(k) => { setSec(k); setBan(banners.banners[k]); }} options={Object.entries(banners.secciones).map(([k, n]) => ({ value: k, label: n + (banners.banners[k] ? " ·" : "") }))} /></div>
          <div className="mt-3">
            {ban ? (
              <>
                <BloqueForm b={ban} onChange={setBan} conKicker previewAspect="1125/300" />
                <div className="mt-3 flex gap-2">
                  <button disabled={busy} onClick={() => guardarBanner(ban)} className="btn btn-primary btn-sm">{busy ? "Guardando…" : "Guardar banner"}</button>
                  <button disabled={busy} onClick={() => guardarBanner(null)} className="btn btn-ghost btn-sm text-[#aa0b56]">Quitar banner</button>
                  <button disabled={busy} onClick={() => setBan(banners.banners[sec])} className="btn btn-light btn-sm">Descartar cambios</button>
                </div>
              </>
            ) : (
              <button onClick={() => setBan({ img: "", titulo: nombre, kicker: "", cta: "Ver productos", link: `/c/${sec}?categoria=${encodeURIComponent(nombre)}` })} className="btn btn-light btn-sm">+ Crear banner para {banners.secciones[sec]}</button>
            )}
          </div>
        </Panel>
      )}

      <Panel className="mt-4 !p-0">
        <table className="w-full font-sans text-[13px]">
          <thead><tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-4 py-3" colSpan={2}>Producto</th><th className="py-3">Tipo</th><th className="py-3">Pertenencia</th><th className="py-3 pr-6 text-right">Stock</th><th className="py-3">Publicación</th><th className="w-20" /></tr></thead>
          <tbody>
            {d.items.map((i) => (
              <tr key={i.producto_cod} className="border-b border-line hover:bg-[#fafafa]">
                <td className="w-[56px] px-4 py-2"><Thumb src={i.foto} className="h-[44px] w-[44px] object-contain" /></td>
                <td className="py-2"><Link href={`/admin/catalogo/${i.producto_cod}`} className="font-bold hover:underline">{i.nombre}</Link><div className="card-meta"><b>{i.producto_cod}</b> · {i.marca}</div></td>
                <td className="py-2"><Link href={`/admin/tipos/${encodeURIComponent(i.rubro)}?categoria=${encodeURIComponent(nombre)}`} className="hover:underline">{i.rubro}</Link></td>
                <td className={`py-2 ${ORIGEN[i.origen].cls}`}>{ORIGEN[i.origen].l}{i.origen === "extra" && <span className="text-muted"> · principal: {i.categoria_principal}</span>}</td>
                <td className="py-2 pr-6 text-right">{i.stock}</td>
                <td className="py-2">{i.publicado === false ? <span className="text-[#aa0b56]">Oculto</span> : i.publicado === true ? "Publicado" : <span className="text-muted">Automático</span>}</td>
                <td className="py-2 pr-4 text-right">{i.origen === "extra" && <button disabled={busy} onClick={() => quitar(i.producto_cod)} className="font-sans text-[12px] text-[#aa0b56] hover:underline">Quitar</button>}</td>
              </tr>
            ))}
            {d.items.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-muted">Esta categoría todavía no tiene productos. Agregá con el buscador de arriba.</td></tr>}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
