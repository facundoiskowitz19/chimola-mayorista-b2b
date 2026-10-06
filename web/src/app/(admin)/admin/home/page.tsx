"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ClientError } from "@/lib/client";
import type { HomeBloque } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { Confirm, Field, H1, Kicker, Muted, Panel, Pills, Spinner } from "@/components/admin/ui";

type Sec = "marro" | "indu" | "lima";
const SECS: { value: Sec; label: string }[] = [{ value: "marro", label: "Marroquinería (Chimola)" }, { value: "indu", label: "Indumentaria (Chimola)" }, { value: "lima", label: "LIMA" }];
interface Fila { titulo: string; tipo: string; productos: string; rubro: string; temporada: string; link: string }
interface Cfg { hero: HomeBloque[]; bloques: HomeBloque[]; secciones: { titulo: string; tipo: string; productos?: string[]; filtro?: { rubro?: string[]; temporada?: string[] }; link?: string | null }[]; banner_grilla: HomeBloque | null; banners_catalogo?: HomeBloque[] }
interface Opciones { temporadas: { valor: string }[]; tipos: { valor: string }[]; tendencias: { valor: string }[] }
interface Res { seccion: Sec; config: Cfg; personalizada: boolean; tipos_seccion: Record<string, string> }

const vacio = (): HomeBloque => ({ img: "", titulo: "", subtitulo: "", cta: "", link: "", tag: "", ancho: "simple" });

