"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { money } from "@/lib/format";
import { useToast } from "@/components/Toast";
import { Check, Field, H1, Kicker, Manual, Muted, Panel, Spinner, Tag } from "@/components/admin/ui";
import PedidoAdmin from "./PedidoAdmin";

interface Data {
  usuario: { email: string; rol: string; activo: boolean; cliente_cod: number | null; nombre_display: string; last_login_at: string | null };
  cliente: { nombre_display: string; lista_precios: number; lista_origen: string; descuento: number; descuento_origen: string; cuit: string | null; cuit_origen?: string; localidad: string | null; provincia_desc: string | null; contacto_nombre: string; contacto_email: string; contacto_telefono: string; notas?: string } | null;
  override: { descuento_pct?: number | null; lista_precios?: number | null; contacto_nombre?: string; contacto_email?: string; contacto_telefono?: string; cuit?: string | null; odoo_cliente?: string; notas?: string };
  metricas: { pedidos: number; cancelados: number; sin_procesar: number; unidades: number; total: number; ticket: number; ultimo: string; top: [string, string, number][] } | null;
  pedidos: { numero: number; fecha_str: string; estado: string; unidades: number; total: number }[];
  pv: { pv_cod: number; pv_nombre: string } | null;
  repo_dias_default: number;
}
interface Pwd { email: string; password: string; en_secret: boolean; aviso: string | null }

