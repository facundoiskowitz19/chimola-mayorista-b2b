"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Field, H1, Muted, Panel, Spinner } from "@/components/admin/ui";

interface U { email: string; rol: string; activo: boolean; cliente_cod: number | null; nombre_display: string; last_login_at: string | null; cliente: { nombre_display: string; lista_precios: number; lista_origen: string; descuento: number; descuento_origen: string } | null }
interface Nuevo { email: string; password: string; en_secret: boolean; aviso: string | null }

export default function ClientesAdmin() {
  const [items, setItems] = useState<U[] | null>(null);
  const [q, setQ] = useState("");
  const [alta, setAlta] = useState(false);
  const [nuevo, setNuevo] = useState({ email: "", cliente_cod: "", nombre: "", rol: "cliente" });
  const [creado, setCreado] = useState<Nuevo | null>(null);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  useEffect(() => { api<{ items: U[] }>("/admin/clientes").then((d) => setItems(d.items)); }, []);

  async function crear(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try {
      const r = await api<Nuevo>("/admin/clientes", { method: "POST", json: { email: nuevo.email, cliente_cod: nuevo.cliente_cod ? parseInt(nuevo.cliente_cod, 10) : null, nombre: nuevo.nombre, rol: nuevo.rol } });
      setCreado(r); setAlta(false); setNuevo({ email: "", cliente_cod: "", nombre: "", rol: "cliente" });
      setItems((await api<{ items: U[] }>("/admin/clientes")).items);
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  const vis = (items || []).filter((u) => !q || `${u.email} ${u.nombre_display} ${u.cliente?.nombre_display || ""} ${u.cliente_cod || ""}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <H1 right={<button onClick={() => setAlta(!alta)} className="btn btn-primary">Nuevo usuario</button>}>Clientes</H1>
      <Muted>Click en un usuario para ver su ficha: pedidos, métricas y edición de lista, descuento y contacto.</Muted>
      {creado && (
        <div className="mt-4 rounded border border-[#1d7a44] bg-[#e6f6ec] px-4 py-3 font-sans text-[13px]">
          Password de <b>{creado.email}</b>: <code className="rounded bg-white px-2 py-[2px] font-mono">{creado.password}</code> — guardala ahora{creado.en_secret ? " (también quedó en el secret mayorista-seed-passwords)." : "."}
          {creado.aviso && <div className="mt-1 text-[#aa0b56]">{creado.aviso}</div>}
          <button onClick={() => setCreado(null)} className="ml-3 underline">cerrar</button>
        </div>
      )}
      {alta && (
        <Panel className="mt-4">
          <form onSubmit={crear} className="grid gap-3 sm:grid-cols-[1.4fr_1fr_1.4fr_0.8fr_auto]">
            <Field label="Email"><input className="input" type="email" required value={nuevo.email} onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })} /></Field>
            <Field label="cliente_cod de Aleph" hint="Vacío = sin cliente (solo admins)"><input className="input" inputMode="numeric" value={nuevo.cliente_cod} onChange={(e) => setNuevo({ ...nuevo, cliente_cod: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Nombre para mostrar" hint="Vacío = razón social de Aleph"><input className="input" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} /></Field>
            <Field label="Rol"><select className="input" value={nuevo.rol} onChange={(e) => setNuevo({ ...nuevo, rol: e.target.value })}><option value="cliente">cliente</option><option value="admin">admin</option></select></Field>
            <button type="submit" disabled={busy} className="btn btn-primary self-end">{busy ? "Creando…" : "Crear usuario"}</button>
          </form>
        </Panel>
      )}
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar email, nombre o código" className="input mt-4 !w-[360px]" />
      {!items ? <div className="mt-4"><Spinner /></div> : (
        <Panel className="mt-4 !p-0">
          <table className="w-full font-sans text-[13px]">
            <thead><tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-4 py-3">Email</th><th className="py-3">Rol</th><th className="py-3">Cliente</th><th className="py-3">Lista</th><th className="py-3">Desc %</th><th className="py-3">Último login</th></tr></thead>
            <tbody>
              {vis.map((u) => (
                <tr key={u.email} className={`border-b border-line hover:bg-[#fafafa] ${!u.activo ? "opacity-50" : ""}`}>
                  <td className="px-4 py-2"><Link href={`/admin/clientes/${encodeURIComponent(u.email)}`} className="font-bold hover:underline">{u.email}</Link>{!u.activo && <span className="ml-2 text-[11px] text-[#aa0b56]">desactivado</span>}</td>
                  <td className="py-2">{u.rol}</td>
                  <td className="py-2">{u.cliente_cod !== null ? <>{u.cliente?.nombre_display || u.nombre_display} <span className="text-muted">· {u.cliente_cod}</span></> : <span className="text-muted">—</span>}</td>
                  <td className="py-2">{u.cliente ? <>{u.cliente.lista_precios} <span className={u.cliente.lista_origen === "Override" ? "text-[#006786]" : "text-muted"}>({u.cliente.lista_origen})</span></> : "—"}</td>
                  <td className="py-2">{u.cliente ? <>{u.cliente.descuento}% <span className={u.cliente.descuento_origen === "Override" ? "text-[#006786]" : "text-muted"}>({u.cliente.descuento_origen})</span></> : "—"}</td>
                  <td className="py-2 text-muted">{u.last_login_at ? new Date(u.last_login_at).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </>
  );
}