export default function HomeAdmin() {
  const [sec, setSec] = useState<Sec>("marro");
  const [r, setR] = useState<Res | null>(null);
  const [hero, setHero] = useState<HomeBloque[]>([]);
  const [bloques, setBloques] = useState<HomeBloque[]>([]);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [banner, setBanner] = useState<HomeBloque | null>(null);
  const [cats, setCats] = useState<HomeBloque[]>([]);
  const [ops, setOps] = useState<Opciones | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    const d = await api<Res>(`/admin/home/${sec}`); setR(d);
    setHero(d.config.hero.map((h) => ({ ...vacio(), ...h })));
    setBloques(d.config.bloques.map((b) => ({ ...vacio(), ...b })));
    setFilas(d.config.secciones.map((s) => ({ titulo: s.titulo, tipo: s.tipo, productos: (s.productos || []).join(", "), rubro: (s.filtro?.rubro || []).join(", "), temporada: (s.filtro?.temporada || []).join(", "), link: s.link || "" })));
    setBanner(d.config.banner_grilla ? { ...vacio(), ...d.config.banner_grilla } : null);
    setCats((d.config.banners_catalogo || []).map((b) => ({ ...vacio(), ...b })));
    api<{ auto: Opciones }>(`/admin/menu/${sec}`).then((m) => setOps(m.auto)).catch(() => setOps(null));
  }, [sec]);
  useEffect(() => { setR(null); cargar(); }, [cargar]);

  async function subir(file: File): Promise<string> {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch("/api/admin/home/upload", { method: "POST", body: fd });
    if (!res.ok) throw new ClientError(res.status, (await res.json()).detail);
    return (await res.json()).url;
  }

  async function guardar() {
    setBusy(true);
    try {
      await api(`/admin/home/${sec}`, { method: "PUT", json: {
        hero, bloques,
        secciones: filas.filter((f) => f.titulo.trim()).map((f) => ({ titulo: f.titulo, tipo: f.tipo, productos: f.productos, filtro: { rubro: f.rubro, temporada: f.temporada }, link: f.link })),
        banner_grilla: banner && (banner.img || banner.titulo) ? banner : null,
        banners_catalogo: cats,
      } });
      notify("Home guardada — el sitio la toma en menos de un minuto"); await cargar();
    } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); }
    finally { setBusy(false); }
  }

  if (!r) return <><H1>Home del sitio</H1><div className="mb-4"><Pills value={sec} onChange={setSec} options={SECS} /></div><Spinner /></>;
  return (
    <>
      <H1 right={<a href={`/h/${sec}`} target="_blank" className="btn btn-light btn-sm">Ver esta home ›</a>}>Home del sitio</H1>
      <Muted>Lo que ve el cliente al entrar, por sección del header. Nada se aplica hasta «Guardar home». Hero: 1600×480 · bloques: 800×600 · banner de grilla: 1200×160.</Muted>
      <div className="mt-4"><Pills value={sec} onChange={setSec} options={SECS} /></div>
      <Muted className="mt-2">{r.personalizada ? "Esta sección tiene una home personalizada guardada." : "Esta sección usa los valores por defecto del sitio. Al guardar quedan pisados."}</Muted>

      <Panel className="mt-5">
        <Kicker>Carrusel principal</Kicker><Muted className="mt-1">Hasta 3 imágenes. Con una sola, no rota. En el título, | corta en dos líneas.</Muted>
        <div className="mt-3 space-y-3">
          {hero.map((h, i) => <BloqueForm key={i} b={h} onChange={(nb) => setHero(hero.map((x, k) => k === i ? nb : x))} onQuitar={() => setHero(hero.filter((_, k) => k !== i))} subir={subir} conTag />)}
          {hero.length < 3 && <button onClick={() => setHero([...hero, vacio()])} className="btn btn-light btn-sm">+ Agregar imagen</button>}
        </div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Bloques destacados</Kicker><Muted className="mt-1">Hasta 3: uno «doble» (grande, a la izquierda) y dos «simples» apilados a la derecha. Con dos, lado a lado.</Muted>
        <div className="mt-3 space-y-3">
          {bloques.map((b, i) => <BloqueForm key={i} b={b} onChange={(nb) => setBloques(bloques.map((x, k) => k === i ? nb : x))} onQuitar={() => setBloques(bloques.filter((_, k) => k !== i))} subir={subir} conSubtitulo conAncho />)}
          {bloques.length < 3 && <button onClick={() => setBloques([...bloques, vacio()])} className="btn btn-light btn-sm">+ Agregar bloque</button>}
        </div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Filas de productos</Kicker>
        <Muted className="mt-1">Cada fila muestra hasta 8 productos con flechas. <b>destacados</b> = los marcados en Catálogo (completa con lo más nuevo) · <b>ofertas</b> = con descuento · <b>manual</b> = los códigos que pongas · <b>filtro</b> = por tipo de producto / temporada.</Muted>
        <table className="vt mt-3 text-[12.5px]">
          <thead><tr><th>Título</th><th>Tipo</th><th>Códigos (manual)</th><th>Tipo de producto (filtro)</th><th>Temporada (filtro)</th><th>Link «Ver todo»</th><th /></tr></thead>
          <tbody>{filas.map((f, i) => {
            const set = (k: keyof Fila, v: string) => setFilas(filas.map((x, kk) => kk === i ? { ...x, [k]: v } : x));
            return (
              <tr key={i}>
                <td><input className="input !py-1" value={f.titulo} onChange={(e) => set("titulo", e.target.value)} /></td>
                <td><select className="input !py-1" value={f.tipo} onChange={(e) => set("tipo", e.target.value)}>{Object.entries(r.tipos_seccion).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
                <td><input className="input !py-1" value={f.productos} onChange={(e) => set("productos", e.target.value)} placeholder="M211, BP171" disabled={f.tipo !== "manual"} /></td>
                <td><input className="input !py-1" value={f.rubro} onChange={(e) => set("rubro", e.target.value)} placeholder="Mochilas, Bolsos y totes" disabled={f.tipo !== "filtro"} /></td>
                <td><input className="input !py-1" value={f.temporada} onChange={(e) => set("temporada", e.target.value)} placeholder="Summer 2027" disabled={f.tipo !== "filtro"} /></td>
                <td><input className="input !py-1" value={f.link} onChange={(e) => set("link", e.target.value)} placeholder={`/c/${sec}?rubro=Mochilas`} /></td>
                <td><button onClick={() => setFilas(filas.filter((_, k) => k !== i))} className="text-faint hover:text-[#aa0b56]">×</button></td>
              </tr>
            );
          })}</tbody>
        </table>
        <button onClick={() => setFilas([...filas, { titulo: "", tipo: "destacados", productos: "", rubro: "", temporada: "", link: `/c/${sec}` }])} className="btn btn-light btn-sm mt-3">+ Agregar fila</button>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Banner dentro de la grilla del catálogo</Kicker><Muted className="mt-1">Franja angosta después de la segunda fila de productos del catálogo de esta sección. Vacío = no se muestra.</Muted>
        <div className="mt-3">{banner ? <BloqueForm b={banner} onChange={setBanner} onQuitar={() => setBanner(null)} subir={subir} conSubtitulo /> : <button onClick={() => setBanner(vacio())} className="btn btn-light btn-sm">+ Agregar banner</button>}</div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Banners por colección o categoría (arriba del catálogo)</Kicker>
        <Muted className="mt-1">Cuando el cliente entra a una temporada, tipo de producto o categoría que tenga banner, lo ve arriba de la grilla (como «Verano 2027» en el diseño). Imagen ideal 1600×420. El título admite | para cortar en dos líneas.</Muted>
        <div className="mt-3 space-y-3">
          {cats.map((b, i) => {
            const tipo: "temporada" | "rubro" | "categoria" = b.temporada ? "temporada" : b.rubro ? "rubro" : "categoria";
            const valores = tipo === "temporada" ? ops?.temporadas : tipo === "rubro" ? ops?.tipos : ops?.tendencias;
            const set = (nb: HomeBloque) => setCats(cats.map((x, k) => k === i ? nb : x));
            return (
              <div key={i} className="rounded border border-line p-3">
                <div className="mb-3 grid gap-3 sm:grid-cols-3">
                  <Field label="Se muestra cuando el filtro es"><select className="input" value={tipo} onChange={(e) => set({ ...b, temporada: "", rubro: "", categoria: "", [e.target.value]: valores?.[0]?.valor || "" })}><option value="temporada">Temporada</option><option value="rubro">Tipo de producto</option><option value="categoria">Categoría</option></select></Field>
                  <Field label="Valor"><select className="input" value={b[tipo] || ""} onChange={(e) => set({ ...b, [tipo]: e.target.value })}><option value="">—</option>{(valores || []).map((v) => <option key={v.valor} value={v.valor}>{v.valor}</option>)}</select></Field>
                  <Field label="Texto chico arriba del título (kicker)"><input className="input" value={b.kicker || ""} onChange={(e) => set({ ...b, kicker: e.target.value })} placeholder="Grupo_ Denim Indigo" /></Field>
                </div>
                <BloqueForm b={b} onChange={set} onQuitar={() => setCats(cats.filter((_, k) => k !== i))} subir={subir} />
              </div>
            );
          })}
          <button onClick={() => setCats([...cats, { ...vacio(), temporada: ops?.temporadas?.[0]?.valor || "", cta: "Ver productos" }])} className="btn btn-light btn-sm">+ Agregar banner de colección</button>
        </div>
      </Panel>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={guardar} disabled={busy} className="btn btn-primary">{busy ? "Guardando…" : "Guardar home"}</button>
        {r.personalizada && (!confirmReset ? <button onClick={() => setConfirmReset(true)} className="btn btn-ghost">Volver a los valores por defecto</button> : <Confirm busy={busy} texto="Se descarta lo personalizado de esta sección y vuelve la home por defecto." onYes={async () => { setBusy(true); await api(`/admin/home/${sec}`, { method: "DELETE" }); setConfirmReset(false); setBusy(false); notify("Home restaurada"); cargar(); }} onNo={() => setConfirmReset(false)} />)}
      </div>
    </>
  );
}