export default function ClienteAdmin({ email }: { email: string }) {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [edit, setEdit] = useState(false);
  const [pwd, setPwd] = useState<Pwd | null>(null);
  const [abierto, setAbierto] = useState<number | null>(null);
  const [impN, setImpN] = useState("3");
  const [impMsgs, setImpMsgs] = useState<string[] | null>(null);
  const [repoDias, setRepoDias] = useState<number | null>(null);
  const [repo, setRepo] = useState<{ items: { producto_cod: string; producto_nombre: string; color: string; talle: string; vendidas_30d: number; stock_pv: number; sugerido: number }[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  const [cuenta, setCuenta] = useState({ rol: "cliente", cliente_cod: "" });
  const [com, setCom] = useState({ usar_desc: false, desc: "", usar_lista: false, lista: "1", contacto_nombre: "", contacto_email: "", contacto_telefono: "", cuit: "", odoo_cliente: "", notas: "" });

  const cargar = useCallback(async () => {
    try {
      const x = await api<Data>(`/admin/clientes/${encodeURIComponent(email)}`); setD(x);
      setCuenta({ rol: x.usuario.rol, cliente_cod: x.usuario.cliente_cod?.toString() || "" });
      const o = x.override, e = x.cliente;
      setCom({ usar_desc: o.descuento_pct !== null && o.descuento_pct !== undefined, desc: String(o.descuento_pct ?? e?.descuento ?? 0), usar_lista: !!o.lista_precios, lista: String(o.lista_precios || e?.lista_precios || 1),
        contacto_nombre: o.contacto_nombre || "", contacto_email: o.contacto_email || "", contacto_telefono: o.contacto_telefono || "", cuit: o.cuit || "", odoo_cliente: o.odoo_cliente || "", notas: o.notas || "" });
    } catch (e) { setErr(e instanceof ClientError ? e.message : "Error"); }
  }, [email]);
  useEffect(() => { cargar(); }, [cargar]);

  async function accion(fn: () => Promise<void>, ok?: string) {
    setBusy(true);
    try { await fn(); if (ok) notify(ok); await cargar(); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  if (err) return <><H1>{email}</H1><p className="text-[#aa0b56]">{err}</p></>;
  if (!d) return <Spinner />;
  const u = d.usuario, e = d.cliente, m = d.metricas;
  const dato = (k: string, v: React.ReactNode, origen?: string) => <div><Kicker>{k}</Kicker><div className="font-brand text-[18px] font-bold">{v}</div>{origen && (origen === "Override" ? <Manual>Override</Manual> : <span className="font-sans text-[11px] text-muted">{origen}</span>)}</div>;

  return (
    <>
      <Link href="/admin/clientes" className="font-sans text-[12px] text-muted hover:text-ink">← Clientes</Link>
      <H1 right={!edit ? <button onClick={() => setEdit(true)} className="btn btn-primary">Editar</button> : null}>{e?.nombre_display || u.nombre_display || email}</H1>
      <Muted className="-mt-3 mb-5">{email} · rol {u.rol} · {u.activo ? "activo" : <b className="text-[#aa0b56]">DESACTIVADO</b>}{u.cliente_cod !== null ? <> · cliente {u.cliente_cod}</> : " · sin cliente asociado"}</Muted>

      {pwd && (
        <div className="mb-4 rounded border border-[#1d7a44] bg-[#e6f6ec] px-4 py-3 font-sans text-[13px]">
          Password de <b>{pwd.email}</b>: <code className="rounded bg-white px-2 py-[2px] font-mono">{pwd.password}</code> — guardala ahora{pwd.en_secret ? " (también quedó en el secret)." : "."}
          {pwd.aviso && <div className="mt-1 text-[#aa0b56]">{pwd.aviso}</div>}<button onClick={() => setPwd(null)} className="ml-3 underline">cerrar</button>
        </div>
      )}

      {edit ? (
        <div className="space-y-5">
          <Panel>
            <Kicker>Cuenta</Kicker><Muted className="mt-1">Rol y cliente de Aleph del usuario. Sin cliente asociado no puede hacer pedidos.</Muted>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
              <Field label="Rol"><select className="input" value={cuenta.rol} onChange={(ev) => setCuenta({ ...cuenta, rol: ev.target.value })}><option value="cliente">cliente</option><option value="admin">admin</option></select></Field>
              <Field label="cliente_cod de Aleph" hint="Vacío = sin cliente"><input className="input" inputMode="numeric" value={cuenta.cliente_cod} onChange={(ev) => setCuenta({ ...cuenta, cliente_cod: ev.target.value.replace(/\D/g, "") })} /></Field>
              <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/clientes/${encodeURIComponent(email)}/cuenta`, { method: "PUT", json: { rol: cuenta.rol, cliente_cod: cuenta.cliente_cod ? parseInt(cuenta.cliente_cod, 10) : null } }); }, "Cuenta actualizada")} className="btn btn-light self-end">Guardar cuenta</button>
            </div>
          </Panel>
          {u.cliente_cod !== null ? (
            <Panel>
              <Kicker>Datos comerciales (pisan a Aleph)</Kicker>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <div><Check checked={com.usar_desc} onChange={(v) => setCom({ ...com, usar_desc: v })} label="Override de descuento" /><input className="input mt-2" inputMode="decimal" disabled={!com.usar_desc} value={com.desc} onChange={(ev) => setCom({ ...com, desc: ev.target.value.replace(/[^\d.]/g, "") })} /><Muted>Aleph: {e?.descuento}%</Muted></div>
                <div><Check checked={com.usar_lista} onChange={(v) => setCom({ ...com, usar_lista: v })} label="Override de lista de precios" /><input className="input mt-2" inputMode="numeric" disabled={!com.usar_lista} value={com.lista} onChange={(ev) => setCom({ ...com, lista: ev.target.value.replace(/\D/g, "") })} /><Muted>Aleph: lista {e?.lista_precios}</Muted></div>
                <Field label="Persona de contacto"><input className="input" value={com.contacto_nombre} onChange={(ev) => setCom({ ...com, contacto_nombre: ev.target.value })} /></Field>
                <Field label="Email de contacto"><input className="input" value={com.contacto_email} onChange={(ev) => setCom({ ...com, contacto_email: ev.target.value })} /></Field>
                <Field label="Teléfono de contacto"><input className="input" value={com.contacto_telefono} onChange={(ev) => setCom({ ...com, contacto_telefono: ev.target.value })} placeholder="+54 9 ..." /></Field>
                <Field label="CUIT" hint={`Vacío = usa Aleph (${e?.cuit || "—"})`}><input className="input" value={com.cuit} onChange={(ev) => setCom({ ...com, cuit: ev.target.value })} /></Field>
                <Field label="Nombre del cliente en Odoo (export franquicias)" hint="Vacío = nombre de Aleph"><input className="input" value={com.odoo_cliente} onChange={(ev) => setCom({ ...com, odoo_cliente: ev.target.value })} /></Field>
                <Field label="Notas"><input className="input" value={com.notas} onChange={(ev) => setCom({ ...com, notas: ev.target.value })} /></Field>
              </div>
              <div className="mt-4 flex gap-3">
                <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/clientes/${encodeURIComponent(email)}/comercial`, { method: "PUT", json: { descuento_pct: com.usar_desc ? parseFloat(com.desc || "0") : null, lista_precios: com.usar_lista ? parseInt(com.lista || "1", 10) : null, contacto_nombre: com.contacto_nombre, contacto_email: com.contacto_email, contacto_telefono: com.contacto_telefono, cuit: com.cuit || null, odoo_cliente: com.odoo_cliente, notas: com.notas } }); setEdit(false); }, "Cliente guardado")} className="btn btn-primary">Guardar</button>
                <button onClick={() => { setEdit(false); cargar(); }} className="btn btn-light">Descartar</button>
              </div>
            </Panel>
          ) : <Muted>Sin cliente asociado no hay datos comerciales para editar. <button onClick={() => setEdit(false)} className="underline">Volver a la vista</button></Muted>}
        </div>
      ) : (
        <div className="space-y-5">
          {e && (
            <Panel>
              <div className="grid gap-4 sm:grid-cols-4">
                {dato("Lista de precios", e.lista_precios, e.lista_origen)}
                {dato("Descuento cabecera", `${e.descuento}%`, e.descuento_origen)}
                {dato("CUIT", e.cuit || "—", e.cuit_origen)}
                {dato("Ubicación", `${e.localidad || "—"}${e.provincia_desc ? ` · ${e.provincia_desc}` : ""}`)}
              </div>
              <div className="mt-4"><Kicker>Contacto</Kicker><div className="font-sans text-[13px]">{[e.contacto_nombre, e.contacto_email, e.contacto_telefono].filter(Boolean).join(" · ") || <span className="text-muted">sin cargar — se pide al confirmar un pedido</span>}</div></div>
              {e.notas && <Muted className="mt-2">Notas: {e.notas}</Muted>}
            </Panel>
          )}
          {u.cliente_cod === null ? (
            <Panel>{u.rol === "admin" ? <Muted>Usuario administrador, sin historial de pedidos.</Muted> : <div className="rounded bg-[#fff6d6] px-3 py-2 font-sans text-[13px]">Usuario cliente SIN cliente de Aleph asociado: no puede hacer pedidos. Entrá a «Editar» y asignale el cliente_cod en Cuenta.</div>}</Panel>
          ) : m && (
            <>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {[["Pedidos", m.pedidos], ["Unidades", m.unidades.toLocaleString("es-AR")], ["Total histórico", money(m.total)], ["Ticket promedio", money(m.ticket)], ["Último pedido", m.ultimo], ["Cancelados", m.cancelados]].map(([l, v]) => (
                  <div key={String(l)} className="border-t-2 border-ink bg-white px-3 pb-3 pt-2"><div className="font-sans text-[11px] text-muted">{l}</div><div className="font-brand text-[18px] font-bold">{v}</div></div>
                ))}
              </div>
              <div className="grid gap-5 lg:grid-cols-[1fr_1.6fr]">
                <Panel>
                  <Kicker>Top productos</Kicker>
                  {m.top.length ? m.top.map(([c, n, uds]) => <div key={c} className="flex justify-between border-b border-line py-2 font-sans text-[13px]"><span>{n} <Link href={`/admin/catalogo/${c}`} className="text-muted hover:underline">{c}</Link></span><span>{uds} u.</span></div>) : <Muted className="mt-2">Sin compras todavía.</Muted>}
                </Panel>
                <Panel className="!p-0">
                  <div className="px-5 pt-5"><Kicker>Pedidos · click para ver el detalle</Kicker></div>
                  <table className="mt-2 w-full font-sans text-[13px]">
                    <thead><tr className="border-b border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-5 py-2">N°</th><th className="py-2">Fecha</th><th className="py-2 text-right">Unid.</th><th className="py-2 text-right">Total</th><th className="py-2 pl-4">Estado</th></tr></thead>
                    <tbody>{d.pedidos.map((p) => <tr key={p.numero} onClick={() => setAbierto(abierto === p.numero ? null : p.numero)} className={`cursor-pointer border-b border-line hover:bg-[#fafafa] ${abierto === p.numero ? "bg-[#f3fbff]" : ""}`}><td className="px-5 py-2 font-bold">{String(p.numero).padStart(6, "0")}</td><td className="py-2">{p.fecha_str}</td><td className="py-2 text-right">{p.unidades}</td><td className="py-2 text-right">{money(p.total)}</td><td className="py-2 pl-4"><Tag estado={p.estado} /></td></tr>)}
                      {d.pedidos.length === 0 && <tr><td colSpan={5} className="p-5 text-muted">Sin pedidos todavía.</td></tr>}</tbody>
                  </table>
                </Panel>
              </div>
              {abierto && <PedidoAdmin numero={abierto} onChange={cargar} />}
              <Panel>
                <details>
                  <summary className="cursor-pointer font-brand text-[14px] font-bold">Importar historial de Aleph</summary>
                  <Muted className="mt-2">Trae los últimos N comprobantes de venta del cliente (NP y facturas, sin anulados) desde el espejo del ERP y los crea como pedidos «procesados», con Excel y backup. Los ya importados se saltean: pedir de nuevo NUNCA duplica.</Muted>
                  <div className="mt-3 flex items-center gap-3"><input className="input !w-[90px]" inputMode="numeric" value={impN} onChange={(ev) => setImpN(ev.target.value.replace(/\D/g, ""))} /><button disabled={busy} onClick={() => accion(async () => { const r = await api<{ mensajes: string[] }>(`/admin/clientes/${encodeURIComponent(email)}/importar-aleph`, { method: "POST", json: { n: parseInt(impN || "3", 10) } }); setImpMsgs(r.mensajes); })} className="btn btn-light">{busy ? "Importando…" : "Importar de Aleph"}</button></div>
                  {impMsgs && <ul className="mt-3 list-disc pl-5 font-sans text-[12.5px]">{impMsgs.map((x, i) => <li key={i}>{x}</li>)}</ul>}
                </details>
              </Panel>
              {d.pv && (
                <Panel>
                  <details>
                    <summary className="cursor-pointer font-brand text-[14px] font-bold">Reposición sugerida hoy — {d.pv.pv_nombre}</summary>
                    <Muted className="mt-2">Lo que el sitio le sugeriría hoy a esta franquicia (velocidad de venta de los últimos 30 días).</Muted>
                    <div className="mt-3 flex flex-wrap items-center gap-2 font-sans text-[12px] font-bold">Días a cubrir:
                      {Array.from(new Set([7, 14, 21, 30, d.repo_dias_default])).sort((a, b) => a - b).map((x) => <button key={x} onClick={() => setRepoDias(x)} className={`pill !py-[4px] ${(repoDias ?? d.repo_dias_default) === x ? "!border-ink !bg-ink !text-white" : ""}`}>{x}</button>)}
                      <button disabled={busy} onClick={() => accion(async () => { setRepo(await api(`/admin/clientes/${encodeURIComponent(email)}/reposicion?dias=${repoDias ?? d.repo_dias_default}`)); })} className="btn btn-light btn-sm">Calcular</button>
                    </div>
                    {repo && (repo.items.length === 0 ? <Muted className="mt-3">Nada para reponer hoy.</Muted> : (
                      <table className="vt mt-3 text-[12.5px]"><thead><tr><th>Código</th><th>Producto</th><th>Color</th><th>Talle</th><th className="text-right">Vendió 30d</th><th className="text-right">Tiene</th><th className="text-right">Sugerido</th></tr></thead>
                        <tbody>{repo.items.map((r, i) => <tr key={i}><td>{r.producto_cod}</td><td>{r.producto_nombre}</td><td>{r.color}</td><td>{r.talle}</td><td className="text-right">{r.vendidas_30d}</td><td className="text-right">{r.stock_pv}</td><td className="text-right font-bold">{r.sugerido}</td></tr>)}</tbody></table>
                    ))}
                  </details>
                </Panel>
              )}
            </>
          )}
          <Panel>
            <Kicker>Acciones instantáneas (no pasan por Guardar)</Kicker>
            <div className="mt-3 flex flex-wrap gap-3">
              <button disabled={busy} onClick={() => accion(async () => { setPwd(await api<Pwd>(`/admin/clientes/${encodeURIComponent(email)}/reset-password`, { method: "POST" })); })} className="btn btn-light">Resetear password</button>
              <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/clientes/${encodeURIComponent(email)}/activo`, { method: "POST", json: { activo: !u.activo } }); }, u.activo ? "Usuario desactivado" : "Usuario activado")} className={`btn ${u.activo ? "btn-ghost text-[#aa0b56]" : "btn-primary"}`}>{u.activo ? "Desactivar usuario" : "Activar usuario"}</button>
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
