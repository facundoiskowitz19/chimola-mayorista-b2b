"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, qs } from "@/lib/client";
import { money } from "@/lib/format";
import { H1, Muted, Panel, Pills, Spinner, Tag } from "@/components/admin/ui";
import PedidoAdmin from "@/components/admin/PedidoAdmin";

interface Row { numero: number; fecha_str: string; cliente_cod: number; cliente_nombre: string; usuario_email: string; unidades: number; total: number; estado: string; observaciones: string; email_enviado: boolean; n_items: number }
interface Res { counts: Record<string, number>; clientes: [number, string][]; items: Row[] }
type Estado = "todos" | "confirmado" | "procesado" | "cancelado";

export default function Page() { return <Suspense fallback={<Spinner />}><PedidosAdmin /></Suspense>; }

function PedidosAdmin() {
  const sp = useSearchParams(); const router = useRouter();
  const [estado, setEstado] = useState<Estado>((sp.get("estado") as Estado) || "todos");
  const [cliente, setCliente] = useState("");
  const [desde, setDesde] = useState("");
  const [res, setRes] = useState<Res | null>(null);
  const [abierto, setAbierto] = useState<number | null>(sp.get("n") ? parseInt(sp.get("n")!, 10) : null);

  const cargar = useCallback(async () => {
    setRes(await api<Res>(`/admin/pedidos${qs({ estado: estado === "todos" ? undefined : estado, cliente_cod: cliente || undefined, desde: desde || undefined })}`));
  }, [estado, cliente, desde]);
  useEffect(() => { cargar(); }, [cargar]);

  return (
    <>
      <H1>Pedidos</H1>
      <div className="flex flex-wrap items-center gap-3">
        <Pills value={estado} onChange={(e) => { setEstado(e); router.replace(`/admin/pedidos?estado=${e}`); }} options={[{ value: "todos", label: "Todos", n: res?.counts.todos }, { value: "confirmado", label: "Confirmados", n: res?.counts.confirmado }, { value: "procesado", label: "Procesados", n: res?.counts.procesado }, { value: "cancelado", label: "Cancelados", n: res?.counts.cancelado }]} />
        <select value={cliente} onChange={(e) => setCliente(e.target.value)} className="input !w-auto"><option value="">Todos los clientes</option>{(res?.clientes || []).map(([c, n]) => <option key={c} value={c}>{c} · {n}</option>)}</select>
        <label className="flex items-center gap-2 font-sans text-[12px]">Desde <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="input !w-auto !py-[7px]" /></label>
      </div>
      {!res ? <div className="mt-4"><Spinner /></div> : (
        <Panel className="mt-4 !p-0">
          <table className="w-full font-sans text-[13px]">
            <thead><tr className="border-b-2 border-ink text-left text-[11px] uppercase text-ink-2"><th className="px-4 py-3">N°</th><th className="py-3">Fecha</th><th className="py-3">Cliente</th><th className="py-3 text-right">Unid.</th><th className="py-3 text-right">Total</th><th className="py-3 pl-4">Estado</th><th className="py-3 text-center">Email</th></tr></thead>
            <tbody>{res.items.map((p) => (
              <tr key={p.numero} onClick={() => setAbierto(abierto === p.numero ? null : p.numero)} className={`cursor-pointer border-b border-line hover:bg-[#fafafa] ${abierto === p.numero ? "bg-[#f3fbff]" : ""}`}>
                <td className="px-4 py-2 font-bold">{String(p.numero).padStart(6, "0")}</td><td className="py-2">{p.fecha_str}</td>
                <td className="py-2">{p.cliente_nombre.slice(0, 40)} <span className="text-muted">· {p.cliente_cod}</span>{p.observaciones && <div className="card-meta">“{p.observaciones.slice(0, 70)}”</div>}</td>
                <td className="py-2 text-right">{p.unidades}</td><td className="py-2 text-right">{money(p.total)}</td><td className="py-2 pl-4"><Tag estado={p.estado} /></td><td className="py-2 text-center text-muted">{p.email_enviado ? "sí" : "—"}</td>
              </tr>
            ))}
              {res.items.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-muted">No hay pedidos con ese filtro.</td></tr>}</tbody>
          </table>
        </Panel>
      )}
      {abierto === null && res && res.items.length > 0 && <Muted className="mt-3">Click en una fila para ver el detalle.</Muted>}
      {abierto !== null && <div className="mt-5"><PedidoAdmin numero={abierto} onChange={cargar} /></div>}
    </>
  );
}