function BloqueForm({ b, onChange, onQuitar, subir, conSubtitulo, conTag, conAncho }: { b: HomeBloque; onChange: (b: HomeBloque) => void; onQuitar: () => void; subir: (f: File) => Promise<string>; conSubtitulo?: boolean; conTag?: boolean; conAncho?: boolean }) {
  const [up, setUp] = useState(false);
  const { notify } = useToast();
  return (
    <div className="grid gap-4 rounded border border-line p-3 md:grid-cols-[220px_1fr]">
      <div>
        <div className="aspect-[16/9] w-full overflow-hidden bg-[#eee]">{b.img && /* eslint-disable-next-line @next/next/no-img-element */ <img src={b.img} alt="" className="h-full w-full object-cover" />}</div>
        <Muted className="mt-1 truncate">{b.img ? (b.img.startsWith("/banners/") ? "Imagen por defecto" : "Imagen subida") : "Sin imagen"}</Muted>
        <label className={`btn btn-light btn-sm mt-2 cursor-pointer ${up ? "opacity-50" : ""}`}>{up ? "Subiendo…" : "Subir imagen"}<input type="file" accept="image/*" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; setUp(true); try { onChange({ ...b, img: await subir(f) }); } catch (er) { notify(er instanceof ClientError ? er.message : "Error al subir", "error"); } finally { setUp(false); } }} /></label>
        <input className="input mt-2 !py-1 !text-[11px]" placeholder="…o pegá la URL de una imagen (https://…)" value={b.img && b.img.startsWith("http") ? b.img : ""} onChange={(e) => onChange({ ...b, img: e.target.value.trim() })} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Título"><input className="input" value={(b.titulo || "").replace(/\n/g, "|")} onChange={(e) => onChange({ ...b, titulo: e.target.value.replace(/\|/g, "\n") })} /></Field>
        {conSubtitulo && <Field label="Subtítulo"><input className="input" value={b.subtitulo || ""} onChange={(e) => onChange({ ...b, subtitulo: e.target.value })} /></Field>}
        {conTag && <Field label="Etiqueta (ej: SS_2027)"><input className="input" value={b.tag || ""} onChange={(e) => onChange({ ...b, tag: e.target.value })} /></Field>}
        <Field label="Texto del botón"><input className="input" value={b.cta || ""} onChange={(e) => onChange({ ...b, cta: e.target.value })} /></Field>
        <Field label="Link" hint="Ej: /c/marro?rubro=Mochilas · /c/lima?solo_desc=1 · /p/M211"><input className="input" value={b.link || ""} onChange={(e) => onChange({ ...b, link: e.target.value })} /></Field>
        {conAncho && <Field label="Tamaño"><select className="input" value={b.ancho || "simple"} onChange={(e) => onChange({ ...b, ancho: e.target.value as "doble" | "simple" })}><option value="doble">doble</option><option value="simple">simple</option></select></Field>}
        <div className="self-end"><button onClick={onQuitar} className="font-sans text-[12px] text-[#aa0b56] hover:underline">Quitar este elemento</button></div>
      </div>
    </div>
  );
}
