"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Carrito, Me, Pedido } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { Chevron, XIcon } from "./Brand";
import Thumb from "./Thumb";
import { useCart } from "./CartContext";
import { useToast } from "./Toast";
import QtyInput from "./QtyInput";
import { capital } from "./ProductCard";

const DEBOUNCE_MS = 500;

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

  // Cantidades que el usuario está tipeando, por SKU. Se mandan al confirmar (blur/Enter) o tras un debounce;
  // mientras tanto el input muestra el borrador y no lo que devuelve la API.
  const [borrador, setBorrador] = useState<Record<string, number>>({});
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  // Cada request de carrito lleva un número; solo se aplica la respuesta del último (las anteriores pueden llegar después).
  const seq = useRef(0);

  useEffect(() => {
    const ts = timers.current;
    return () => Object.values(ts).forEach(clearTimeout);
  }, []);

  function aplicar(d: Carrito, mio: number) {
    if (mio !== seq.current) return false;
    setC(d); setUnidades(d.totales.unidades);
    return true;
  }
  const sinBorrador = (sku: string) => setBorrador((b) => { if (!(sku in b)) return b; const rest = { ...b }; delete rest[sku]; return rest; });

  useEffect(() => {
    const mio = ++seq.current;
    api<Carrito>("/carrito").then((d) => { if (mio === seq.current) { setC(d); setUnidades(d.totales.unidades); } }).catch((e) => setErr(e.message));
  }, [setUnidades]);

  async function fijar(sku: string, n: number) {
    const mio = ++seq.current;
    try {
      const d = await api<Carrito>(`/carrito/items/${encodeURIComponent(sku)}`, { method: "PUT", json: { cantidad: n } });
      if (aplicar(d, mio)) d.avisos.forEach((a) => notify(a, "aviso"));
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { sinBorrador(sku); }
  }

  function cancelarTimer(sku: string) {
    if (timers.current[sku]) { clearTimeout(timers.current[sku]); delete timers.current[sku]; }
  }
  function tipear(sku: string, n: number) {
    setBorrador((b) => ({ ...b, [sku]: n }));
    cancelarTimer(sku);
    if (n > 0) timers.current[sku] = setTimeout(() => confirmarCantidad(sku, n), DEBOUNCE_MS);
  }
  function confirmarCantidad(sku: string, n: number) {
    cancelarTimer(sku);
    const actual = c?.items.find((i) => i.sku === sku)?.cantidad;
    if (n > 0 && n !== actual) fijar(sku, n);
    else sinBorrador(sku);
  }

  async function vaciar() {
    const mio = ++seq.current;
    try {
      const d = await api<Carrito>("/carrito", { method: "DELETE" });
      aplicar(d, mio);
    } catch (e) { notify(e instanceof ClientError ? e.message : "No se pudo vaciar el carrito.", "error"); }
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
        if (e.status === 409) { const mio = ++seq.current; const d = await api<Carrito>("/carrito"); aplicar(d, mio); }
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

  const minUnidades = c?.minimo_unidades ?? 0;
  const minMonto = c?.minimo_monto ?? 0;

  return (
    <div className="container-lt pb-10 pt-8">
      <h1 className="font-brand text-[28px] font-extrabold">Tu carrito</h1>
      {err && <p className="mt-4 rounded-md border border-[#f3b7cc] bg-[#fff1f4] px-4 py-3 font-sans text-[13px] text-[#aa0b56]">{err}</p>}
      {!c && !err && <div className="mt-6 flex h-40 items-center justify-center bg-white font-sans text-[13px] text-muted">Cargando tu carrito…</div>}
      {c && c.items.length === 0 && (
        <div className="mt-6 bg-white p-12 text-center">
          <p className="font-sans text-[15px]">Tu carrito está vacío.</p>
          <Link href="/h/marro" className="btn btn-primary mt-5">Ir al catálogo <Chevron size={15} /></Link>
        </div>
      )}
      {c && c.items.length > 0 && (
        <div className="mt-6 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 bg-white">
            <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
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
                    <td className="px-2 py-3 text-center">
                      <QtyInput value={borrador[it.sku] ?? it.cantidad} onChange={(n) => tipear(it.sku, n)}
                        onCommit={() => confirmarCantidad(it.sku, borrador[it.sku] ?? it.cantidad)} />
                    </td>
                    <td className="px-2 py-3 text-right">{it.pct_desc > 0 && it.precio_lista ? <div className="price-old">{money(it.precio_lista)}</div> : null}{money(it.precio_unit)}</td>
                    <td className="px-2 py-3 text-right font-bold">{money(it.subtotal)}</td>
                    <td className="py-3 pr-3 text-right"><button onClick={() => { cancelarTimer(it.sku); fijar(it.sku, 0); }} className="text-faint hover:text-ink" aria-label="Quitar"><XIcon size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <div className="flex justify-between p-4">
              <Link href="/h/marro" className="font-sans text-[12px] hover:underline">‹ Seguir comprando</Link>
              <button onClick={vaciar} className="font-sans text-[12px] text-muted hover:text-ink">Vaciar carrito</button>
            </div>
          </div>
          <div>
            <div className="bg-white p-6">
              <h2 className="font-brand text-[16px] font-bold">Resumen</h2>
              <Resumen t={c.totales} />
              {minUnidades > 0 && c.totales.unidades < minUnidades && <p className="mt-3 font-sans text-[12px] text-[#aa0b56]">El pedido mínimo es de {minUnidades} unidades.</p>}
              {minMonto > 0 && c.totales.subtotal < minMonto && <p className="mt-3 font-sans text-[12px] text-[#aa0b56]">El pedido mínimo es de {money(minMonto)} a precio de lista.</p>}
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
