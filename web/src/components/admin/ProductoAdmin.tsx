"use client";
/* Ficha de producto del admin: VISTA (qué ve el cliente y de dónde sale) ↔ EDICIÓN (overrides). */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { useToast } from "@/components/Toast";
import { Check, Confirm, Field, H1, Kicker, Manual, Muted, Panel, Spinner } from "@/components/admin/ui";
import { FotoGrid } from "@/components/admin/FotoPicker";

interface Var { sku: string; color: string; talle: string; ean: string | null; stock: number; stock_aleph: number | null; precio1: number | null; es_manual: boolean; ov: { stock?: number; oculta?: boolean; precios?: Record<string, number> } }
interface Extra { color: string; talle: string; stock: number; precios: Record<string, number>; ean?: string }
interface Data {
  producto_cod: string;
  efectivo: { nombre: string; descripcion: string; marca: string; temporada: string; rubro: string; categoria: string; precios: Record<string, number | null> };
  aleph: { nombre: string; descripcion: string; precios: Record<string, number>; descvta: number };
  override: { publicado?: boolean | null; destacado?: boolean; nombre?: string; descripcion?: string; precios?: Record<string, number>; ub?: number; descuento_pct?: number | null; portada?: string; fotos_color?: Record<string, string>; variantes?: Record<string, Var["ov"]>; variantes_extra?: Record<string, Extra>; updated_by?: string; updated_at?: string | null; categoria?: string; rubro?: string; relacionados?: string[]; categorias_extra?: string[] };
  variantes: Var[];
  fotos: { files: string[]; n: number; portada_auto: string | null; portada: string | null; principal: string | null; urls: Record<string, string>; por_color: { color: string; auto: string | null; manual: string | null; norm: string }[] };
  colores: { color: string; hex: string }[];
  clasificacion: { categoria: string; rubro: string; categoria_aleph: string; rubro_aleph: string; opciones_categoria: string[]; opciones_rubro: string[] };
  relacionados: RelInfo[];
  relacionados_inversos: RelInfo[];
}
interface RelInfo { producto_cod: string; nombre: string; foto: string | null; en_catalogo: boolean }
interface Form {
  publicado: "auto" | "si" | "no"; destacado: boolean; ub: string; descuento_pct: string; nombre: string; descripcion: string;
  precios: Record<string, string>; variantes: Record<string, { stock: string; oculta: boolean; precio1: string }>;
  extras: Record<string, { color: string; talle: string; stock: string; precio: string; ean: string; quitar: boolean }>;
  fotos_color: Record<string, string>; portada: string;
  categoria: string; rubro: string; relacionados: RelInfo[]; categorias_extra: string[]; nuevaCat: string;
}

const PUB = [
  { v: "auto", l: "Automático", c: "Visible si tiene stock (lo decide Aleph)" },
  { v: "si", l: "Publicado", c: "Visible — igual exige stock > 0, nunca se vende sin stock" },
  { v: "no", l: "Oculto", c: "Nunca visible para clientes" },
] as const;

function formDe(d: Data): Form {
  const o = d.override;
  return {
    publicado: o.publicado === true ? "si" : o.publicado === false ? "no" : "auto",
    destacado: !!o.destacado, ub: o.ub ? String(o.ub) : "", descuento_pct: o.descuento_pct !== null && o.descuento_pct !== undefined ? String(o.descuento_pct) : "",
    nombre: o.nombre || "", descripcion: o.descripcion || "",
    precios: Object.fromEntries(["1", "2", "3", "4"].map((n) => [n, o.precios?.[n] ? String(o.precios[n]) : ""])),
    variantes: Object.fromEntries(d.variantes.filter((v) => !v.es_manual).map((v) => [v.sku, { stock: v.ov.stock !== undefined && v.ov.stock !== null ? String(v.ov.stock) : "", oculta: !!v.ov.oculta, precio1: v.ov.precios?.["1"] ? String(v.ov.precios["1"]) : "" }])),
    extras: Object.fromEntries(Object.entries(o.variantes_extra || {}).map(([sku, x]) => [sku, { color: x.color, talle: x.talle, stock: String(x.stock), precio: String(x.precios?.["1"] || ""), ean: x.ean || "", quitar: false }])),
    fotos_color: Object.fromEntries(d.fotos.por_color.map((c) => [c.norm, c.manual || ""])),
    portada: d.fotos.portada || "",
    categoria: o.categoria || "", rubro: o.rubro || "", relacionados: d.relacionados, categorias_extra: o.categorias_extra || [], nuevaCat: "",
  };
}

