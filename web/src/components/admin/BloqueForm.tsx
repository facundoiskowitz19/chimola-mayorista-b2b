"use client";
/* Formulario de un banner / bloque / slide: imagen (subir, URL o foto de un producto) + textos + link + visible. */
import { useState } from "react";
import type { HomeBloque } from "@/lib/types";
import { ClientError } from "@/lib/client";
import { useToast } from "@/components/Toast";
import { Check, Field, Muted } from "./ui";
import { FotoDeProducto } from "./FotoPicker";

export async function subirImagen(file: File): Promise<string> {
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch("/api/admin/home/upload", { method: "POST", body: fd });
  if (!res.ok) throw new ClientError(res.status, (await res.json()).detail);
  return (await res.json()).url;
}

export default function BloqueForm({ b, onChange, onQuitar, conSubtitulo, conTag, conAncho, conKicker, previewAspect = "16/9" }: {
  b: HomeBloque; onChange: (b: HomeBloque) => void; onQuitar?: () => void;
  conSubtitulo?: boolean; conTag?: boolean; conAncho?: boolean; conKicker?: boolean; previewAspect?: string;
}) {
  const [up, setUp] = useState(false);
  const [deProducto, setDeProducto] = useState(false);
  const { notify } = useToast();
  return (
    <div className={`grid gap-4 rounded border border-line p-3 md:grid-cols-[240px_1fr] ${b.oculto ? "bg-[#f7f7f7]" : ""}`}>
      <div>
        <div className={`w-full overflow-hidden bg-[#eee] ${b.oculto ? "opacity-40" : ""}`} style={{ aspectRatio: previewAspect }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {b.img && <img src={b.img} alt="" className="h-full w-full object-cover" />}
        </div>
        <Muted className="mt-1 truncate">{b.img ? (b.img.startsWith("/banners/") ? "Imagen por defecto" : b.img.startsWith("/api/media/") ? "Imagen subida" : "Imagen por URL") : "Sin imagen"}</Muted>
        <div className="mt-2 flex flex-wrap gap-2">
          <label className={`btn btn-light btn-sm cursor-pointer ${up ? "opacity-50" : ""}`}>{up ? "Subiendo…" : "Subir"}<input type="file" accept="image/*" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; setUp(true); try { onChange({ ...b, img: await subirImagen(f) }); } catch (er) { notify(er instanceof ClientError ? er.message : "Error al subir", "error"); } finally { setUp(false); } }} /></label>
          <button type="button" onClick={() => setDeProducto(!deProducto)} className="btn btn-light btn-sm">Foto de un producto</button>
        </div>
        {/* Se muestra todo lo que no sea una ruta del sitio ("/…"): así se puede tipear la URL letra por letra, no solo pegarla. */}
        <input className="input mt-2 !py-1 !text-[11px]" placeholder="…o pegá la URL de una imagen (https://…)" value={b.img && !b.img.startsWith("/") ? b.img : ""} onChange={(e) => onChange({ ...b, img: e.target.value.trim() })} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {conKicker && <Field label="Texto chico arriba del título" className="sm:col-span-2"><input className="input" value={b.kicker || ""} onChange={(e) => onChange({ ...b, kicker: e.target.value })} placeholder="Grupo_ Denim Indigo" /></Field>}
        <Field label="Título" hint="| corta en dos líneas"><input className="input" value={(b.titulo || "").replace(/\n/g, "|")} onChange={(e) => onChange({ ...b, titulo: e.target.value.replace(/\|/g, "\n") })} /></Field>
        {conSubtitulo && <Field label="Subtítulo"><input className="input" value={b.subtitulo || ""} onChange={(e) => onChange({ ...b, subtitulo: e.target.value })} /></Field>}
        {conTag && <Field label="Etiqueta (ej: SS_2027)"><input className="input" value={b.tag || ""} onChange={(e) => onChange({ ...b, tag: e.target.value })} /></Field>}
        <Field label="Texto del botón"><input className="input" value={b.cta || ""} onChange={(e) => onChange({ ...b, cta: e.target.value })} /></Field>
        <Field label="Link" hint="Ej: /c/marro?rubro=Mochilas · /c/lima?solo_desc=1 · /p/M211 · o una URL externa"><input className="input" value={b.link || ""} onChange={(e) => onChange({ ...b, link: e.target.value })} /></Field>
        {conAncho && <Field label="Tamaño"><select className="input" value={b.ancho || "simple"} onChange={(e) => onChange({ ...b, ancho: e.target.value as "doble" | "simple" })}><option value="doble">doble</option><option value="simple">simple</option></select></Field>}
        <div className="flex items-center justify-between self-end sm:col-span-2">
          <Check checked={!b.oculto} onChange={(v) => onChange({ ...b, oculto: !v })} label={b.oculto ? <span className="text-[#aa0b56]">Oculto (guardado, no se muestra)</span> : "Visible en el sitio"} />
          {onQuitar && <button type="button" onClick={onQuitar} className="font-sans text-[12px] text-[#aa0b56] hover:underline">Quitar</button>}
        </div>
      </div>
      {deProducto && <div className="md:col-span-2"><FotoDeProducto onElegir={(url) => { onChange({ ...b, img: url }); setDeProducto(false); }} onCerrar={() => setDeProducto(false)} /></div>}
    </div>
  );
}
