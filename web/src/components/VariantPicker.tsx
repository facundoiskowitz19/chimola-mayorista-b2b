"use client";
/* Selector de cantidades por variante. Dos modos:
 *  - lista:  un talle → una fila por color (marroquinería)
 *  - matriz: varios talles → color × talle, con "Curva personalizada" / "Curva sugerida" (indumentaria)
 * Nunca muestra stock. Al agregar, la API NO recorta (`recortar: false`): si algo supera lo disponible
 * devuelve `ajustes` con el máximo por variante, el picker pone ese número y el cliente vuelve a confirmar.
 * Colores/talles sin ninguna variante disponible no se muestran; una celda puntual sin stock queda en gris.
 */
import { useMemo, useState } from "react";
import type { Ajuste, Carrito, Curva, Producto } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { Chevron } from "./Brand";
import QtyInput from "./QtyInput";
import { capital } from "./ProductCard";
import { useToast } from "./Toast";

export type Cants = Record<string, number>;
export type Maximos = Record<string, number>;

export function esMatriz(p: Producto) {
  return p.talles.length > 1;
}

/** Resultado de un POST /carrito/items con `recortar:false`. Devuelve los máximos a mostrar (vacío si se agregó). */
export function procesarAgregado(c: Carrito, cants: Cants, setCants: (c: Cants) => void, notify: (m: string, t?: "ok" | "aviso" | "error") => void): Maximos {
  const aj: Ajuste[] = c.ajustes ?? [];
  if (aj.length) {
    const next = { ...cants };
    const max: Maximos = {};
    aj.forEach((a) => { next[a.sku] = a.maximo; max[a.sku] = a.maximo; });
    setCants(next);
    const det = aj.slice(0, 3).map((a) => `${capital(a.color)}${a.talle !== "U" ? ` T.${a.talle}` : ""}: ${a.maximo === 0 ? (a.en_carrito ? "ya tenés todo lo disponible en el carrito" : "sin disponibilidad") : `máximo ${a.maximo} u.`}`).join(" · ");
    notify(`Ajustamos las cantidades a lo disponible (${det}${aj.length > 3 ? ` y ${aj.length - 3} más` : ""}). Revisalas y volvé a tocar «Agregar al carrito».`, "aviso");
    return max;
  }
  c.avisos.forEach((a) => notify(a, "aviso"));
  return {};
}

const Gris = ({ className = "" }: { className?: string }) => <span className={`inline-block h-[28px] w-[44px] rounded-sm bg-[#f1f1f1] align-middle ${className}`} title="Sin disponibilidad" />;

