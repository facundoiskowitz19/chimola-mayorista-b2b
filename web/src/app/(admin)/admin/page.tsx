"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { money } from "@/lib/format";
import { H1, Metric, Muted, Panel, Spinner } from "@/components/admin/ui";

interface Inicio {
  sin_procesar: number; pedidos_mes: number; monto_mes: number; unidades_mes: number; clientes_mes: number;
  top: [string, string, number][];
  salud: { productos: number; ocultos: number; sin_foto: number; sin_precio_l1: number; con_overrides: number };
  catalogo_hace_seg: number;
}

export default function AdminInicio() {
  const [d, setD] = useState<Inicio | null>(null);
  useEffect(() => { api<Inicio>("/admin/inicio").then(setD); }, []);
  if (!d) return <><H1>Inicio</H1><Spinner /></>;
  return (
    <>
      <H1>Inicio</H1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="Sin procesar" value={d.sin_procesar} href={d.sin_procesar ? "/admin/pedidos?estado=confirmado" : undefined} />
        <Metric label="Pedidos del mes" value={d.pedidos_mes} />
        <Metric label="Ventas del mes (sin IVA)" value={money(d.monto_mes)} />
        <Metric label="Unidades del mes" value={d.unidades_mes.toLocaleString("es-AR")} />
        <Metric label="Clientes que pidieron" value={d.clientes_mes} />
      </div>
      <h2 className="mb-3 mt-8 font-brand text-[16px] font-bold">Salud del catálogo</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="Productos con stock" value={d.salud.productos} />
        <Metric label="Ocultos" value={d.salud.ocultos} href="/admin/catalogo?pill=ocultos" />
        <Metric label="Sin foto" value={d.salud.sin_foto} href="/admin/catalogo?pill=sin_foto" />
        <Metric label="Sin precio L1" value={d.salud.sin_precio_l1} />
        <Metric label="Con overrides" value={d.salud.con_overrides} href="/admin/catalogo?pill=con_override" />
      </div>
      <Muted className="mt-3">Catálogo leído de BigQuery hace {Math.round(d.catalogo_hace_seg / 60)} min. El stock se actualiza una vez por día a las 08:30.</Muted>
      {d.top.length > 0 && (
        <Panel className="mt-8">
          <h2 className="font-brand text-[16px] font-bold">Top productos del mes</h2>
          <table className="mt-3 w-full font-sans text-[13px]">
            <thead><tr className="border-b border-ink text-left text-[11px] uppercase text-ink-2"><th className="py-2">Código</th><th className="py-2">Producto</th><th className="py-2 text-right">Unidades</th></tr></thead>
            <tbody>{d.top.map(([c, n, u]) => <tr key={c} className="border-b border-line"><td className="py-2"><Link href={`/admin/catalogo/${c}`} className="font-bold hover:underline">{c}</Link></td><td className="py-2">{n}</td><td className="py-2 text-right">{u}</td></tr>)}</tbody>
          </table>
        </Panel>
      )}
    </>
  );
}
