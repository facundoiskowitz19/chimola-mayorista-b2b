"use client";
/* Un tipo de producto (rubro de Aleph) en el admin: productos, mover a otro tipo, traer productos y banner. */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ClientError } from "@/lib/client";
import type { HomeBloque } from "@/lib/types";
import { useToast } from "@/components/Toast";
import Thumb from "@/components/Thumb";
import { H1, Kicker, Muted, Panel, Pills, Spinner } from "./ui";
import BloqueForm from "./BloqueForm";

interface Item { producto_cod: string; nombre: string; categoria: string; marca: string; stock: number; publicado: boolean | null; origen: "aleph" | "manual"; rubro_aleph: string | null; foto: string | null }
interface Res { rubro: string; categoria: string | null; items: Item[]; n: number; opciones_rubro: string[] }
interface Banners { banners: Record<string, HomeBloque | null>; secciones: Record<string, string> }

export default function TipoAdmin({ rubro, categoria }: { rubro: string; categoria: string | null }) {
  const [d, setD] = useState<Res | null>(null);
  const [bans, setBans] = useState<Banners | null>(null);
  const [sec, setSec] = useState("marro");
  const secRef = useRef<string | null>(null);   // sección elegida; null = todavía no se cargó (se elige la inicial una sola vez)
  const [ban, setBan] = useState<HomeBloque | null>(null);
  const elegirSec = (k: string, b: Record<string, HomeBloque | null>) => { secRef.current = k; setSec(k); setBan(b[k]); };
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ producto_cod: string; nombre: string; foto: string | null; rubro: string }[]>([]);
  const [mover, setMover] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    const [d0, b0] = await Promise.all([
      api<Res>(`/admin/tipos/${encodeURIComponent(rubro)}${categoria ? `?categoria=${encodeURIComponent(categoria)}` : ""}`),
      api<Banners>(`/admin/tipos/${encodeURIComponent(rubro)}/banner`),
    ]);
    setD(d0); setBans(b0);
    // La sección inicial se calcula solo en la primera carga; después de guardar/quitar se queda en la que estaba.
    const sec0 = secRef.current || (["marro", "indu", "lima"] as const).find((k) => b0.banners[k]) || (categoria === "Indumentaria" || categoria === "Pijamas" || d0.items.some((i) => i.categoria === "Indumentaria") ? "indu" : d0.items.length && d0.items.every((i) => i.marca === "Lima") ? "lima" : "marro");
    elegirSec(sec0, b0.banners);
  }, [rubro, categoria]);
  useEffect(() => { secRef.current = null; cargar(); }, [cargar]);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const t = setTimeout(async () => {
      const r = await api<{ items: { producto_cod: string; nombre: string; foto: string | null; rubro: string }[] }>(`/admin/catalogo?q=${encodeURIComponent(q.trim())}&per_page=8`);
      setRes(r.items);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function accion(fn: () => Promise<void>, ok: string) {
    setBusy(true);
    try { await fn(); notify(ok); await cargar(); } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  if (!d || !bans) return <><Link href="/admin/categorias" className="font-sans text-[12px] text-muted hover:text-ink">← Categorías</Link><H1>{rubro}</H1><Spinner /></>;
  const ya = new Set(d.items.map((i) => i.producto_cod));
  return (
    <>
      <Link href={categoria ? `/admin/categorias/${encodeURIComponent(categoria)}` : "/admin/categorias"} className="font-sans text-[12px] text-muted hover:text-ink">← {categoria || "Categorías"}</Link>
      <H1 right={<Link href={`/c/${sec}?rubro=${encodeURIComponent(rubro)}${categoria ? `&categoria=${encodeURIComponent(categoria)}` : ""}`} target="_blank" className="btn btn-light btn-sm">Ver en el sitio ›</Link>}>{rubro}{categoria && <span className="ml-2 font-sans text-[14px] font-normal text-muted">en {categoria}</span>}</H1>
      <Muted className="-mt-3">{d.n} productos. El tipo de producto viene de Aleph; cada producto tiene uno solo. Desde acá podés <b>mover</b> un producto a otro tipo o <b>traer</b> uno que esté mal clasificado. Volver a Aleph deshace el cambio.</Muted>

      <Panel className="mt-5">
        <Kicker>Banner del tipo (arriba del catálogo)</Kicker>
        <Muted className="mt-1">Lo ve el cliente al entrar a «{rubro}» desde el menú o los filtros. Por sección del header.</Muted>
        <div className="mt-3"><Pills value={sec} onChange={(k) => elegirSec(k, bans.banners)} options={Object.entries(bans.secciones).map(([k, n]) => ({ value: k, label: n + (bans.banners[k] ? " ·" : "") }))} /></div>
        <div className="mt-3">
          {ban ? (
            <>
              <BloqueForm b={ban} onChange={setBan} conKicker previewAspect="1125/300" />
              <div className="mt-3 flex gap-2">
                <button disabled={busy} onClick={() => { if (!ban.img && !ban.titulo?.trim()) { notify("El banner necesita una imagen o un título", "error"); return; } accion(async () => { await api(`/admin/tipos/${encodeURIComponent(rubro)}/banner`, { method: "PUT", json: { seccion: sec, banner: ban } }); }, "Banner guardado"); }} className="btn btn-primary btn-sm">{busy ? "Guardando…" : "Guardar banner"}</button>
                <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/tipos/${encodeURIComponent(rubro)}/banner`, { method: "PUT", json: { seccion: sec, banner: null } }); }, "Banner quitado")} className="btn btn-ghost btn-sm text-[#aa0b56]">Quitar banner</button>
                <button disabled={busy} onClick={() => setBan(bans.banners[sec])} className="btn btn-light btn-sm">Descartar cambios</button>
              </div>
            </>
          ) : <button onClick={() => setBan({ img: "", titulo: rubro, kicker: categoria || "", cta: "Ver productos", link: `/c/${sec}?rubro=${encodeURIComponent(rubro)}` })} className="btn btn-light btn-sm">+ Crear banner para {bans.secciones[sec]}</button>}
        </div>
      </Panel>

      <Panel className="mt-4">
        <div className="relative">
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Traer un producto a «${rubro}»: buscá por código o nombre…`} />
          {q.trim().length >= 2 && res.length > 0 && (
            <div className="absolute z-20 mt-1 w-full border border-line bg-white shadow-lg">
              {res.map((r) => (
                <button key={r.producto_cod} type="button" disabled={busy || ya.has(r.producto_cod)} onClick={() => accion(async () => { await api(`/admin/tipos/${encodeURIComponent(rubro)}/productos`, { method: "POST", json: { producto_cod: r.producto_cod } }); setQ(""); setRes([]); }, `${r.producto_cod} movido a ${rubro}`)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left font-sans text-[12.5px] hover:bg-[#f5f5f5] disabled:opacity-40">
                  <Thumb src={r.foto} className="h-[32px] w-[32px] object-contain" /><b>{r.producto_cod}</b> {r.nombre}<span className="ml-auto text-muted">{ya.has(r.producto_cod) ? "ya está" : `hoy: ${r.rubro}`}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </Panel>

      <Panel className="mt-4 !p-0">
        <table className="w-full font-sans text-[13px]">
          <thead><tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-4 py-3" colSpan={2}>Producto</th><th className="py-3">Categoría</th><th className="py-3">Origen</th><th className="py-3 pr-6 text-right">Stock</th><th className="py-3">Publicación</th><th className="w-56" /></tr></thead>
          <tbody>
            {d.items.map((i) => (
              <tr key={i.producto_cod} className="border-b border-line hover:bg-[#fafafa]">
                <td className="w-[56px] px-4 py-2"><Thumb src={i.foto} className="h-[44px] w-[44px] object-contain" /></td>
                <td className="py-2"><Link href={`/admin/catalogo/${i.producto_cod}`} className="font-bold hover:underline">{i.nombre}</Link><div className="card-meta"><b>{i.producto_cod}</b> · {i.marca}</div></td>
                <td className="py-2">{i.categoria}</td>
                <td className={`py-2 ${i.origen === "manual" ? "text-[#006786]" : "text-muted"}`}>{i.origen === "manual" ? <>manual <span className="text-muted">· Aleph: {i.rubro_aleph}</span></> : "Aleph"}</td>
                <td className="py-2 pr-6 text-right">{i.stock}</td>
                <td className="py-2">{i.publicado === false ? <span className="text-[#aa0b56]">Oculto</span> : i.publicado === true ? "Publicado" : <span className="text-muted">Automático</span>}</td>
                <td className="py-2 pr-4 text-right">
                  {mover === i.producto_cod ? (
                    <span className="inline-flex items-center gap-1">
                      <select className="input !w-[170px] !py-1 !text-[12px]" defaultValue="" onChange={(e) => { const v = e.target.value; if (!v) return; accion(async () => { await api(`/admin/productos/${i.producto_cod}/rubro`, { method: "PUT", json: { rubro: v === "__aleph__" ? null : v } }); setMover(null); }, v === "__aleph__" ? `${i.producto_cod} vuelve al tipo de Aleph` : `${i.producto_cod} → ${v}`); }}>
                        <option value="">Mover a…</option>
                        {i.origen === "manual" && <option value="__aleph__">Volver a Aleph ({i.rubro_aleph})</option>}
                        {d.opciones_rubro.filter((r) => r !== rubro).map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                      <button onClick={() => setMover(null)} className="text-faint hover:text-ink">×</button>
                    </span>
                  ) : <button disabled={busy} onClick={() => setMover(i.producto_cod)} className="font-sans text-[12px] hover:underline">Mover / quitar</button>}
                </td>
              </tr>
            ))}
            {d.items.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-muted">Sin productos.</td></tr>}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
