"use client";
/* Detalle + acciones de un pedido (Pedidos y ficha de cliente). */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import type { Pedido } from "@/lib/types";
import { money } from "@/lib/format";
import { useToast } from "@/components/Toast";
import Thumb from "@/components/Thumb";
import { Resumen } from "@/components/CarritoClient";
import { Check, Kicker, Muted, Panel, Spinner, Tag } from "./ui";

const SIGUIENTES: Record<string, string[]> = { confirmado: ["procesado", "cancelado"], procesado: ["cancelado"], cancelado: [] };

export default function PedidoAdmin({ numero, onChange }: { numero: number; onChange?: () => void }) {
  const [p, setP] = useState<Pedido | null>(null);
  const [busy, setBusy] = useState(false);
  const [mod, setMod] = useState<Record<string, { cantidad: string; quitar: boolean }> | null>(null);
  const { notify } = useToast();

  const cargar = useCallback(async () => { setP(await api<Pedido>(`/pedidos/${numero}`)); }, [numero]);
  useEffect(() => { setP(null); setMod(null); cargar(); }, [cargar]);

  async function accion(fn: () => Promise<string | void>) {
    setBusy(true);
    try { const msg = await fn(); if (msg) notify(msg); await cargar(); onChange?.(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  if (!p) return <Spinner />;
  const contacto = [p.contacto_nombre, p.contacto_email, p.contacto_telefono].filter(Boolean).join(" · ");
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-brand text-[20px] font-bold">Pedido N° {String(p.numero).padStart(6, "0")}</h2><Tag estado={p.estado} />
      </div>
      <Muted className="mt-1">{p.fecha_str} · <b className="text-ink">{p.cliente_nombre}</b> (cliente <Link href={`/admin/clientes`} className="underline">{p.cliente_cod}</Link>) · {(p as unknown as { usuario_email: string }).usuario_email} · {p.unidades} u. · <b className="text-ink">{money(p.total)}</b> (desc. {p.descuento_pct}%)</Muted>
      {contacto && <Muted>Contacto del pedido: {contacto}</Muted>}
      {p.observaciones && <Muted>Obs: {p.observaciones}</Muted>}
      {p.historial?.map((h, i) => <Muted key={i}>{new Date(h.en).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} — <b className="text-ink">{h.estado}</b> por {h.por}{h.detalle && <span className="block whitespace-pre-line pl-4">{h.detalle}</span>}</Muted>)}

      <div className="mt-4 grid items-start gap-6 lg:grid-cols-[1fr_280px]">
        <table className="w-full font-sans text-[13px]">
          <thead><tr className="border-b border-ink text-left text-[11px] uppercase text-ink-2"><th className="py-2" colSpan={2}>Producto</th><th className="py-2">Variante</th><th className="py-2 text-right">Cant.</th><th className="py-2 text-right">Precio</th><th className="py-2 text-right">Subtotal</th>{mod && <th className="py-2 text-center">Nueva cant.</th>}</tr></thead>
          <tbody>{p.items.map((it) => (
            <tr key={it.sku} className="border-b border-line">
              <td className="w-[48px] py-2"><Thumb src={it.foto} className="h-[40px] w-[40px] object-contain" /></td>
              <td className="py-2"><Link href={`/admin/catalogo/${it.producto_cod}`} className="font-bold hover:underline">{it.producto_nombre}</Link><div className="card-meta"><b>{it.producto_cod}</b>{it.manual && <span className="ml-2 text-[#aa0b56]">variante manual</span>}</div></td>
              <td className="py-2">{it.color}{it.talle !== "U" && ` · Talle ${it.talle}`}</td>
              <td className="py-2 text-right">{it.cantidad}</td><td className="py-2 text-right">{money(it.precio_unit)}</td><td className="py-2 text-right font-bold">{money(it.subtotal)}</td>
              {mod && <td className="py-2 text-center"><span className="inline-flex items-center gap-2"><input className="input !w-[70px] !py-1 text-center" inputMode="numeric" value={mod[it.sku].cantidad} onChange={(e) => setMod({ ...mod, [it.sku]: { ...mod[it.sku], cantidad: e.target.value.replace(/\D/g, "") } })} /><Check checked={mod[it.sku].quitar} onChange={(v) => setMod({ ...mod, [it.sku]: { ...mod[it.sku], quitar: v } })} label="quitar" /></span></td>}
            </tr>
          ))}</tbody>
        </table>
        <div>
          <Resumen t={p} />
          <div className="mt-4 flex flex-col gap-2">
            {SIGUIENTES[p.estado]?.map((n) => <button key={n} disabled={busy} onClick={() => accion(async () => { await api(`/admin/pedidos/${p.numero}/estado`, { method: "POST", json: { nuevo: n } }); return `Pedido ${p.numero} → ${n}`; })} className={`btn ${n === "procesado" ? "btn-primary" : "btn-light"}`}>Marcar {n}</button>)}
            <button disabled={busy} onClick={() => accion(async () => { const r = await api<{ enviado: boolean; destinatarios: string[]; error: string }>(`/admin/pedidos/${p.numero}/reenviar`, { method: "POST" }); if (!r.enviado) throw new ClientError(500, r.error); return `Reenviado a ${r.destinatarios.join(", ")}`; })} className="btn btn-light">Reenviar email</button>
            <a href={`/api/pedidos/${p.numero}/excel`} className="btn btn-light">Descargar Excel</a>
          </div>
        </div>
      </div>

      {p.estado === "confirmado" ? (
        <div className="mt-5 border-t border-line pt-4">
          {!mod ? <button onClick={() => setMod(Object.fromEntries(p.items.map((it) => [it.sku, { cantidad: String(it.cantidad), quitar: false }])))} className="btn btn-light btn-sm">Modificar pedido (avisa al cliente)</button> : (
            <>
              <Kicker>Modificar pedido</Kicker>
              <Muted className="mt-1">Cambiá cantidades o marcá «quitar» (0 también quita). Solo antes de marcarlo procesado. Al guardar se recalculan los totales, se regenera el Excel y <b className="text-ink">se le avisa al cliente por email</b>.</Muted>
              <div className="mt-3 flex gap-2">
                <button disabled={busy} onClick={() => accion(async () => { const r = await api<{ email_modificado: { enviado: boolean } | null }>(`/admin/pedidos/${p.numero}/modificar`, { method: "POST", json: { cantidades: Object.fromEntries(Object.entries(mod).map(([sku, m]) => [sku, m.quitar ? 0 : parseInt(m.cantidad || "0", 10)])) } }); setMod(null); return `Pedido ${p.numero} modificado${r.email_modificado?.enviado ? " · cliente avisado" : " · email no salió"}`; })} className="btn btn-primary btn-sm">Guardar cambios y avisar al cliente</button>
                <button onClick={() => setMod(null)} className="btn btn-light btn-sm">Cancelar</button>
              </div>
            </>
          )}
        </div>
      ) : <Muted className="mt-4">Un pedido procesado o cancelado ya no se modifica. Para cambios, coordinalo por fuera o cancelá y rehacé.</Muted>}
    </Panel>
  );
}