export default function ProductoAdmin({ cod }: { cod: string }) {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmQuitar, setConfirmQuitar] = useState(false);
  const [nuevaExtra, setNuevaExtra] = useState({ color: "", talle: "U", stock: "", precio: "", ean: "" });
  const [fcAbierto, setFcAbierto] = useState<string | null>(null);
  const [relQ, setRelQ] = useState("");
  const [relRes, setRelRes] = useState<{ producto_cod: string; nombre: string; foto: string | null }[]>([]);
  useEffect(() => {
    if (relQ.trim().length < 2) return;
    const t = setTimeout(async () => {
      const r = await api<{ items: { producto_cod: string; nombre: string; foto: string | null }[] }>(`/admin/catalogo?q=${encodeURIComponent(relQ.trim())}&per_page=8`);
      setRelRes(r.items.filter((i) => i.producto_cod !== cod));
    }, 250);
    return () => clearTimeout(t);
  }, [relQ, cod]);
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    try { const x = await api<Data>(`/admin/productos/${cod}`); setD(x); setF(formDe(x)); }
    catch (e) { setErr(e instanceof ClientError ? e.message : "Error"); }
  }, [cod]);
  useEffect(() => { cargar(); }, [cargar]);

  async function guardar() {
    if (!d || !f) return;
    setBusy(true);
    try {
      const variantes: Record<string, { stock?: number; oculta?: boolean; precios?: Record<string, number> }> = {};
      for (const [sku, v] of Object.entries(f.variantes)) {
        const o: { stock?: number; oculta?: boolean; precios?: Record<string, number> } = {};
        if (v.stock !== "") o.stock = parseInt(v.stock, 10);
        if (v.oculta) o.oculta = true;
        if (v.precio1 && parseFloat(v.precio1) > 0) o.precios = { "1": parseFloat(v.precio1) };
        if (Object.keys(o).length) variantes[sku] = o;
      }
      const extras: Record<string, Extra> = {};
      for (const [sku, x] of Object.entries(f.extras)) if (!x.quitar) extras[sku] = { color: x.color, talle: x.talle, stock: parseInt(x.stock || "0", 10), precios: { "1": parseFloat(x.precio || "0") }, ean: x.ean };
      await api(`/admin/productos/${cod}`, { method: "PUT", json: {
        nombre: f.nombre, descripcion: f.descripcion,
        precios: Object.fromEntries(Object.entries(f.precios).map(([k, v]) => [k, v ? parseFloat(v) : null])),
        publicado: f.publicado === "si" ? true : f.publicado === "no" ? false : null, destacado: f.destacado,
        ub: f.ub ? parseInt(f.ub, 10) : null, descuento_pct: f.descuento_pct === "" ? null : parseFloat(f.descuento_pct),
        portada: f.portada, fotos_color: Object.fromEntries(Object.entries(f.fotos_color).filter(([, v]) => v)),
        variantes, variantes_extra: Object.keys(d.override.variantes_extra || {}).length || Object.keys(extras).length ? extras : null,
        categoria: f.categoria || null, rubro: f.rubro || null, relacionados: f.relacionados.map((r) => r.producto_cod), categorias_extra: f.categorias_extra,
      } });
      notify(`${cod} guardado`); setEdit(false); await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  async function quitarTodo() {
    setBusy(true);
    try { await api(`/admin/productos/${cod}/overrides`, { method: "DELETE" }); notify(`${cod} volvió 100% a Aleph`); setEdit(false); setConfirmQuitar(false); await cargar(); }
    finally { setBusy(false); }
  }

  async function agregarExtra() {
    try {
      const r = await api<{ sku: string }>(`/admin/productos/${cod}/variantes-extra`, { method: "POST", json: { ...nuevaExtra, stock: parseInt(nuevaExtra.stock || "0", 10), precio: parseFloat(nuevaExtra.precio || "0") } });
      notify(`Variante manual ${r.sku} agregada`); setNuevaExtra({ color: "", talle: "U", stock: "", precio: "", ean: "" }); await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
  }

  if (err) return <><H1>{cod}</H1><p className="text-[#aa0b56]">{err}</p><Link href="/admin/catalogo" className="btn btn-light mt-4">← Catálogo</Link></>;
  if (!d || !f) return <Spinner />;
  const o = d.override;
  const hex = (c: string) => d.colores.find((x) => x.color === c)?.hex;

  return (
    <>
      <Link href="/admin/catalogo" className="font-sans text-[12px] text-muted hover:text-ink">← Catálogo</Link>
      <H1 right={!edit ? <button onClick={() => { setF(formDe(d)); setEdit(true); }} className="btn btn-primary">Editar</button> : null}>{d.efectivo.nombre}</H1>
      <Muted className="-mt-3 mb-5"><b className="text-ink">{cod}</b> · {d.efectivo.marca} · {d.efectivo.temporada} · {d.efectivo.categoria} / {d.efectivo.rubro}{o.updated_by && <> · overrides por {o.updated_by}</>}</Muted>

      {!edit ? <Vista d={d} hex={hex} /> : (
        <>
          <Muted><b className="text-ink">Nada se aplica hasta tocar Guardar</b>. Descartar vuelve a la vista sin cambios. Única excepción: «Agregar variante manual», que se aplica al instante.</Muted>
          <div className="mt-4 grid gap-6 lg:grid-cols-[260px_1fr]">
            <Panel>
              {d.fotos.principal && /* eslint-disable-next-line @next/next/no-img-element */ <img src={d.fotos.principal} alt="" className="mb-4 aspect-square w-full object-contain" />}
              <Kicker>Publicación</Kicker>
              <div className="mt-2 space-y-2">
                {PUB.map((p) => <button key={p.v} type="button" onClick={() => setF({ ...f, publicado: p.v })} className="flex w-full items-start gap-2 text-left"><span className={`mt-[3px] h-[14px] w-[14px] shrink-0 rounded-full border ${f.publicado === p.v ? "border-ink bg-ink" : "border-line-2"}`} /><span><span className="block font-sans text-[13px] font-medium">{p.l}</span><span className="block font-sans text-[11px] text-muted">{p.c}</span></span></button>)}
              </div>
              <div className="mt-4"><Check checked={f.destacado} onChange={(v) => setF({ ...f, destacado: v })} label="Destacado (primero en el catálogo)" /></div>
              <Field label="Múltiplo de compra (U.B.)" className="mt-4" hint="Mínimo y múltiplo por variante. Vacío = libre"><input className="input" inputMode="numeric" value={f.ub} onChange={(e) => setF({ ...f, ub: e.target.value.replace(/\D/g, "") })} /></Field>
              <Field label="Descuento del producto (%)" className="mt-3" hint={<>Vacío = usa Aleph ({d.aleph.descvta > 0 ? `${d.aleph.descvta}%` : "sin descuento"}). 0 fuerza SIN descuento.</>}><input className="input" inputMode="decimal" value={f.descuento_pct} onChange={(e) => setF({ ...f, descuento_pct: e.target.value.replace(/[^\d.]/g, "") })} placeholder={d.aleph.descvta > 0 ? `Aleph: ${d.aleph.descvta}%` : "sin descuento"} /></Field>
            </Panel>
            <div className="space-y-5">
              <Panel>
                <Field label="Nombre" hint={<>Aleph: {d.aleph.nombre} · vacío = usa Aleph</>}><input className="input" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} placeholder={d.aleph.nombre} /></Field>
                <Field label="Descripción" className="mt-3" hint="Vacío = usa Aleph"><textarea className="input min-h-[70px]" value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} placeholder={d.aleph.descripcion || "—"} /></Field>
                <Kicker className="mt-4">Precios por lista — manual pisa a Aleph solo en esa lista</Kicker>
                <div className="mt-2 grid gap-3 sm:grid-cols-4">
                  {["1", "2", "3", "4"].map((n) => (
                    <Field key={n} label={`Lista ${n}`} hint={<>Aleph: {d.aleph.precios[n] > 0 ? money(d.aleph.precios[n]) : "—"}{f.precios[n] && <><br /><Manual>Manual — pisa a Aleph</Manual></>}</>}>
                      <input className="input" inputMode="numeric" value={f.precios[n]} onChange={(e) => setF({ ...f, precios: { ...f.precios, [n]: e.target.value.replace(/[^\d.]/g, "") } })} placeholder="usa Aleph" />
                    </Field>
                  ))}
                </div>
              </Panel>
              <Panel>
                <Kicker>Variantes — stock y precio manual pisan a Aleph (vacío = automático)</Kicker>
                <table className="vt mt-2 text-[12.5px]">
                  <thead><tr><th>SKU</th><th>Color</th><th>Talle</th><th className="text-right">Stock Aleph</th><th>Stock manual</th><th>Oculta</th><th>Precio manual L1</th></tr></thead>
                  <tbody>
                    {d.variantes.filter((v) => !v.es_manual).map((v) => {
                      const fv = f.variantes[v.sku];
                      return (
                        <tr key={v.sku}>
                          <td className="font-mono text-[11px]">{v.sku}</td><td><span className="swatch mr-1" style={{ background: hex(v.color) }} />{v.color}</td><td>{v.talle}</td>
                          <td className="text-right">{v.stock_aleph}</td>
                          <td><input className="input !w-[80px] !py-1" inputMode="numeric" value={fv.stock} onChange={(e) => setF({ ...f, variantes: { ...f.variantes, [v.sku]: { ...fv, stock: e.target.value.replace(/\D/g, "") } } })} /></td>
                          <td><Check checked={fv.oculta} onChange={(x) => setF({ ...f, variantes: { ...f.variantes, [v.sku]: { ...fv, oculta: x } } })} /></td>
                          <td><input className="input !w-[110px] !py-1" inputMode="numeric" value={fv.precio1} onChange={(e) => setF({ ...f, variantes: { ...f.variantes, [v.sku]: { ...fv, precio1: e.target.value.replace(/[^\d.]/g, "") } } })} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {d.variantes.filter((v) => !v.es_manual && f.variantes[v.sku]?.stock !== "").map((v) => (
                  <p key={v.sku} className="mt-2 rounded bg-[#fff6d6] px-3 py-2 font-sans text-[12px]">{v.sku} tiene stock manual ({f.variantes[v.sku].stock} u.) sobre un stock real de {v.stock_aleph}. Mientras esté en manual, el sitio deja de validar contra Aleph y puede vender de más.</p>
                ))}
              </Panel>
              <Panel>
                <Kicker>Clasificación — pisa a Aleph solo en el sitio</Kicker>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Categoría" hint={<>Aleph: {d.clasificacion.categoria_aleph || "— (Otros)"} · vacío = usa Aleph</>}>
                    <input className="input" list="cats" value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })} placeholder={d.clasificacion.categoria} />
                    <datalist id="cats">{d.clasificacion.opciones_categoria.map((x) => <option key={x} value={x} />)}</datalist>
                  </Field>
                  <Field label="Tipo de producto" hint={<>Aleph: {d.clasificacion.rubro_aleph || "—"} · vacío = usa Aleph</>}>
                    <input className="input" list="rubros" value={f.rubro} onChange={(e) => setF({ ...f, rubro: e.target.value })} placeholder={d.clasificacion.rubro} />
                    <datalist id="rubros">{d.clasificacion.opciones_rubro.map((x) => <option key={x} value={x} />)}</datalist>
                  </Field>
                </div>
                <Muted className="mt-2">La categoría principal decide la sección del header: Indumentaria o Pijamas → Indumentaria; el resto de Chimola → Marroquinería. Podés escribir un valor nuevo.</Muted>
                <Field label="Categorías adicionales (el producto aparece también en estas)" className="mt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {f.categorias_extra.map((c, i) => <span key={c} className="chip">{c} <button type="button" onClick={() => setF({ ...f, categorias_extra: f.categorias_extra.filter((_, k) => k !== i) })} className="text-faint hover:text-[#aa0b56]">×</button></span>)}
                    <input className="input !w-[240px] !py-1" list="cats" value={f.nuevaCat} onChange={(e) => setF({ ...f, nuevaCat: e.target.value })}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); const v = f.nuevaCat.trim(); if (v && !f.categorias_extra.some((x) => x.toLowerCase() === v.toLowerCase())) setF({ ...f, categorias_extra: [...f.categorias_extra, v], nuevaCat: "" }); } }}
                      placeholder="Escribí y Enter (ej: Día de la madre)" />
                  </div>
                </Field>
              </Panel>
              <Panel>
                <Kicker>Productos relacionados</Kicker>
                <Muted className="mt-1">Lo que el cliente ve en «Otros productos que te pueden interesar». Si no elegís nada, se arma solo por familia (misma última palabra del nombre) y después por tipo de producto. Los que elijas van primero, en este orden.</Muted>
                <div className="mt-3 flex flex-wrap gap-2">
                  {f.relacionados.map((r, i) => (
                    <span key={r.producto_cod} className={`inline-flex items-center gap-2 rounded-sm border border-line bg-[#fafafa] px-2 py-1 font-sans text-[12px] ${r.en_catalogo ? "" : "opacity-60"}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {r.foto && <img src={r.foto} alt="" className="h-[28px] w-[28px] object-contain" />}
                      <b>{r.producto_cod}</b> {r.nombre}
                      <button type="button" onClick={() => setF({ ...f, relacionados: f.relacionados.filter((_, k) => k !== i) })} className="text-faint hover:text-[#aa0b56]">×</button>
                    </span>
                  ))}
                  {f.relacionados.length === 0 && <Muted>Sin relacionados manuales (automático).</Muted>}
                </div>
                <div className="relative mt-3">
                  <input className="input" value={relQ} onChange={(e) => setRelQ(e.target.value)} placeholder="Buscar producto por código o nombre para agregar…" />
                  {relQ.trim().length >= 2 && relRes.length > 0 && (
                    <div className="absolute z-20 mt-1 w-full border border-line bg-white shadow-lg">
                      {relRes.filter((r) => !f.relacionados.some((x) => x.producto_cod === r.producto_cod)).map((r) => (
                        <button key={r.producto_cod} type="button" onClick={() => { setF({ ...f, relacionados: [...f.relacionados, { producto_cod: r.producto_cod, nombre: r.nombre, foto: r.foto, en_catalogo: true }] }); setRelQ(""); setRelRes([]); }}
                          className="flex w-full items-center gap-3 px-3 py-2 text-left font-sans text-[12.5px] hover:bg-[#f5f5f5]">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          {r.foto && <img src={r.foto} alt="" className="h-[32px] w-[32px] object-contain" />}<b>{r.producto_cod}</b> {r.nombre}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {d.relacionados_inversos.length > 0 && <Muted className="mt-3">Además lo eligieron como relacionado: {d.relacionados_inversos.map((r) => r.producto_cod).join(", ")} (aparecen en su ficha automáticamente).</Muted>}
              </Panel>
              <Panel>
                <Kicker>Variantes manuales</Kicker>
                <Muted className="mt-1">No existen en Aleph: stock y precio son 100% tuyos y el Excel las marca. <Manual>«Agregar» se aplica al instante</Manual>; las ediciones de la tabla van con Guardar.</Muted>
                {Object.keys(f.extras).length > 0 ? (
                  <table className="vt mt-3 text-[12.5px]">
                    <thead><tr><th>SKU</th><th>Color</th><th>Talle</th><th>Stock</th><th>Precio L1</th><th>EAN</th><th>Quitar</th></tr></thead>
                    <tbody>{Object.entries(f.extras).map(([sku, x]) => (
                      <tr key={sku} className={x.quitar ? "opacity-40" : ""}>
                        <td className="font-mono text-[11px]">{sku}</td><td>{x.color}</td><td>{x.talle}</td>
                        <td><input className="input !w-[80px] !py-1" inputMode="numeric" value={x.stock} onChange={(e) => setF({ ...f, extras: { ...f.extras, [sku]: { ...x, stock: e.target.value.replace(/\D/g, "") } } })} /></td>
                        <td><input className="input !w-[110px] !py-1" inputMode="numeric" value={x.precio} onChange={(e) => setF({ ...f, extras: { ...f.extras, [sku]: { ...x, precio: e.target.value.replace(/[^\d.]/g, "") } } })} /></td>
                        <td><input className="input !w-[140px] !py-1" value={x.ean} onChange={(e) => setF({ ...f, extras: { ...f.extras, [sku]: { ...x, ean: e.target.value } } })} /></td>
                        <td><Check checked={x.quitar} onChange={(v) => setF({ ...f, extras: { ...f.extras, [sku]: { ...x, quitar: v } } })} /></td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <Muted className="mt-2">Este producto no tiene variantes manuales.</Muted>}
                <div className="mt-3 grid gap-2 sm:grid-cols-[1.2fr_0.7fr_0.7fr_1fr_1.2fr_auto]">
                  <input className="input" placeholder="Color nuevo (obligatorio)" value={nuevaExtra.color} onChange={(e) => setNuevaExtra({ ...nuevaExtra, color: e.target.value })} />
                  <input className="input" placeholder="Talle" value={nuevaExtra.talle} onChange={(e) => setNuevaExtra({ ...nuevaExtra, talle: e.target.value })} />
                  <input className="input" placeholder="Stock" inputMode="numeric" value={nuevaExtra.stock} onChange={(e) => setNuevaExtra({ ...nuevaExtra, stock: e.target.value.replace(/\D/g, "") })} />
                  <input className="input" placeholder="Precio L1" inputMode="numeric" value={nuevaExtra.precio} onChange={(e) => setNuevaExtra({ ...nuevaExtra, precio: e.target.value.replace(/[^\d.]/g, "") })} />
                  <input className="input" placeholder="EAN (opcional)" value={nuevaExtra.ean} onChange={(e) => setNuevaExtra({ ...nuevaExtra, ean: e.target.value })} />
                  <button onClick={agregarExtra} className="btn btn-light">Agregar</button>
                </div>
              </Panel>
              {d.fotos.n > 0 && (
                <Panel>
                  <Kicker>Fotos por color</Kicker>
                  <Muted className="mt-1">La miniatura de cada variante usa la foto de SU color (detección por nombre de archivo). Si un color no matchea, asignale el archivo a mano.</Muted>
                  <table className="vt mt-3 text-[12.5px]">
                    <thead><tr><th>Color</th><th>Foto detectada</th><th>Asignación manual</th></tr></thead>
                    <tbody>{d.fotos.por_color.map((c) => (
                      <tr key={c.norm}>
                        <td><span className="swatch mr-1" style={{ background: hex(c.color) }} />{c.color}</td>
                        <td className="text-muted">{c.auto || "— (usa portada)"}</td>
                        <td>
                          <button type="button" onClick={() => setFcAbierto(fcAbierto === c.norm ? null : c.norm)} className="flex items-center gap-2 font-sans text-[12px] hover:underline">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={d.fotos.urls[f.fotos_color[c.norm] || c.auto || ""] || ""} alt="" className="h-[36px] w-[36px] bg-white object-contain" />
                            {f.fotos_color[c.norm] ? <Manual>{f.fotos_color[c.norm]}</Manual> : <span className="text-muted">(automática) · elegir</span>}
                          </button>
                        </td>
                      </tr>
                    )).flatMap((row, idx) => fcAbierto === d.fotos.por_color[idx].norm ? [row,
                      <tr key={`${d.fotos.por_color[idx].norm}-picker`}><td colSpan={3} className="bg-[#fafafa] p-3">
                        <FotoGrid fotos={d.fotos.files.map((fn) => ({ filename: fn, url: d.fotos.urls[fn] }))} value={f.fotos_color[d.fotos.por_color[idx].norm] || null} permitirNinguna
                          onChange={(ft) => { setF({ ...f, fotos_color: { ...f.fotos_color, [d.fotos.por_color[idx].norm]: ft ? ft.filename : "" } }); setFcAbierto(null); }} />
                      </td></tr>] : [row])}</tbody>
                  </table>
                  <Kicker className="mt-5">Foto de portada</Kicker>
                  <Muted className="mt-1">Con la que el producto aparece en el catálogo. Automática = la detectada por nombre ({d.fotos.portada_auto}).</Muted>
                  <div className="mt-2"><FotoGrid fotos={d.fotos.files.map((fn) => ({ filename: fn, url: d.fotos.urls[fn] }))} value={f.portada || null} permitirNinguna onChange={(ft) => setF({ ...f, portada: ft ? ft.filename : "" })} /></div>
                </Panel>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <button onClick={guardar} disabled={busy} className="btn btn-primary">{busy ? "Guardando…" : "Guardar"}</button>
                <button onClick={() => { setEdit(false); setF(formDe(d)); }} className="btn btn-light">Descartar</button>
                {!confirmQuitar ? <button onClick={() => setConfirmQuitar(true)} className="btn btn-ghost text-[#aa0b56]">Quitar TODOS los overrides</button> : <Confirm busy={busy} texto={<>El producto vuelve 100% a Aleph: se pierden nombre, precios, variantes manuales, fotos asignadas y publicación. ¿Seguro?</>} onYes={quitarTodo} onNo={() => setConfirmQuitar(false)} />}
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function Vista({ d, hex }: { d: Data; hex: (c: string) => string | undefined }) {
  const o = d.override;
  const pub = o.publicado === true || o.publicado === false ? o.publicado : null;
  const regla = { null: "Automático — visible si tiene stock", true: "Publicado — visible, exige stock > 0", false: "Oculto — nunca visible" }[String(pub) as "null" | "true" | "false"];
  const attr = (k: string, v: React.ReactNode, manual: boolean) => <div className="mt-3"><Kicker>{k}</Kicker><div className="font-sans text-[13.5px]">{v}</div>{manual && <Manual />}</div>;
  const origenes = (v: Var) => v.es_manual ? "VARIANTE MANUAL" : [v.ov.stock !== undefined && v.ov.stock !== null ? "stock manual" : "", v.ov.oculta ? "oculta" : "", v.ov.precios ? "precio manual" : ""].filter(Boolean).join(" · ");
  const avisos: string[] = [];
  for (const v of d.variantes) if (!v.es_manual && v.ov.stock !== undefined && v.ov.stock !== null) avisos.push(`${v.sku} tiene stock manual (${v.ov.stock} u.) sobre un stock real de ${v.stock_aleph} — el sitio no valida contra Aleph mientras dure.`);
  for (const sku of Object.keys(o.variantes_extra || {})) avisos.push(`${sku} es una variante manual: no existe en Aleph y el Excel del pedido la marca.`);
  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      <Panel>
        {d.fotos.principal ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={d.fotos.principal} alt="" className="aspect-square w-full object-contain" /> : <div className="flex aspect-square items-center justify-center text-faint">Sin foto</div>}
        {attr("Publicación", regla, pub !== null)}
        {attr("Destacado", o.destacado ? "Sí" : "No", !!o.destacado)}
        {attr("Múltiplo (U.B.)", o.ub ? `${o.ub} unidades` : "Libre", !!o.ub)}
        {attr("Descuento", o.descuento_pct !== null && o.descuento_pct !== undefined ? `${o.descuento_pct}%` : d.aleph.descvta > 0 ? `${d.aleph.descvta}% (Aleph)` : "Sin descuento", o.descuento_pct !== null && o.descuento_pct !== undefined)}
        {attr("Fotos", d.fotos.n ? `${d.fotos.n} cargada(s)` : "Sin foto", false)}
        {attr("Categoría", <>{d.clasificacion.categoria}{(o.categorias_extra || []).length > 0 && <span className="text-muted"> + {o.categorias_extra!.join(", ")}</span>}</>, !!o.categoria || (o.categorias_extra || []).length > 0)}
        {attr("Tipo de producto", d.clasificacion.rubro, !!o.rubro)}
        {attr("Relacionados", d.relacionados.length ? d.relacionados.map((r) => r.producto_cod).join(", ") : "Automático", d.relacionados.length > 0)}
      </Panel>
      <div className="space-y-5">
        <Panel>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><Kicker>Nombre</Kicker><div className="font-sans text-[14px]">{d.efectivo.nombre} {o.nombre && <Manual />}</div>{o.nombre && <Muted>Aleph: {d.aleph.nombre}</Muted>}</div>
            <div><Kicker>Descripción</Kicker><div className="font-sans text-[13px] leading-snug">{d.efectivo.descripcion || "—"} {o.descripcion && <Manual />}</div>{o.descripcion && d.aleph.descripcion && <Muted>Aleph: {d.aleph.descripcion}</Muted>}</div>
          </div>
          <Kicker className="mt-5">Precio efectivo por lista</Kicker>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {["1", "2", "3", "4"].map((n) => { const ef = o.precios?.[n] || d.aleph.precios[n]; return <div key={n} className="border-t border-line-2 pt-2 font-sans text-[12px]">Lista {n}<div className="font-brand text-[18px] font-bold">{ef > 0 ? money(ef) : "—"}</div>{o.precios?.[n] ? <Manual>Manual</Manual> : <span className="text-muted">Aleph</span>}</div>; })}
          </div>
        </Panel>
        <Panel>
          <Kicker>Variantes · efectivo hoy</Kicker>
          <Muted className="mt-1">Lo que el cliente ve ahora, con el origen de cada valor.</Muted>
          <table className="vt mt-3 text-[12.5px]">
            <thead><tr><th>SKU</th><th>Color</th><th>Talle</th><th>EAN</th><th className="text-right">Stock</th><th className="text-right">Aleph</th><th className="text-right">Precio L1</th><th>Overrides</th></tr></thead>
            <tbody>{d.variantes.map((v) => <tr key={v.sku}><td className="font-mono text-[11px]">{v.sku}</td><td><span className="swatch mr-1" style={{ background: hex(v.color) }} />{v.color}</td><td>{v.talle}</td><td className="text-muted">{v.ean || "—"}</td><td className="text-right">{v.stock}</td><td className="text-right text-muted">{v.es_manual ? "—" : v.stock_aleph}</td><td className="text-right">{v.precio1 ? money(v.precio1) : "—"}</td><td className={v.es_manual ? "font-semibold text-[#aa0b56]" : "text-[#006786]"}>{origenes(v)}</td></tr>)}</tbody>
          </table>
          {avisos.length > 0 && <div className="mt-3 rounded bg-[#fff6d6] px-3 py-2 font-sans text-[12px] leading-relaxed">{avisos.join(" ")}</div>}
        </Panel>
      </div>
    </div>
  );
}
