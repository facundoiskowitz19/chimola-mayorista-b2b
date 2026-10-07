"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { H1, Muted, Panel, Spinner } from "@/components/admin/ui";

interface Tipo { rubro: string; productos: number; stock: number }
interface Cat { categoria: string; productos: number; stock: number; tipos: Tipo[] }
interface Res { arbol: Cat[]; reclasificados: { producto_cod: string; categoria: string | null; rubro: string | null; categorias_extra: string[] }[]; por_seccion: Record<string, number>; secciones: Record<string, string> }

export default function CategoriasAdmin() {
  const [d, setD] = useState<Res | null>(null);
  const [nueva, setNueva] = useState("");
  const router = useRouter();
  useEffect(() => { api<Res>("/admin/categorias").then(setD); }, []);
  if (!d) return <><H1>Categorías</H1><Spinner /></>;
  return (
    <>
      <H1 right={<form onSubmit={(e) => { e.preventDefault(); if (nueva.trim()) router.push(`/admin/categorias/${encodeURIComponent(nueva.trim())}`); }} className="flex gap-2"><input className="input !w-[220px]" value={nueva} onChange={(e) => setNueva(e.target.value)} placeholder="Nueva categoría…" /><button type="submit" className="btn btn-primary btn-sm">Crear</button></form>}>Categorías</H1>
      <Muted>Un producto puede estar en varias categorías: la principal de Aleph más las que agregues. Click en una categoría o en un tipo de producto para ver y editar sus productos y su banner. Cómo está clasificado hoy el catálogo. Los nombres vienen de Aleph: el campo «tipo_producto» es la <b>categoría</b> y el campo «rubro» es el <b>tipo de producto</b>; «Otros» son productos sin categoría en Aleph. Para cambiar la clasificación de un producto, abrilo en Catálogo y editá «Categoría» y «Tipo de producto»: el cambio pisa a Aleph solo en el sitio. Los nombres que ve el cliente en el menú se editan en <Link href="/admin/menu" className="underline">Menú</Link>.</Muted>
      <div className="mt-4 flex flex-wrap gap-3 font-sans text-[13px]">
        {Object.entries(d.secciones).map(([k, n]) => <span key={k} className="pill">{n}: <b className="ml-1">{d.por_seccion[k]}</b> productos</span>)}
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {d.arbol.map((c) => (
          <Panel key={c.categoria}>
            <div className="flex items-baseline justify-between">
              <h2 className="font-brand text-[16px] font-bold"><Link href={`/admin/categorias/${encodeURIComponent(c.categoria)}`} className="hover:underline">{c.categoria}</Link>{c.categoria === "Otros" && <span className="ml-2 font-sans text-[11px] font-normal text-[#aa0b56]">sin categoría en Aleph</span>}</h2>
              <Link href={`/admin/categorias/${encodeURIComponent(c.categoria)}`} className="font-sans text-[12px] hover:underline">{c.productos} productos ›</Link>
            </div>
            <table className="mt-2 w-full font-sans text-[12.5px]">
              <tbody>{c.tipos.map((t) => (
                <tr key={t.rubro} className="border-t border-line">
                  <td className="py-[6px]"><Link href={`/admin/tipos/${encodeURIComponent(t.rubro)}?categoria=${encodeURIComponent(c.categoria)}`} className="hover:underline">{t.rubro}</Link></td>
                  <td className="py-[6px] text-right text-muted">{t.productos} prod.</td>
                  <td className="py-[6px] text-right text-muted">{t.stock.toLocaleString("es-AR")} u.</td>
                </tr>
              ))}</tbody>
            </table>
          </Panel>
        ))}
      </div>
      <Panel className="mt-5">
        <h2 className="font-brand text-[16px] font-bold">Productos con clasificación manual</h2>
        {d.reclasificados.length === 0 ? <Muted className="mt-2">Ninguno todavía. Se hace desde la ficha del producto en Catálogo, modo Editar.</Muted> : (
          <table className="mt-2 w-full font-sans text-[12.5px]"><thead><tr className="border-b border-ink text-left text-[11px] uppercase"><th className="py-1">Producto</th><th className="py-1">Categoría principal</th><th className="py-1">Tipo de producto</th><th className="py-1">Categorías adicionales</th></tr></thead>
            <tbody>{d.reclasificados.map((r) => <tr key={r.producto_cod} className="border-b border-line"><td className="py-1"><Link href={`/admin/catalogo/${r.producto_cod}`} className="font-bold hover:underline">{r.producto_cod}</Link></td><td className="py-1">{r.categoria || <span className="text-muted">Aleph</span>}</td><td className="py-1">{r.rubro || <span className="text-muted">Aleph</span>}</td><td className="py-1">{r.categorias_extra.join(", ") || <span className="text-muted">—</span>}</td></tr>)}</tbody></table>
        )}
      </Panel>
    </>
  );
}
