"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Me, Pedido, PedidoResumen } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { Chevron } from "./Brand";
import Thumb from "./Thumb";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import { Resumen } from "./CarritoClient";
import { capital } from "./ProductCard";

const ESTADO: Record<string, { label: string; cls: string }> = {
  confirmado: { label: "Confirmado", cls: "bg-[#e9f8ff] text-[#006786]" },
  procesado: { label: "Procesado", cls: "bg-[#e6f6ec] text-[#1d7a44]" },
  cancelado: { label: "Cancelado", cls: "bg-[#fff1f4] text-[#aa0b56]" },
};

export default function PedidosClient({ me, lista }: { me: Me; lista: PedidoResumen[] }) {
  const [abierto, setAbierto] = useState<number | null>(null);
  const [det, setDet] = useState<Record<number, Pedido>>({});
  const [confirmCancel, setConfirmCancel] = useState<number | null>(null);
  const { setUnidades } = useCart();
  const { notify } = useToast();
  const router = useRouter();

  async function abrir(n: number) {
    if (abierto === n) { setAbierto(null); return; }
    setAbierto(n);
    if (!det[n]) { const d = await api<Pedido>(`/pedidos/${n}`); setDet((prev) => ({ ...prev, [n]: d })); }
  }
  async function repetir(n: number) {
    try {
      const r = await api<{ agregadas: number; avisos: string[] }>(`/pedidos/${n}/repetir`, { method: "POST" });
      r.avisos.forEach((a) => notify(a, "aviso"));
      notify(`Se cargaron ${r.agregadas} unidades al carrito.`);
      const c = await api<{ totales: { unidades: number } }>("/carrito"); setUnidades(c.totales.unidades);
      if (!r.avisos.length) router.push("/carrito");
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
  }
  async function cancelar(n: number) {
    try {
      const p = await api<Pedido>(`/pedidos/${n}/cancelar`, { method: "POST" });
      setDet((prev) => ({ ...prev, [n]: p })); setConfirmCancel(null);
      notify("Pedido cancelado."); router.refresh();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
  }

  return (
    <div className="container-lt pb-10 pt-8">
      <h1 className="font-brand text-[28px] font-extrabold">Mis pedidos</h1>
      {lista.length === 0 && <div className="mt-6 bg-white p-12 text-center font-sans">Todavía no hiciste pedidos. <Link href="/h/marro" className="font-bold underline">Ir al catálogo</Link></div>}
      <div className="mt-6 space-y-3">
        {lista.map((p) => {
          const e = ESTADO[p.estado] || { label: p.estado, cls: "bg-[#eee]" };
          const d = det[p.numero];
          return (
            <div key={p.numero} className="bg-white">
              <button onClick={() => abrir(p.numero)} className="grid w-full grid-cols-[90px_1fr_auto] items-center gap-4 px-5 py-4 text-left md:grid-cols-[90px_140px_1fr_110px_130px_28px]">
                <span className="font-brand text-[15px] font-bold">N° {String(p.numero).padStart(6, "0")}</span>
                <span className="font-sans text-[13px]">{p.fecha_str}</span>
                <span className="hidden font-sans text-[13px] md:block">{me.es_admin ? p.cliente_nombre : `${p.n_items} líneas · ${p.unidades} u.`}{p.observaciones && <span className="ml-2 text-muted">“{p.observaciones.slice(0, 60)}”</span>}</span>
                <span className={`hidden w-fit rounded-sm px-2 py-[3px] font-sans text-[11px] font-medium md:block ${e.cls}`}>{e.label}</span>
                <span className="text-right font-brand text-[15px] font-bold">{money(p.total)}</span>
                <span className="hidden text-faint md:block"><Chevron dir={abierto === p.numero ? "up" : "down"} size={18} /></span>
              </button>
              {abierto === p.numero && (
                <div className="fade-in border-t border-line px-5 pb-6 pt-4">
                  {!d && <div className="h-24 animate-pulse bg-[#f3f3f3]" />}
                  {d && (
                    <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
                      <div>
                        <table className="w-full font-sans text-[13px]">
                          <thead><tr className="border-b border-ink text-[11px] uppercase text-ink-2"><th className="py-2 text-left" colSpan={2}>Producto</th><th className="py-2 text-left">Variante</th><th className="py-2 text-right">Cant.</th><th className="py-2 text-right">Precio</th><th className="py-2 text-right">Subtotal</th></tr></thead>
                          <tbody>
                            {d.items.map((it) => (
                              <tr key={it.sku} className="border-b border-line">
                                <td className="w-[52px] py-2"><Thumb src={it.foto} className="h-[44px] w-[44px] object-contain" /></td>
                                <td className="py-2"><Link href={`/p/${it.producto_cod}`} className="font-bold hover:underline">{it.producto_nombre}</Link><div className="card-meta"><b>{it.producto_cod}</b></div></td>
                                <td className="py-2">{capital(it.color)}{it.talle !== "U" && ` · Talle ${it.talle}`}</td>
                                <td className="py-2 text-right">{it.cantidad}</td>
                                <td className="py-2 text-right">{money(it.precio_unit)}</td>
                                <td className="py-2 text-right font-bold">{money(it.subtotal)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {d.historial && d.historial.length > 0 && (
                          <ul className="mt-4 space-y-1 font-sans text-[11.5px] text-muted">
                            {d.historial.map((h, i) => <li key={i}>{new Date(h.en).toLocaleString("es-AR")} · {ESTADO[h.estado]?.label || h.estado} · {h.por}{h.detalle && <> · {h.detalle}</>}</li>)}
                          </ul>
                        )}
                      </div>
                      <div>
                        <Resumen t={d} />
                        <div className="mt-5 flex flex-col gap-2">
                          <a href={`/api/pedidos/${d.numero}/excel`} className="btn btn-primary justify-between">Descargar Excel <Chevron size={15} /></a>
                          {d.odoo && <a href={`/api/pedidos/${d.numero}/odoo`} className="btn btn-light justify-between">Excel para Odoo <Chevron size={15} /></a>}
                          {me.puede_pedir && <button onClick={() => repetir(d.numero)} className="btn btn-light justify-between">Repetir pedido <Chevron size={15} /></button>}
                          {d.puede_cancelar && confirmCancel !== d.numero && <button onClick={() => setConfirmCancel(d.numero)} className="btn btn-ghost text-[#aa0b56]">Cancelar pedido</button>}
                          {confirmCancel === d.numero && (
                            <div className="rounded-md border border-[#f3b7cc] bg-[#fff1f4] p-3 font-sans text-[12px]">
                              ¿Cancelar el pedido N° {d.numero}? Lautin recibe el aviso por email.
                              <div className="mt-2 flex gap-2"><button onClick={() => cancelar(d.numero)} className="btn btn-sm !bg-[#aa0b56] text-white">Sí, cancelar</button><button onClick={() => setConfirmCancel(null)} className="btn btn-light btn-sm">No</button></div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
