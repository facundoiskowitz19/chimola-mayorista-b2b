"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, ClientError, qs } from "@/lib/client";
import { money } from "@/lib/format";
import { useToast } from "@/components/Toast";
import Thumb from "@/components/Thumb";
import { Check, Confirm, H1, Muted, Panel, Pills, Spinner } from "@/components/admin/ui";

interface Item { producto_cod: string; nombre: string; marca: string; temporada: string; rubro: string; categoria: string; stock: number; variantes: number; precio1: number | null; publicado: boolean | null; publicacion: string; destacado: boolean; sin_foto: boolean; editado: boolean; foto: string | null }
interface Res { total: number; page: number; pages: number; items: Item[]; counts: Record<string, number>; cods_filtrados: string[]; facetas: Record<string, string[]> }
type Pill = "todos" | "publicados" | "ocultos" | "destacados" | "sin_foto" | "con_override";
const PILLS: { value: Pill; label: string }[] = [
  { value: "todos", label: "Todos" }, { value: "publicados", label: "Publicados" }, { value: "ocultos", label: "Ocultos" },
  { value: "destacados", label: "Destacados" }, { value: "sin_foto", label: "Sin foto" }, { value: "con_override", label: "Con override" },
];
const LOTES: { label: string; campos: Record<string, boolean | null>; desc: string }[] = [
  { label: "Ocultar", campos: { publicado: false }, desc: "OCULTAR" },
  { label: "Volver a automático", campos: { publicado: null }, desc: "volver a publicación AUTOMÁTICA" },
  { label: "Destacar", campos: { destacado: true }, desc: "DESTACAR" },
  { label: "Quitar destacado", campos: { destacado: false }, desc: "quitar el destacado a" },
];

export default function Page() {
  return <Suspense fallback={<Spinner />}><CatalogoAdmin /></Suspense>;
}

