"use client";
/* Reposición sugerida para franquicias: sell-out 30d del PV vs stock del PV → cantidades sugeridas. */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { Chevron } from "./Brand";
import Thumb from "./Thumb";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import QtyInput from "./QtyInput";
import { capital } from "./ProductCard";

interface Item {
  sku: string; producto_cod: string; nombre: string; marca: string; rubro: string; categoria: string; temporada: string;
  color: string; hex: string; talle: string; precio: number | null; precio_lista: number | null; pct_desc: number;
  vendidas_30d: number; stock_pv: number; cobertura_dias: number | null; sugerido: number; ub: number | null; foto: string | null;
}
interface Res { pv: { pv_cod: number; pv_nombre: string }; dias: number; items: Item[]; total_sugerido: number }

const DIAS = [7, 14, 21, 30];

export default function ReposicionClient() {
  const [dias, setDias] = useState<number | null>(null);
  const [res, setRes] = useState<Res | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cants, setCants] = useState<Record<string, number>>({});
  const [q, setQ] = useState("");
  const [rubro, setRubro] = useState("");
  const [busy, setBusy] = useState(false);
  const { agregar } = useCart();
  const { notify } = useToast();

  useEffect(() => {
    let vivo = true;
    api<Res>(`/reposicion${dias ? `?dias=${dias}` : ""}`).then((d) => {
      if (!vivo) return;
      setRes(d);
      setCants(Object.fromEntries(d.items.map((i) => [i.sku, i.sugerido])));
    }).catch((e) => vivo && setErr(e instanceof ClientError ? e.message : "No se pudo cargar la reposición"));
    return () => { vivo = false; };
  }, [dias]);

  const rubros = useMemo(() => Array.from(new Set((res?.items ?? []).map((i) => i.rubro))).sort(), [res]);
  const visibles = useMemo(() => (res?.items ?? []).filter((i) =>
    (!rubro || i.rubro === rubro) &&
    (!q || `${i.producto_cod} ${i.nombre} ${i.color}`.toLowerCase().includes(q.toLowerCase()))), [res, rubro, q]);

  const total = useMemo(() => visibles.reduce((a, i) => a + (cants[i.sku] || 0), 0), [visibles, cants]);
  const monto = useMemo(() => visibles.reduce((a, i) => a + (cants[i.sku] || 0) * (i.precio || 0), 0), [visibles, cants]);

  async function onAgregar() {
    const items = visibles.filter((i) => (cants[i.sku] || 0) > 0).map((i) => ({ sku: i.sku, cantidad: cants[i.sku] }));
    if (!items.length) return;
    setBusy(true);
    try {
      const c = await agregar(items);
      c.avisos.forEach((a) => notify(a, "aviso"));
      const n = c.agregadas ?? 0;
      if (n > 0) notify(`Se cargaron ${n} unidades de reposición al carrito.`);
      else if (!c.avisos.length) notify("No se cargó nada: sin disponibilidad para lo elegido.", "aviso");
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className="container-lt pb-10 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-brand text-[28px] font-extrabold">Reposición sugerida</h1>
          {res && <p className="mt-1 font-sans text-[13px] text-muted">Según lo que vendió <b className="text-ink">{res.pv.pv_nombre}</b> en los últimos 30 días y lo que tiene en el local.</p>}
        </div>
        <div className="flex items-center gap-2 font-sans text-[12px] font-bold">
          Días de venta a cubrir:
          {DIAS.map((d) => (
            <button key={d} onClick={() => setDias(d)} className={`pill !px-3 !py-[5px] ${(res?.dias ?? dias) === d ? "!bg-ink !text-white !border-ink" : ""}`}>{d}</button>
          ))}
        </div>
      </div>

      {err && <p className="mt-6 rounded-md border border-[#f3b7cc] bg-[#fff1f4] px-4 py-3 font-sans text-[13px] text-[#aa0b56]">{err}</p>}
      {!res && !err && <div className="mt-6 flex h-64 items-center justify-center bg-white font-sans text-[13px] text-muted">Calculando la reposición sugerida (puede tardar unos segundos)…</div>}

      {res && (
        <>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar código, nombre o color" className="input !w-[280px]" />
            <select value={rubro} onChange={(e) => setRubro(e.target.value)} className="input !w-auto">
              <option value="">Todos los tipos</option>
              {rubros.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <span className="ml-auto font-sans text-[12px] text-muted">{visibles.length} variantes · sugerido {res.total_sugerido} u.</span>
          </div>

          {visibles.length === 0 ? (
            <div className="mt-4 bg-white p-10 text-center font-sans text-[14px] text-muted">No hay nada para reponer con estos filtros.</div>
          ) : (
            <div className="mt-4 bg-white">
              <div className="overflow-x-auto">
              <table className="w-full min-w-[760px]">
                <thead>
                  <tr className="border-b-2 border-ink font-sans text-[11px] uppercase text-ink-2">
                    <th className="px-4 py-3 text-left" colSpan={2}>Producto</th><th className="px-2 py-3 text-left">Variante</th>
                    <th className="px-2 py-3 text-right">Vendiste 30d</th><th className="px-2 py-3 text-right">Tenés</th>
                    <th className="px-2 py-3 text-right">Cobertura</th><th className="px-2 py-3 text-right">Precio</th>
                    <th className="px-2 py-3 text-center">Cantidad</th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((i) => (
                    <tr key={i.sku} className="border-b border-line font-sans text-[13px]">
                      <td className="w-[64px] py-2 pl-4">
                        <Thumb src={i.foto} className="h-[52px] w-[52px] bg-white object-contain" />
                      </td>
                      <td className="py-2 pr-2"><Link href={`/p/${i.producto_cod}`} className="font-brand text-[13px] font-bold hover:underline">{i.nombre}</Link><div className="card-meta"><b>{i.producto_cod}</b> · {i.rubro}</div></td>
                      <td className="px-2 py-2"><span className="inline-flex items-center gap-2"><span className="swatch" style={{ background: i.hex }} />{capital(i.color)}{i.talle !== "U" && <span className="text-muted"> · Talle {i.talle}</span>}</span></td>
                      <td className="px-2 py-2 text-right">{i.vendidas_30d}</td>
                      <td className="px-2 py-2 text-right">{i.stock_pv}</td>
                      <td className="px-2 py-2 text-right">{i.cobertura_dias === null ? "—" : `${Math.round(i.cobertura_dias)} d`}</td>
                      <td className="px-2 py-2 text-right">{i.pct_desc > 0 && i.precio_lista ? <div className="price-old">{money(i.precio_lista)}</div> : null}{money(i.precio)}</td>
                      <td className="px-2 py-2 text-center"><QtyInput value={cants[i.sku] || 0} onChange={(n) => setCants({ ...cants, [i.sku]: n })} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-4 p-4">
                <span className="font-sans text-[13px]"><b>{total}</b> unidades · {money(monto)} a precio de lista</span>
                <button onClick={onAgregar} disabled={busy || total === 0} className="btn btn-primary">{busy ? "Agregando…" : "Agregar reposición al carrito"} <Chevron size={15} /></button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
