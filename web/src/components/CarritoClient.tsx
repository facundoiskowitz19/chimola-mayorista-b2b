"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Carrito, Me, Pedido } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { Chevron, XIcon } from "./Brand";
import Thumb from "./Thumb";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import QtyInput from "./QtyInput";
import { capital } from "./ProductCard";

export default function CarritoClient({ me }: { me: Me }) {
  const [c, setC] = useState<Carrito | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { setUnidades } = useCart();
  const { notify } = useToast();
  const cli = me.cliente;
  const [contacto, setContacto] = useState({ contacto_nombre: cli?.contacto_nombre || "", contacto_email: cli?.contacto_email || me.user.email, contacto_telefono: cli?.contacto_telefono || "" });
  const [obs, setObs] = useState("");

  useEffect(() => {
    api<Carrito>("/carrito").then((d) => { setC(d); setUnidades(d.totales.unidades); }).catch((e) => setErr(e.message));
  }, [setUnidades]);

  async function fijar(sku: string, n: number) {
    try {
      const d = await api<Carrito>(`/carrito/items/${encodeURIComponent(sku)}`, { method: "PUT", json: { cantidad: n } });
      d.avisos.forEach((a) => notify(a, "aviso"));
      setC(d); setUnidades(d.totales.unidades);
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
  }

  async function confirmar(e: React.FormEvent) {
    e.preventDefault();
    if (!c || busy) return;
    setBusy(true); setErr(null);
    try {
      const p = await api<Pedido>("/pedidos", { method: "POST", json: { ...contacto, observaciones: obs } });
      setPedido(p); setUnidades(0);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      if (e instanceof ClientError) {
        setErr(e.message);
        if (e.status === 409) { const d = await api<Carrito>("/carrito"); setC(d); }
      } else setErr("No pudimos confirmar el pedido. Probá de nuevo.");
    } finally { setBusy(false); }
  }

  if (!me.puede_pedir) {
    return <div className="container-lt py-16 text-center font-sans">Tu usuario no tiene un cliente asociado para hacer pedidos.</div>;
  }

  if (pedido) {
    return (
      <div className="container-lt py-12">
        <div className="mx-auto max-w-[720px] bg-white p-10">
          <p className="kicker text-green">Pedido confirmado</p>
          <h1 className="mt-2 font-brand text-[30px] font-extrabold">Pedido N° {String(pedido.numero).padStart(6, "0")}</h1>
          <p className="mt-3 font-sans text-[14px] leading-relaxed">
            Te enviamos el detalle con el Excel adjunto a <b>{pedido.contacto_email || me.user.email}</b>
            {pedido.email && !pedido.email.enviado && <span className="text-[#aa0b56]"> (el email no pudo enviarse: {pedido.email.error})</span>}.
            Lautin coordina entrega y facturación.
          </p>
          <Resumen t={pedido} />
          <div className="mt-8 flex flex-wrap gap-3">
            <a href={`/api/pedidos/${pedido.numero}/excel`} className="btn btn-primary">Descargar Excel <Chevron size={15} /></a>
            {pedido.odoo && <a href={`/api/pedidos/${pedido.numero}/odoo`} className="btn btn-light">Excel para Odoo <Chevron size={15} /></a>}
            <Link href="/pedidos" className="btn btn-light">Ver mis pedidos</Link>
            <Link href="/h/marro" className="btn btn-ghost">Seguir comprando</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container-lt pb-10 pt-8">
      <h1 className="font-brand text-[28px] font-extrabold">Tu carrito</h1>
      {err && <p className="mt-4 rounded-md border border-[#f3b7cc] bg-[#fff1f4] px-4 py-3 font-sans text-[13px] text-[#aa0b56]">{err}</p>}
      {!c && !err && <div className="mt-6 h-40 animate-pulse bg-white" />}
      {c && c.items.length === 0 && (
        <div className="mt-6 bg-white p-12 text-center">
          <p className="font-sans text-[15px]">Tu carrito está vacío.</p>
          <Link href="/h/marro" className="btn btn-primary mt-5">Ir al catálogo <Chevron size={15} /></Link>
        </div>
      )}
      {c && c.items.length > 0 && (
        <div className="mt-6 grid items-start gap-8 lg:grid-cols-[1fr_340px]">
          <div className="bg-white">
            <table className="w-full">
              <thead>
                <tr className="border-b-2 border-ink font-sans text-[11px] uppercase text-ink-2">
                  <th className="px-4 py-3 text-left" colSpan={2}>Producto</th><th className="px-2 py-3 text-left">Variante</th>
                  <th className="px-2 py-3 text-center">Cantidad</th><th className="px-2 py-3 text-right">Precio</th><th className="px-2 py-3 text-right">Subtotal</th><th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {c.items.map((it) => (
                  <tr key={it.sku} className="border-b border-line font-sans text-[13px]">
                    <td className="w-[72px] py-3 pl-4">
                      <Thumb src={it.foto} className="h-[60px] w-[60px] bg-white object-contain" />
                    </td>
                    <td className="py-3 pr-2"><Link href={`/p/${it.producto_cod}`} className="font-brand text-[13px] font-bold hover:underline">{it.producto_nombre}</Link>
                      <div className="card-meta"><b>{it.producto_cod}</b>{it.manual && <span className="ml-2 text-[#aa0b56]">variante manual</span>}</div></td>
                    <td className="px-2 py-3">{capital(it.color)}{it.talle !== "U" && <span className="text-muted"> · Talle {it.talle}</span>}</td>
                    <td className="px-2 py-3 text-center"><QtyInput value={it.cantidad} onChange={(n) => n > 0 && n !== it.cantidad && fijar(it.sku, n)} /></td>
                    <td className="px-2 py-3 text-right">{it.pct_desc > 0 && it.precio_lista ? <div className="price-old">{money(it.precio_lista)}</div> : null}{money(it.precio_unit)}</td>
                    <td className="px-2 py-3 text-right font-bold">{money(it.subtotal)}</td>
                    <td className="py-3 pr-3 text-right"><button onClick={() => fijar(it.sku, 0)} className="text-faint hover:text-ink" aria-label="Quitar"><XIcon size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-between p-4">
              <Link href="/h/marro" className="font-sans text-[12px] hover:underline">‹ Seguir comprando</Link>
              <button onClick={async () => { const d = await api<Carrito>("/carrito", { method: "DELETE" }); setC(d); }} className="font-sans text-[12px] text-muted hover:text-ink">Vaciar carrito</button>
            </div>
          </div>
          <div>
            <div className="bg-white p-6">
              <h2 className="font-brand text-[16px] font-bold">Resumen</h2>
              <Resumen t={c.totales} />
              {c.minimo_unidades && c.totales.unidades < c.minimo_unidades && <p className="mt-3 font-sans text-[12px] text-[#aa0b56]">El pedido mínimo es de {c.minimo_unidades} unidades.</p>}
              {c.minimo_monto && c.totales.subtotal < c.minimo_monto && <p className="mt-3 font-sans text-[12px] text-[#aa0b56]">El pedido mínimo es de {money(c.minimo_monto)} a precio de lista.</p>}
            </div>
            <form onSubmit={confirmar} className="mt-4 bg-white p-6">
              <h2 className="font-brand text-[16px] font-bold">Datos de contacto</h2>
              <p className="mt-1 font-sans text-[11.5px] text-muted">Si los cambiás, quedan guardados para la próxima.</p>
              <label className="mt-4 block font-sans text-[12px]">Nombre<input className="input mt-1" value={contacto.contacto_nombre} onChange={(e) => setContacto({ ...contacto, contacto_nombre: e.target.value })} /></label>
              <label className="mt-3 block font-sans text-[12px]">Email<input type="email" className="input mt-1" value={contacto.contacto_email} onChange={(e) => setContacto({ ...contacto, contacto_email: e.target.value })} /></label>
              <label className="mt-3 block font-sans text-[12px]">Teléfono<input className="input mt-1" value={contacto.contacto_telefono} onChange={(e) => setContacto({ ...contacto, contacto_telefono: e.target.value })} /></label>
              <label className="mt-3 block font-sans text-[12px]">Observaciones<textarea className="input mt-1 min-h-[70px]" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Aclaraciones para el equipo de Lautin" /></label>
              <button type="submit" disabled={busy} className="btn btn-primary mt-5 w-full justify-between !py-4 !text-[15px]">
                <span>{busy ? "Confirmando…" : "Confirmar pedido"}</span><Chevron size={18} />
              </button>
              <p className="mt-3 font-sans text-[11px] leading-snug text-muted">Sin pago online. Recibís el Excel por email y Lautin coordina entrega y facturación.</p>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function Resumen({ t }: { t: { unidades: number; subtotal: number; ahorro_descvta: number; descuento_pct: number; descuento_monto: number; total: number; iva_pct: number; iva_monto: number; total_con_iva: number } }) {
  const row = (l: React.ReactNode, v: React.ReactNode, cls = "") => <div className={`flex justify-between font-sans text-[13px] ${cls}`}><span>{l}</span><span>{v}</span></div>;
  return (
    <div className="mt-4 space-y-2">
      {row("Unidades", t.unidades)}
      {t.ahorro_descvta > 0 && row("Ahorro por ofertas", `− ${money(t.ahorro_descvta)}`, "text-red")}
      {row("Subtotal", money(t.subtotal))}
      {t.descuento_pct > 0 && row(`Descuento ${Math.round(t.descuento_pct)}%`, `− ${money(t.descuento_monto)}`)}
      <div className="flex justify-between border-t-2 border-ink pt-2 font-brand text-[16px] font-bold"><span>TOTAL</span><span>{money(t.total)}</span></div>
      {t.iva_pct > 0 && <>
        {row(`IVA ${Math.round(t.iva_pct)}%`, money(t.iva_monto), "text-muted")}
        {row("Total c/IVA", money(t.total_con_iva), "text-muted")}
      </>}
    </div>
  );
}