export default function VariantPicker({ p, cants, setCants, onAgregar, busy, maximos = {} }: {
  p: Producto; cants: Cants; setCants: (c: Cants) => void; onAgregar: () => void; busy: boolean; maximos?: Maximos;
}) {
  const matriz = esMatriz(p);
  const total = useMemo(() => Object.values(cants).reduce((a, b) => a + b, 0), [cants]);
  const [modo, setModo] = useState<"personalizada" | "sugerida">("personalizada");
  const [totalCurva, setTotalCurva] = useState(0);
  const [curvaBusy, setCurvaBusy] = useState(false);
  const [recortada, setRecortada] = useState(false);
  const { notify } = useToast();

  const skuDe = (color: string, talle: string) => p.variantes.find((v) => v.color === color && v.talle === talle);
  // Solo colores y talles con al menos una variante disponible; el resto no se ofrece.
  const disponibles = useMemo(() => p.variantes.filter((v) => v.disponible), [p.variantes]);
  const colores = useMemo(() => p.colores.filter((c) => disponibles.some((v) => v.color === c.color)), [p.colores, disponibles]);
  const talles = useMemo(() => p.talles.filter((t) => disponibles.some((v) => v.talle === t)), [p.talles, disponibles]);
  const hayAjustes = Object.keys(maximos).length > 0;

  async function sugerir() {
    if (totalCurva <= 0) return;
    setCurvaBusy(true);
    try {
      const c = await api<Curva>(`/productos/${p.producto_cod}/curva?total=${totalCurva}`);
      const next: Cants = {};
      c.items.forEach((i) => { next[i.sku] = i.cantidad; });
      setCants(next);
      setRecortada(c.recortado);
    } catch (e) {
      notify(e instanceof ClientError ? e.message : "No se pudo armar la curva sugerida.", "error");
    } finally { setCurvaBusy(false); }
  }

  const set = (sku: string, n: number) => setCants({ ...cants, [sku]: n });
  const maxHint = (sku: string) => maximos[sku] !== undefined ? <span className="block font-sans text-[10px] leading-tight text-[#aa0b56]">máx. {maximos[sku]}</span> : null;

  const pie = (
    <>
      {hayAjustes && <p className="mt-3 rounded-md bg-[#fff1f4] px-3 py-2 font-sans text-[12px] text-[#aa0b56]">Algunas cantidades superaban lo disponible: las bajamos al máximo posible. Si estás de acuerdo, tocá «Agregar al carrito» de nuevo.</p>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 font-sans text-[12px] font-bold leading-tight">
          Cantidad<br />Total:
          <span className="qty !min-w-[56px] !h-[30px] font-semibold">{total || "-"}</span>
          <span className="font-normal">u.</span>
        </div>
        <button onClick={onAgregar} disabled={busy || total === 0} className="btn btn-primary !py-3 !px-5">
          <span>{busy ? "Agregando…" : hayAjustes ? "Agregar al carrito así" : "Agregar al carrito"}</span><Chevron size={16} />
        </button>
      </div>
    </>
  );

  if (!disponibles.length) {
    return <p className="font-sans text-[13px] text-muted">Este producto no tiene variantes disponibles en este momento.</p>;
  }

  if (!matriz) {
    return (
      <div>
        <p className="font-sans text-[12.5px] font-medium">Indique las cantidades y añada al carrito</p>
        <table className="vt mt-2">
          <thead><tr><th>Variante</th><th className="w-[150px]">Cantidad</th></tr></thead>
          <tbody>
            {disponibles.map((v) => (
              <tr key={v.sku} className={cants[v.sku] > 0 ? "sel" : ""}>
                <td><span className="inline-flex items-center gap-2"><span className="swatch" style={{ background: p.colores.find((c) => c.color === v.color)?.hex }} />{capital(v.color)}{p.talles[0] !== "U" && <span className="text-muted"> · Talle {v.talle}</span>}</span></td>
                <td>
                  <span className="inline-flex items-center gap-2">
                    <span><QtyInput value={cants[v.sku] || 0} onChange={(n) => set(v.sku, n)} className={maximos[v.sku] !== undefined ? "!border-[#aa0b56]" : ""} />{maxHint(v.sku)}</span>
                    <span className="font-sans text-[12px]">Unidades</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {pie}
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap gap-7">
        <button type="button" onClick={() => setModo("personalizada")} className="flex items-start gap-3 text-left">
          <span className="cb cb-lg mt-[2px]" data-on={modo === "personalizada"}>{modo === "personalizada" && "✓"}</span>
          <span><span className={`block font-brand text-[13px] font-bold ${modo !== "personalizada" ? "text-faint" : ""}`}>Curva personalizada</span>
            <span className={`block font-sans text-[11.5px] ${modo !== "personalizada" ? "text-faint" : "text-muted"}`}>Indique las cantidades por talle y color</span></span>
        </button>
        <button type="button" onClick={() => setModo("sugerida")} className="flex items-start gap-3 text-left">
          <span className="cb cb-lg mt-[2px]" data-on={modo === "sugerida"}>{modo === "sugerida" && "✓"}</span>
          <span><span className={`block font-brand text-[13px] font-bold ${modo !== "sugerida" ? "text-faint" : ""}`}>Curva sugerida</span>
            <span className={`block font-sans text-[11.5px] ${modo !== "sugerida" ? "text-faint" : "text-muted"}`}>Indique el total y le sugeriremos la curva</span></span>
        </button>
      </div>
      {modo === "sugerida" && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md bg-[#fff0f7] px-4 py-3">
          <span className="font-brand text-[13px] font-bold text-pink">Indique aquí el total de unidades</span>
          <span className="ml-auto flex items-center gap-2 font-sans text-[12px] font-bold">Cantidad total:
            <QtyInput value={totalCurva} onChange={setTotalCurva} pink className="!h-[34px] !min-w-[72px] text-[14px]" placeholder="" />
            <span className="font-normal">u.</span>
            <button type="button" onClick={sugerir} disabled={curvaBusy || totalCurva <= 0} className="btn btn-primary !rounded-full !p-0 h-[34px] w-[34px]" aria-label="Sugerir curva"><Chevron size={18} /></button>
          </span>
        </div>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="vt">
          <thead>
            <tr><th>Variante</th>{talles.map((t) => <th key={t} className="!px-1 text-center whitespace-nowrap">T. {t}</th>)}</tr>
          </thead>
          <tbody>
            {colores.map((c) => (
              <tr key={c.color}>
                <td className="whitespace-nowrap"><span className="inline-flex items-center gap-2"><span className="swatch" style={{ background: c.hex }} /><b className="font-semibold">{capital(c.color)}</b></span></td>
                {talles.map((t) => {
                  const v = skuDe(c.color, t);
                  return (
                    <td key={t} className={`!px-1 text-center ${v?.disponible ? "" : "bg-[#f7f7f7]"}`}>
                      {v?.disponible ? (
                        <span className="inline-flex items-start gap-[3px]">
                          <span><QtyInput value={cants[v.sku] || 0} onChange={(n) => set(v.sku, n)} className={`!min-w-[38px] !w-[44px] !px-1 ${maximos[v.sku] !== undefined ? "!border-[#aa0b56]" : ""}`} />{maxHint(v.sku)}</span>
                          <span className="mt-[7px] font-sans text-[10px] text-muted">u.</span>
                        </span>
                      ) : <Gris />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {recortada && <p className="mt-2 font-sans text-[12px] text-[#aa0b56]">No hay disponibilidad para todo el total pedido: la curva se armó con lo disponible.</p>}
      {p.ub && p.ub > 1 && <p className="mt-2 font-sans text-[11.5px] text-muted">Este producto se vende en múltiplos de {p.ub} unidades.</p>}
      {modo === "sugerida" && total > 0 && <p className="mt-2 font-sans text-[12px] text-muted">Curva sugerida: {total} u. repartidas por talle y color según lo disponible (descontando lo que ya tenés en el carrito). Podés ajustarla a mano.</p>}
      {pie}
    </div>
  );
}
