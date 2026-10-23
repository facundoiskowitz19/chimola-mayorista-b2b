"use client";
/* «Nombre que ve el cliente» para una categoría, tipo de producto o temporada de Aleph (alias global). */
import { useState } from "react";
import { api, ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Kicker, Muted, Panel } from "./ui";

export default function AliasField({ tipo, valor, actual, onSaved }: { tipo: "categoria" | "rubro" | "temporada"; valor: string; actual: string | null; onSaved?: () => void }) {
  const [v, setV] = useState(actual || "");
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const QUE = { categoria: "esta categoría", rubro: "este tipo de producto", temporada: "esta temporada" }[tipo];
  async function guardar(nombre: string) {
    setBusy(true);
    try {
      await api("/admin/alias", { method: "PUT", json: { tipo, valor, nombre } });
      setV(nombre); notify(nombre ? `Se muestra como «${nombre}»` : `Vuelve al nombre de Aleph («${valor}»)`); onSaved?.();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); }
  }
  return (
    <Panel className="mt-5">
      <Kicker>Nombre que ve el cliente</Kicker>
      <Muted className="mt-1">En Aleph se llama <b className="text-ink">{valor}</b>. El alias se usa en todo el sitio para {QUE}: menú, filtros, título del catálogo, migaja y cards. Los links y filtros siguen funcionando con el nombre de Aleph.</Muted>
      <form className="mt-3 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); guardar(v.trim()); }}>
        <input className="input !w-[320px]" value={v} onChange={(e) => setV(e.target.value)} placeholder={valor} />
        <button type="submit" disabled={busy || (v.trim() || "") === (actual || "")} className="btn btn-primary btn-sm">{busy ? "Guardando…" : "Guardar"}</button>
        {actual && <button type="button" disabled={busy} onClick={() => guardar("")} className="btn btn-ghost btn-sm text-[#aa0b56]">Volver a «{valor}»</button>}
      </form>
    </Panel>
  );
}
