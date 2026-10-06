"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Check, Confirm, H1, Kicker, Muted, Panel, Pills, Spinner } from "@/components/admin/ui";

type Sec = "marro" | "indu" | "lima";
type Lista = "temporadas" | "tipos" | "tendencias";
const SECS: { value: Sec; label: string }[] = [{ value: "marro", label: "Marroquinería (Chimola)" }, { value: "indu", label: "Indumentaria (Chimola)" }, { value: "lima", label: "LIMA" }];
const LISTAS: { key: Lista; titulo: string; ayuda: string }[] = [
  { key: "temporadas", titulo: "Temporada", ayuda: "Las tres primeras van arriba; «anterior» las manda al grupo «Temporadas anteriores». «Nuevo» pone la etiqueta New." },
  { key: "tipos", titulo: "Tipo de producto", ayuda: "Los rubros de Aleph. En automático se muestran los 12 con más productos." },
  { key: "tendencias", titulo: "Tendencia", ayuda: "Las categorías de Aleph que no son Marroquinería ni Indumentaria (Bazar, Librería, Textil…)." },
];
interface Item { valor: string; nombre: string; n: number; nuevo?: boolean; anterior?: boolean }
interface Fila extends Item { mostrar: boolean }
interface Res { seccion: Sec; auto: Record<Lista, { valor: string; n: number }[]>; config: Partial<Record<Lista, Item[]>> | null; efectivo: Record<Lista, Item[]> & { personalizado: Record<Lista, boolean>; n: number; oportunidades: number }; tope_auto: Record<Lista, number> }

export default function MenuAdmin() {
  const [sec, setSec] = useState<Sec>("marro");
  const [r, setR] = useState<Res | null>(null);
  const [filas, setFilas] = useState<Record<Lista, Fila[]>>({ temporadas: [], tipos: [], tendencias: [] });
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    const d = await api<Res>(`/admin/menu/${sec}`); setR(d);
    const out = {} as Record<Lista, Fila[]>;
    for (const L of LISTAS) {
      const conf = d.config?.[L.key] || [];
      const auto = d.auto[L.key];
      const nAuto = new Map(auto.map((a) => [a.valor, a.n]));
      const mostrados: Fila[] = (conf.length ? conf.filter((c) => nAuto.has(c.valor)).map((c) => ({ ...c, n: nAuto.get(c.valor)!, mostrar: true }))
        : d.efectivo[L.key].map((e) => ({ ...e, mostrar: true })));
      const vistos = new Set(mostrados.map((m) => m.valor));
      const resto: Fila[] = auto.filter((a) => !vistos.has(a.valor)).map((a) => ({ valor: a.valor, nombre: a.valor, n: a.n, nuevo: false, anterior: false, mostrar: false }));
      out[L.key] = [...mostrados, ...resto];
    }
    setFilas(out);
  }, [sec]);
  useEffect(() => { setR(null); cargar(); }, [cargar]);

  function mover(L: Lista, i: number, dir: -1 | 1) {
    const arr = [...filas[L]]; const j = i + dir; if (j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]]; setFilas({ ...filas, [L]: arr });
  }
  const set = (L: Lista, i: number, patch: Partial<Fila>) => setFilas({ ...filas, [L]: filas[L].map((f, k) => k === i ? { ...f, ...patch } : f) });

  async function guardar() {
    setBusy(true);
    try {
      const body: Record<string, Item[]> = {};
      for (const L of LISTAS) body[L.key] = filas[L.key].filter((f) => f.mostrar).map(({ valor, nombre, nuevo, anterior }) => ({ valor, nombre: nombre || valor, n: 0, ...(L.key === "temporadas" ? { nuevo: !!nuevo, anterior: !!anterior } : {}) }));
      await api(`/admin/menu/${sec}`, { method: "PUT", json: body });
      notify("Menú guardado — el sitio lo toma en menos de un minuto"); await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  if (!r) return <><H1>Menú desplegable</H1><div className="mb-4"><Pills value={sec} onChange={setSec} options={SECS} /></div><Spinner /></>;
  const personalizado = Object.values(r.efectivo.personalizado).some(Boolean);
  return (
    <>
      <H1>Menú desplegable</H1>
      <Muted>Qué aparece al pasar el mouse por cada sección del header. Marcá «mostrar», renombrá y ordená con las flechas. Si no guardás nada, el menú se arma solo desde BigQuery por cantidad de productos. Lo que no esté marcado no aparece en el menú, pero sigue filtrable en el catálogo.</Muted>
      <div className="mt-4"><Pills value={sec} onChange={setSec} options={SECS} /></div>
      <Muted className="mt-2">{personalizado ? "Menú personalizado guardado para esta sección." : "Menú automático (nada guardado)."} · {r.efectivo.n} productos · {r.efectivo.oportunidades} con descuento</Muted>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.5fr_1.1fr_0.9fr]">
        {LISTAS.map((L) => (
          <Panel key={L.key}>
            <Kicker>{L.titulo}{r.efectivo.personalizado[L.key] && <span className="ml-2 text-[#006786]">personalizado</span>}</Kicker>
            <Muted className="mt-1">{L.ayuda}</Muted>
            <table className="vt mt-3 text-[12px]">
              <thead><tr><th className="whitespace-nowrap">Mostrar</th><th className="whitespace-nowrap">Nombre a mostrar</th><th className="text-right">Prod.</th>{L.key === "temporadas" && <><th>Nuevo</th><th>Anterior</th></>}<th /></tr></thead>
              <tbody>{filas[L.key].map((f, i) => (
                <tr key={f.valor} className={f.mostrar ? "" : "opacity-50"}>
                  <td><Check checked={f.mostrar} onChange={(v) => set(L.key, i, { mostrar: v })} /></td>
                  <td className="min-w-[170px]"><input className="input !py-1 !text-[12px]" value={f.nombre} onChange={(e) => set(L.key, i, { nombre: e.target.value })} /><div className="card-meta">{f.valor !== f.nombre && <>Aleph: {f.valor}</>}</div></td>
                  <td className="text-right text-muted">{f.n}</td>
                  {L.key === "temporadas" && <><td><Check checked={!!f.nuevo} onChange={(v) => set(L.key, i, { nuevo: v })} /></td><td><Check checked={!!f.anterior} onChange={(v) => set(L.key, i, { anterior: v })} /></td></>}
                  <td className="whitespace-nowrap"><button onClick={() => mover(L.key, i, -1)} className="px-1 text-faint hover:text-ink">↑</button><button onClick={() => mover(L.key, i, 1)} className="px-1 text-faint hover:text-ink">↓</button></td>
                </tr>
              ))}</tbody>
            </table>
          </Panel>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={guardar} disabled={busy} className="btn btn-primary">{busy ? "Guardando…" : "Guardar menú"}</button>
        {personalizado && (!confirmReset ? <button onClick={() => setConfirmReset(true)} className="btn btn-ghost">Volver al menú automático</button> : <Confirm busy={busy} texto="Se descarta lo personalizado y el menú vuelve a armarse solo." onYes={async () => { setBusy(true); await api(`/admin/menu/${sec}`, { method: "DELETE" }); setConfirmReset(false); setBusy(false); notify("Menú automático restaurado"); cargar(); }} onNo={() => setConfirmReset(false)} />)}
      </div>
    </>
  );
}