function CatalogoAdmin() {
  const sp = useSearchParams(); const router = useRouter();
  const { notify } = useToast();
  const [q, setQ] = useState(sp.get("q") || "");
  const [pill, setPill] = useState<Pill>((sp.get("pill") as Pill) || "todos");
  const [f, setF] = useState<Record<string, string>>({ marca: "", temporada: "", categoria: "", rubro: "" });
  const [page, setPage] = useState(1);
  const [res, setRes] = useState<Res | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<{ cods: string[]; campos: Record<string, boolean | null>; desc: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [fotomap, setFotomap] = useState<{ rows: { producto_cod: string; sku: string; color: string; talle: string; foto: string | null; origen: string }[]; counts: Record<string, number>; n: number } | null>(null);

  const query = useCallback((p = page) => qs({ q, pill, page: p, per_page: 50, marca: f.marca || undefined, temporada: f.temporada || undefined, categoria: f.categoria || undefined, rubro: f.rubro || undefined }), [q, pill, page, f]);

  const cargar = useCallback(async () => {
    const d = await api<Res>(`/admin/catalogo${query()}`);
    setRes(d);
  }, [query]);

  useEffect(() => { const t = setTimeout(cargar, 250); return () => clearTimeout(t); }, [cargar]);
  useEffect(() => { setPage(1); setSel(new Set()); }, [q, pill, f]);

  async function aplicar(cods: string[], campos: Record<string, boolean | null>, desc: string, confirmado = false) {
    // Solo el «Sí» del Confirm pasa confirmado=true: otro botón con un Confirm pendiente vuelve a pedir confirmación.
    if (cods.length > 10 && !confirmado) { setConfirm({ cods, campos, desc }); return; }
    setBusy(true);
    try {
      const r = await api<{ n: number }>("/admin/catalogo/lote", { method: "POST", json: { cods, campos } });
      notify(`Listo: ${r.n} producto(s) actualizados.`);
      setConfirm(null); setSel(new Set());
      await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  async function generarFotomap() {
    setFotomap(await api(`/admin/catalogo/fotomap${qs({ q, pill, marca: f.marca || undefined, temporada: f.temporada || undefined, categoria: f.categoria || undefined, rubro: f.rubro || undefined })}`));
  }
  function csvFotomap() {
    if (!fotomap) return;
    const head = "producto_cod,sku,color,talle,foto,origen";
    const body = fotomap.rows.map((r) => [r.producto_cod, r.sku, r.color, r.talle, r.foto || "", r.origen].map((x) => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([head + "\n" + body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "fotos_variantes.csv"; a.click();
  }

  const todosSel = res ? res.items.every((i) => sel.has(i.producto_cod)) && res.items.length > 0 : false;

  return (
    <>
      <H1>Catálogo</H1>
      <Muted>Click en un producto abre su ficha. Marcá casillas para las acciones en lote; «sobre todo lo filtrado» aplica al conjunto completo del filtro, no solo a la página.</Muted>
      <div className="mt-4 grid gap-2 md:grid-cols-[1.6fr_1fr_1fr_1fr_1fr]">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar código o nombre" className="input" />
        {(["marca", "temporada", "categoria", "rubro"] as const).map((k) => (
          <select key={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="input">
            <option value="">{k === "rubro" ? "Tipo de producto" : k[0].toUpperCase() + k.slice(1)}: todos</option>
            {(res?.facetas[k] || []).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        ))}
      </div>
      <div className="mt-3"><Pills value={pill} onChange={(p) => { setPill(p); router.replace(`/admin/catalogo?pill=${p}`); }} options={PILLS.map((p) => ({ ...p, n: res?.counts[p.value] }))} /></div>

      {sel.size > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border border-[#006786] bg-[#e9f8ff] px-4 py-3">
          <b className="mr-2 font-sans text-[13px] text-[#006786]">{sel.size} seleccionado(s)</b>
          {sel.size === 1 && <Link href={`/admin/catalogo/${[...sel][0]}`} className="btn btn-light btn-sm">Editar</Link>}
          {LOTES.map((l) => <button key={l.label} onClick={() => aplicar([...sel], l.campos, l.desc)} disabled={busy} className="btn btn-light btn-sm">{l.label}</button>)}
          <button onClick={() => setSel(new Set())} className="btn btn-ghost btn-sm">Deseleccionar</button>
          <span className="ml-auto font-sans text-[11px] text-muted">se aplican al instante</span>
        </div>
      )}
      {confirm && (
        <div className="mt-3"><Confirm busy={busy} texto={<>Vas a <b>{confirm.desc}</b> {confirm.cods.length} productos. ¿Seguro?</>} onYes={() => aplicar(confirm.cods, confirm.campos, confirm.desc, true)} onNo={() => setConfirm(null)} /></div>
      )}

      {!res ? <div className="mt-4"><Spinner /></div> : (
        <Panel className="mt-4 !p-0">
          <table className="w-full font-sans text-[13px]">
            <thead>
              <tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2">
                <th className="px-3 py-3"><Check checked={todosSel} onChange={(v) => setSel(v ? new Set(res.items.map((i) => i.producto_cod)) : new Set())} /></th>
                <th className="py-3" colSpan={2}>Producto</th><th className="py-3">Marca · Temp.</th><th className="py-3">Publicación</th>
                <th className="py-3 text-right">Stock</th><th className="py-3 text-right">Var.</th><th className="py-3 text-right">Precio L1</th><th className="py-3 text-center">Override</th>
              </tr>
            </thead>
            <tbody>
              {res.items.map((i) => (
                <tr key={i.producto_cod} className={`border-b border-line hover:bg-[#fafafa] ${sel.has(i.producto_cod) ? "bg-[#f3fbff]" : ""}`}>
                  <td className="px-3 py-2"><Check checked={sel.has(i.producto_cod)} onChange={(v) => { const s = new Set(sel); if (v) s.add(i.producto_cod); else s.delete(i.producto_cod); setSel(s); }} /></td>
                  <td className="w-[56px] py-2"><Thumb src={i.foto} className="h-[44px] w-[44px] object-contain" /></td>
                  <td className="py-2"><Link href={`/admin/catalogo/${i.producto_cod}`} className="font-bold hover:underline">{i.nombre}</Link><div className="card-meta"><b>{i.producto_cod}</b> · {i.rubro}{i.destacado && <span className="ml-2 text-ink">★ destacado</span>}{i.sin_foto && <span className="ml-2 text-[#aa0b56]">sin foto</span>}</div></td>
                  <td className="py-2 text-muted">{i.marca} · {i.temporada}</td>
                  <td className="py-2">{i.publicado === false ? <span className="text-[#aa0b56]">Oculto</span> : i.publicado === true ? "Publicado" : <span className="text-muted">Automático</span>}</td>
                  <td className="py-2 text-right">{i.stock}</td><td className="py-2 text-right">{i.variantes}</td>
                  <td className="py-2 text-right">{i.precio1 ? money(i.precio1) : <span className="text-[#aa0b56]">—</span>}</td>
                  <td className="py-2 text-center">{i.editado && <span className="font-semibold text-[#006786]">editado</span>}</td>
                </tr>
              ))}
              {res.items.length === 0 && <tr><td colSpan={9} className="p-8 text-center text-muted">Sin productos con ese filtro.</td></tr>}
            </tbody>
          </table>
          <div className="flex items-center justify-between px-4 py-3 font-sans text-[12px] text-muted">
            <span>{res.total} productos · página {res.page} de {res.pages}</span>
            <span className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="btn btn-light btn-sm disabled:opacity-40">‹</button>
              <button disabled={page >= res.pages} onClick={() => setPage(page + 1)} className="btn btn-light btn-sm disabled:opacity-40">›</button>
            </span>
          </div>
        </Panel>
      )}

      {res && (
        <details className="mt-6 bg-white p-5">
          <summary className="cursor-pointer font-brand text-[14px] font-bold">Acciones masivas sobre todo lo filtrado ({res.total} productos)</summary>
          <Muted className="mt-2">Afecta a TODOS los productos del filtro actual, no solo a la página. Con más de 10 pide confirmación.</Muted>
          <div className="mt-3 flex flex-wrap gap-2">
            {LOTES.map((l) => <button key={l.label} onClick={() => aplicar(res.cods_filtrados, l.campos, l.desc)} disabled={busy || res.total === 0} className="btn btn-light btn-sm">{l.label} todo</button>)}
          </div>
        </details>
      )}
      <details className="mt-3 bg-white p-5">
        <summary className="cursor-pointer font-brand text-[14px] font-bold">Fotos ↔ variantes (auditoría)</summary>
        <Muted className="mt-2">Qué foto usa cada variante, sobre lo filtrado. Origen: <b>color</b> = detección automática · <b>manual</b> = asignada en la ficha · <b>portada</b> = sin foto propia del color · <b>sin_foto</b>.</Muted>
        <div className="mt-3 flex items-center gap-3">
          <button onClick={generarFotomap} className="btn btn-light btn-sm">Generar mapeo</button>
          {fotomap && <><span className="font-sans text-[12px] text-muted">{Object.entries(fotomap.counts).map(([k, v]) => `${k}: ${v}`).join(" · ")} · {fotomap.n} variantes</span><button onClick={csvFotomap} className="btn btn-primary btn-sm">Descargar CSV</button></>}
        </div>
        {fotomap && fotomap.rows.filter((r) => r.origen === "portada" || r.origen === "sin_foto").length > 0 && (
          <table className="mt-3 w-full font-sans text-[12px]"><thead><tr className="border-b border-ink text-left text-[11px] uppercase"><th className="py-1">Producto</th><th className="py-1">SKU</th><th className="py-1">Color</th><th className="py-1">Origen</th></tr></thead>
            <tbody>{fotomap.rows.filter((r) => r.origen === "portada" || r.origen === "sin_foto").slice(0, 50).map((r) => <tr key={r.sku} className="border-b border-line"><td className="py-1"><Link href={`/admin/catalogo/${r.producto_cod}`} className="hover:underline">{r.producto_cod}</Link></td><td className="py-1">{r.sku}</td><td className="py-1">{r.color}</td><td className="py-1 text-[#aa0b56]">{r.origen}</td></tr>)}</tbody></table>
        )}
      </details>
    </>
  );
}
