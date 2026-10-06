"use client";
import { useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Field, H1, Muted, Panel, Spinner, Toggle } from "@/components/admin/ui";

interface Cfg { pedidos_email_to: string | null; banner_texto: string; aplicar_descvta: boolean; minimo_pedido_unidades: number | null; minimo_pedido_monto: number | null; iva_pct: number; notificar_estados: boolean; repo_dias_objetivo: number }
interface Res { config: Cfg; default_email_to: string[]; catalogo_hace_seg: number; email_override_to: string }

export default function ConfigAdmin() {
  const [r, setR] = useState<Res | null>(null);
  const [f, setF] = useState<Record<string, string | boolean>>({});
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  async function cargar() {
    const d = await api<Res>("/admin/config"); setR(d);
    const c = d.config;
    setF({ pedidos_email_to: c.pedidos_email_to || "", banner_texto: c.banner_texto || "", aplicar_descvta: c.aplicar_descvta, minimo_pedido_unidades: c.minimo_pedido_unidades?.toString() || "", minimo_pedido_monto: c.minimo_pedido_monto?.toString() || "", iva_pct: String(c.iva_pct), notificar_estados: c.notificar_estados, repo_dias_objetivo: String(c.repo_dias_objetivo) });
  }
  useEffect(() => { cargar(); }, []);

  async function guardar(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try {
      await api("/admin/config", { method: "PUT", json: { pedidos_email_to: f.pedidos_email_to || null, banner_texto: f.banner_texto, aplicar_descvta: f.aplicar_descvta, minimo_pedido_unidades: f.minimo_pedido_unidades ? parseInt(f.minimo_pedido_unidades as string, 10) : null, minimo_pedido_monto: f.minimo_pedido_monto ? parseFloat(f.minimo_pedido_monto as string) : null, iva_pct: parseFloat((f.iva_pct as string) || "0"), notificar_estados: f.notificar_estados, repo_dias_objetivo: parseInt((f.repo_dias_objetivo as string) || "21", 10) } });
      notify("Configuración guardada"); await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }
  async function refrescar() {
    setBusy(true);
    try { await api("/admin/config/refrescar", { method: "POST" }); notify("Catálogo actualizado"); await cargar(); }
    finally { setBusy(false); }
  }

  if (!r) return <><H1>Config</H1><Spinner /></>;
  const s = (k: string) => f[k] as string;
  return (
    <>
      <H1>Config</H1>
      <Muted>Todo esto afecta a los clientes al instante una vez guardado. Nada se aplica hasta tocar «Guardar configuración».</Muted>
      <form onSubmit={guardar} className="mt-4 space-y-5">
        <Panel>
          <Field label="Emails de Lautin que reciben pedidos (separados por coma)" hint={`Vacío = default del deploy (${r.default_email_to.join(", ")})`}><input className="input" value={s("pedidos_email_to")} onChange={(e) => setF({ ...f, pedidos_email_to: e.target.value })} /></Field>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Mínimo de unidades por pedido" hint="Vacío = sin mínimo"><input className="input" inputMode="numeric" value={s("minimo_pedido_unidades")} onChange={(e) => setF({ ...f, minimo_pedido_unidades: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Mínimo de compra en $" hint="Sobre el subtotal a PRECIO DE LISTA (sin IVA ni descuento cabecera). Vacío = sin mínimo"><input className="input" inputMode="numeric" value={s("minimo_pedido_monto")} onChange={(e) => setF({ ...f, minimo_pedido_monto: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
            <Field label="IVA % informativo" hint="Las listas de Aleph son sin IVA; se muestra como línea aparte en carrito, Excel y email. 0 = ocultar"><input className="input" inputMode="decimal" value={s("iva_pct")} onChange={(e) => setF({ ...f, iva_pct: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
            <Field label="Reposición: días de venta a cubrir" hint="La página «Reposición» de las franquicias sugiere cantidades para cubrir esta cantidad de días"><input className="input" inputMode="numeric" value={s("repo_dias_objetivo")} onChange={(e) => setF({ ...f, repo_dias_objetivo: e.target.value.replace(/\D/g, "") })} /></Field>
          </div>
          <Field label="Banner para clientes" className="mt-4" hint="Se muestra arriba del catálogo hasta que vacíes el campo"><textarea className="input min-h-[70px]" value={s("banner_texto")} onChange={(e) => setF({ ...f, banner_texto: e.target.value })} /></Field>
          <div className="mt-4 space-y-3">
            <div><Toggle checked={!!f.aplicar_descvta} onChange={(v) => setF({ ...f, aplicar_descvta: v })} label="Aplicar descvta de Aleph" /><Muted className="ml-[48px]">El descuento por venta del ERP (por artículo), como lo usa el Woo</Muted></div>
            <div><Toggle checked={!!f.notificar_estados} onChange={(v) => setF({ ...f, notificar_estados: v })} label="Notificar cambios de estado por email" /><Muted className="ml-[48px]">Al cliente y a Lautin cuando un pedido pasa a procesado o cancelado</Muted></div>
          </div>
          <button type="submit" disabled={busy} className="btn btn-primary mt-5">Guardar configuración</button>
        </Panel>
      </form>
      <Panel className="mt-5">
        <div className="flex flex-wrap items-center gap-4">
          <button onClick={refrescar} disabled={busy} className="btn btn-light">Actualizar catálogo ahora</button>
          <Muted>Relee BigQuery y el índice de fotos{r.catalogo_hace_seg >= 0 && <> · último refresco hace {Math.round(r.catalogo_hace_seg / 60)} min</>}. El stock en sí lo materializa el pipeline a las 08:30.</Muted>
        </div>
        {r.email_override_to && <Muted className="mt-3">DEV: todos los emails se redirigen a {r.email_override_to}.</Muted>}
      </Panel>
    </>
  );
}
