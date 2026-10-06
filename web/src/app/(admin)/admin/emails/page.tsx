"use client";
import { useEffect, useRef, useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Field, H1, Kicker, Muted, Panel, Pills, Spinner } from "@/components/admin/ui";

interface Tpl { formato: string; asunto: string; cuerpo: string }
interface Ev { evento: string; label: string; template: Tpl; default: Tpl; personalizado: boolean }
interface Res { eventos: Ev[]; variables: string[]; ejemplo: { numero: number; cliente_nombre: string; para: string; cc: string[]; adjunto: string }; admin_email: string }

export default function EmailsAdmin() {
  const [r, setR] = useState<Res | null>(null);
  const [ev, setEv] = useState("confirmacion");
  const [tpl, setTpl] = useState<Tpl>({ formato: "texto", asunto: "", cuerpo: "" });
  const [prev, setPrev] = useState<{ asunto: string; cuerpo: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);
  const { notify } = useToast();

  async function cargar(e = ev) {
    const d = await api<Res>("/admin/emails"); setR(d);
    const x = d.eventos.find((z) => z.evento === e)!; setTpl({ ...x.template });
  }
  useEffect(() => { cargar(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const t = setTimeout(async () => {
      if (!tpl.asunto && !tpl.cuerpo) return;
      try { setPrev(await api(`/admin/emails/${ev}/preview`, { method: "POST", json: tpl })); } catch (e) { setPrev({ asunto: "", cuerpo: e instanceof ClientError ? e.message : "Error" }); }
    }, 300);
    return () => clearTimeout(t);
  }, [tpl, ev]);

  function cambiarEvento(e: string) { setEv(e); const x = r?.eventos.find((z) => z.evento === e); if (x) setTpl({ ...x.template }); }
  function insertar(v: string) {
    const el = ta.current; const tok = `{${v}}`;
    if (!el) { setTpl({ ...tpl, cuerpo: tpl.cuerpo + tok }); return; }
    const s = el.selectionStart ?? tpl.cuerpo.length, e = el.selectionEnd ?? s;
    setTpl({ ...tpl, cuerpo: tpl.cuerpo.slice(0, s) + tok + tpl.cuerpo.slice(e) });
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s + tok.length, s + tok.length); });
  }
  async function accion(fn: () => Promise<string>) {
    setBusy(true);
    try { notify(await fn()); await cargar(ev); } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }

  if (!r) return <><H1>Emails</H1><Spinner /></>;
  const actual = r.eventos.find((z) => z.evento === ev)!;
  return (
    <>
      <H1>Plantillas de email</H1>
      <Muted>Editás el asunto y el cuerpo; la vista previa se arma con el pedido N° {r.ejemplo.numero} de {r.ejemplo.cliente_nombre}. Una variable que no exista queda literal en el email, no rompe el envío.</Muted>
      <div className="mt-4"><Pills value={ev} onChange={cambiarEvento} options={r.eventos.map((z) => ({ value: z.evento, label: z.label + (z.personalizado ? " ·" : "") }))} /></div>
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        <Panel>
          <Field label="Asunto"><input className="input" value={tpl.asunto} onChange={(e) => setTpl({ ...tpl, asunto: e.target.value })} /></Field>
          <div className="mt-3 flex items-center gap-4 font-sans text-[13px]">Formato:
            {["texto", "html"].map((x) => <button key={x} type="button" onClick={() => setTpl({ ...tpl, formato: x })} className="flex items-center gap-2"><span className={`h-[14px] w-[14px] rounded-full border ${tpl.formato === x ? "border-ink bg-ink" : "border-line-2"}`} />{x}</button>)}
          </div>
          <Field label="Cuerpo" className="mt-3"><textarea ref={ta} className="input min-h-[280px] font-mono text-[12.5px]" value={tpl.cuerpo} onChange={(e) => setTpl({ ...tpl, cuerpo: e.target.value })} /></Field>
          <Kicker className="mt-3">Variables (click inserta en el cuerpo)</Kicker>
          <div className="mt-2 flex flex-wrap gap-1">{r.variables.map((v) => <button key={v} type="button" onClick={() => insertar(v)} className="chip hover:bg-[#d6d6d6]">{`{${v}}`}</button>)}</div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/emails/${ev}`, { method: "PUT", json: tpl }); return `Plantilla «${actual.label}» guardada`; })} className="btn btn-primary">Guardar plantilla</button>
            <button disabled={busy} onClick={() => accion(async () => { const x = await api<{ enviado: boolean; destinatarios: string[]; error: string }>(`/admin/emails/${ev}/prueba`, { method: "POST", json: tpl }); if (!x.enviado) throw new ClientError(500, `No se pudo enviar: ${x.error}`); return `Prueba enviada a ${x.destinatarios.join(", ")} (y plantilla guardada)`; })} className="btn btn-light">Enviarme una prueba</button>
            {actual.personalizado && <button disabled={busy} onClick={() => accion(async () => { await api(`/admin/emails/${ev}`, { method: "DELETE" }); return "Plantilla restaurada al texto por defecto"; })} className="btn btn-ghost">Volver al texto por defecto</button>}
          </div>
          <Muted className="mt-2">«Enviarme una prueba» también guarda la plantilla. La prueba va a {r.admin_email}, nunca al cliente.</Muted>
        </Panel>
        <Panel>
          <Kicker>Vista previa</Kicker>
          <div className="mt-3 rounded border border-line p-4">
            <Muted>Para: {r.ejemplo.para} · CC: {r.ejemplo.cc.join(", ")}</Muted>
            <div className="mt-1 font-sans text-[16px] font-semibold">{prev?.asunto}</div>
            <div className="mt-3 border-t border-line pt-3">
              {tpl.formato === "html" ? <iframe title="preview" srcDoc={prev?.cuerpo || ""} className="h-[380px] w-full" /> : <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed">{prev?.cuerpo}</pre>}
            </div>
            {ev === "confirmacion" && <Muted className="mt-3">Adjunto: {r.ejemplo.adjunto}</Muted>}
          </div>
        </Panel>
      </div>
    </>
  );
}
