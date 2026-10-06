"use client";
import { useState } from "react";
import type { Me } from "@/lib/types";
import { api, ClientError } from "@/lib/client";
import { useToast } from "./Toast";

export default function MisDatosClient({ me }: { me: Me }) {
  const { notify } = useToast();
  const cli = me.cliente;
  const [contacto, setContacto] = useState({ contacto_nombre: cli?.contacto_nombre || "", contacto_email: cli?.contacto_email || "", contacto_telefono: cli?.contacto_telefono || "" });
  const [pwd, setPwd] = useState({ actual: "", nueva: "", repetir: "" });
  const [busy, setBusy] = useState(false);

  async function guardarContacto(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await api("/cuenta/contacto", { method: "PUT", json: contacto }); notify("Datos de contacto guardados."); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }
  async function cambiarPwd(e: React.FormEvent) {
    e.preventDefault();
    if (pwd.nueva !== pwd.repetir) { notify("Las contraseñas no coinciden", "error"); return; }
    setBusy(true);
    try { await api("/cuenta/password", { method: "POST", json: { actual: pwd.actual, nueva: pwd.nueva } }); notify("Contraseña actualizada."); setPwd({ actual: "", nueva: "", repetir: "" }); }
    catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  const dato = (l: string, v: React.ReactNode) => <div className="flex justify-between gap-4 border-b border-line py-2 font-sans text-[13px]"><span className="text-muted">{l}</span><span className="text-right font-medium">{v || "—"}</span></div>;

  return (
    <div className="container-lt pb-10 pt-8">
      <h1 className="font-brand text-[28px] font-extrabold">Mis datos</h1>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="bg-white p-6">
          <h2 className="font-brand text-[16px] font-bold">Cuenta</h2>
          <div className="mt-3">
            {dato("Usuario", me.user.email)}
            {cli && dato("Razón social", cli.nombre)}
            {cli && dato("Código de cliente", cli.cliente_cod)}
            {cli?.cuit && dato("CUIT", cli.cuit)}
            {cli && dato("Lista de precios", `Lista ${cli.lista_precios}`)}
            {cli && dato("Descuento", `${Math.round(cli.descuento)}%`)}
            {cli?.localidad && dato("Ubicación", `${cli.localidad}${cli.provincia ? `, ${cli.provincia}` : ""}`)}
          </div>
          <p className="mt-3 font-sans text-[11.5px] text-muted">Estos datos vienen del sistema de Lautin. Si algo está mal, avisanos por WhatsApp.</p>
        </section>
        {cli && (
          <form onSubmit={guardarContacto} className="bg-white p-6">
            <h2 className="font-brand text-[16px] font-bold">Contacto para pedidos</h2>
            <label className="mt-4 block font-sans text-[12px]">Nombre<input className="input mt-1" value={contacto.contacto_nombre} onChange={(e) => setContacto({ ...contacto, contacto_nombre: e.target.value })} /></label>
            <label className="mt-3 block font-sans text-[12px]">Email<input type="email" className="input mt-1" value={contacto.contacto_email} onChange={(e) => setContacto({ ...contacto, contacto_email: e.target.value })} /></label>
            <label className="mt-3 block font-sans text-[12px]">Teléfono<input className="input mt-1" value={contacto.contacto_telefono} onChange={(e) => setContacto({ ...contacto, contacto_telefono: e.target.value })} /></label>
            <button type="submit" disabled={busy} className="btn btn-primary mt-5">Guardar</button>
          </form>
        )}
        <form onSubmit={cambiarPwd} className="bg-white p-6">
          <h2 className="font-brand text-[16px] font-bold">Cambiar contraseña</h2>
          <label className="mt-4 block font-sans text-[12px]">Contraseña actual<input type="password" className="input mt-1" value={pwd.actual} onChange={(e) => setPwd({ ...pwd, actual: e.target.value })} required /></label>
          <label className="mt-3 block font-sans text-[12px]">Nueva (mín. 8)<input type="password" className="input mt-1" value={pwd.nueva} onChange={(e) => setPwd({ ...pwd, nueva: e.target.value })} minLength={8} required /></label>
          <label className="mt-3 block font-sans text-[12px]">Repetir nueva<input type="password" className="input mt-1" value={pwd.repetir} onChange={(e) => setPwd({ ...pwd, repetir: e.target.value })} required /></label>
          <button type="submit" disabled={busy} className="btn btn-primary mt-5">Actualizar</button>
        </form>
      </div>
    </div>
  );
}
