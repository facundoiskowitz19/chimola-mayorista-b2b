"use client";
/* Barra de acciones en lote reutilizable (Categorías, Tipos, Temporadas): selección + acciones sobre
 * los seleccionados o sobre todos los productos de la página. Pega en POST /admin/catalogo/lote. */
import { useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Confirm, Muted } from "./ui";

export type Campos = Record<string, boolean | string | null>;
export const LOTES: { label: string; campos: Campos; desc: string }[] = [
  { label: "Ocultar", campos: { publicado: false }, desc: "OCULTAR" },
  { label: "Publicación automática", campos: { publicado: null }, desc: "volver a publicación AUTOMÁTICA" },
  { label: "Destacar", campos: { destacado: true }, desc: "DESTACAR" },
  { label: "Quitar destacado", campos: { destacado: false }, desc: "quitar el destacado a" },
];

export default function LoteBar({ sel, todos, onDone, onClear, opcionesCategoria = [], opcionesRubro = [], extraAcciones }: {
  sel: Set<string>; todos: string[]; onDone: () => Promise<void> | void; onClear: () => void;
  opcionesCategoria?: string[]; opcionesRubro?: string[];
  /** Acciones propias de la pantalla (ej. «Quitar de esta categoría»), reciben los códigos elegidos. */
  extraAcciones?: { label: string; desc: string; campos: Campos }[];
}) {
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{ cods: string[]; campos: Campos; desc: string } | null>(null);
  const [cat, setCat] = useState(""); const [rubro, setRubro] = useState(""); const [extra, setExtra] = useState("");
  const { notify } = useToast();

  async function aplicar(cods: string[], campos: Campos, desc: string, confirmado = false) {
    if (!cods.length) return;
    if (cods.length > 10 && !confirmado) { setConfirm({ cods, campos, desc }); return; }
    setBusy(true);
    try {
      const r = await api<{ n: number }>("/admin/catalogo/lote", { method: "POST", json: { cods, campos } });
      notify(`Listo: ${r.n} producto(s) actualizados.`);
      setConfirm(null); setCat(""); setRubro(""); setExtra("");
      await onDone();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  const cods = sel.size ? [...sel] : todos;
  const alcance = sel.size ? `${sel.size} seleccionado(s)` : `los ${todos.length} de esta lista`;
  const acciones = [...LOTES, ...(extraAcciones || [])];
  return (
    <div className={`mt-4 border px-4 py-3 ${sel.size ? "border-[#006786] bg-[#e9f8ff]" : "border-line bg-white"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b className="mr-2 font-sans text-[13px] text-[#006786]">Acciones en lote · {alcance}</b>
        {acciones.map((l) => <button key={l.label} onClick={() => aplicar(cods, l.campos, l.desc)} disabled={busy || !cods.length} className="btn btn-light btn-sm">{l.label}</button>)}
        {sel.size > 0 && <button onClick={onClear} className="btn btn-ghost btn-sm">Deseleccionar</button>}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 font-sans text-[12px]">
        {opcionesCategoria.length > 0 && (
          <span className="inline-flex items-center gap-1">Categoría principal →
            <input className="input !w-[180px] !py-1 !text-[12px]" list="lote-cats" value={cat} onChange={(e) => setCat(e.target.value)} placeholder="nueva o existente" />
            <datalist id="lote-cats">{opcionesCategoria.map((x) => <option key={x} value={x} />)}</datalist>
            <button disabled={busy || !cat.trim() || !cods.length} onClick={() => aplicar(cods, { categoria: cat.trim() }, `mover a la categoría «${cat.trim()}»`)} className="btn btn-light btn-sm">Mover</button>
          </span>
        )}
        {opcionesRubro.length > 0 && (
          <span className="inline-flex items-center gap-1">Tipo de producto →
            <select className="input !w-[180px] !py-1 !text-[12px]" value={rubro} onChange={(e) => setRubro(e.target.value)}><option value="">elegir…</option>{opcionesRubro.map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <button disabled={busy || !rubro || !cods.length} onClick={() => aplicar(cods, { rubro }, `mover al tipo «${rubro}»`)} className="btn btn-light btn-sm">Mover</button>
          </span>
        )}
        <span className="inline-flex items-center gap-1">Sumar a categoría adicional →
          <input className="input !w-[180px] !py-1 !text-[12px]" list="lote-cats" value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="ej: Día de la madre" />
          <button disabled={busy || !extra.trim() || !cods.length} onClick={() => aplicar(cods, { categoria_extra_add: extra.trim() }, `sumar a la categoría «${extra.trim()}»`)} className="btn btn-light btn-sm">Sumar</button>
        </span>
        <button disabled={busy || !cods.length} onClick={() => aplicar(cods, { categoria: "", rubro: "" }, "volver a la clasificación de Aleph a")} className="btn btn-ghost btn-sm">Clasificación de Aleph</button>
      </div>
      <Muted className="mt-2">Sin casillas marcadas, las acciones aplican a todos los productos de esta lista. Con más de 10 pide confirmación. Se aplican al instante.</Muted>
      {confirm && <div className="mt-3"><Confirm busy={busy} texto={<>Vas a <b>{confirm.desc}</b> {confirm.cods.length} productos. ¿Seguro?</>} onYes={() => aplicar(confirm.cods, confirm.campos, confirm.desc, true)} onNo={() => setConfirm(null)} /></div>}
    </div>
  );
}
