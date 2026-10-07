"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ClientError } from "@/lib/client";
import type { HomeBloque } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { Check, Confirm, Field, H1, Kicker, Muted, Panel, Pills, Spinner } from "@/components/admin/ui";
import BloqueForm from "@/components/admin/BloqueForm";

type Sec = "marro" | "indu" | "lima";
const SECS: { value: Sec; label: string }[] = [{ value: "marro", label: "Marroquinería (Chimola)" }, { value: "indu", label: "Indumentaria (Chimola)" }, { value: "lima", label: "LIMA" }];
interface Fila { titulo: string; tipo: string; productos: string; rubro: string; temporada: string; categoria: string; link: string; oculto: boolean }
interface Cfg { hero: HomeBloque[]; bloques: HomeBloque[]; secciones: { titulo: string; tipo: string; productos?: string[]; filtro?: { rubro?: string[]; temporada?: string[]; categoria?: string[] }; link?: string | null; oculto?: boolean }[]; banner_grilla: HomeBloque | null; banners_catalogo?: HomeBloque[] }
interface Opciones { temporadas: { valor: string }[]; tipos: { valor: string }[]; tendencias: { valor: string }[] }
interface Res { seccion: Sec; config: Cfg; personalizada: boolean; tipos_seccion: Record<string, string> }

const vacio = (): HomeBloque => ({ img: "", titulo: "", subtitulo: "", cta: "", link: "", tag: "", ancho: "simple" });

/* Los ítems de las listas llevan una clave local estable (`_k`): BloqueForm tiene estado interno
   (spinner de subida, selector de fotos abierto) y con key={i} al quitar el 0 ese estado pasaba al 1. */
type Keyed<T> = T & { _k: number };
type TipoBanner = "temporada" | "rubro" | "categoria";
type CatBanner = Keyed<HomeBloque & { tipo: TipoBanner }>;
const tipoDe = (b: HomeBloque): TipoBanner => b.temporada ? "temporada" : b.rubro ? "rubro" : "categoria";
/* Lo que va a la API: sin la clave local ni el `tipo` del selector (el banner lleva solo el filtro elegido). */
const limpiar = (x: object): HomeBloque => Object.fromEntries(Object.entries(x).filter(([k]) => k !== "_k" && k !== "tipo")) as HomeBloque;

export default function HomeAdmin() {
  const [sec, setSec] = useState<Sec>("marro");
  const [r, setR] = useState<Res | null>(null);
  const [hero, setHero] = useState<Keyed<HomeBloque>[]>([]);
  const [bloques, setBloques] = useState<Keyed<HomeBloque>[]>([]);
  const [filas, setFilas] = useState<Fila[]>([]);
  const [banner, setBanner] = useState<HomeBloque | null>(null);
  const [cats, setCats] = useState<CatBanner[]>([]);
  const [ops, setOps] = useState<Opciones | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const kRef = useRef(0);
  const nk = () => ++kRef.current;
  const { notify } = useToast();

  const cargar = useCallback(async () => {
    const d = await api<Res>(`/admin/home/${sec}`); setR(d);
    setHero(d.config.hero.map((h) => ({ ...vacio(), ...h, _k: ++kRef.current })));
    setBloques(d.config.bloques.map((b) => ({ ...vacio(), ...b, _k: ++kRef.current })));
    setFilas(d.config.secciones.map((s) => ({ titulo: s.titulo, tipo: s.tipo, productos: (s.productos || []).join(", "), rubro: (s.filtro?.rubro || []).join(", "), temporada: (s.filtro?.temporada || []).join(", "), categoria: (s.filtro?.categoria || []).join(", "), link: s.link || "", oculto: !!s.oculto })));
    setBanner(d.config.banner_grilla ? { ...vacio(), ...d.config.banner_grilla } : null);
    setCats((d.config.banners_catalogo || []).map((b) => ({ ...vacio(), ...b, tipo: tipoDe(b), _k: ++kRef.current })));
    api<{ auto: Opciones }>(`/admin/menu/${sec}`).then((m) => setOps(m.auto)).catch(() => setOps(null));
  }, [sec]);
  useEffect(() => { setR(null); cargar(); }, [cargar]);

  const listaDe = (t: TipoBanner) => (t === "temporada" ? ops?.temporadas : t === "rubro" ? ops?.tipos : ops?.tendencias) || [];

  async function guardar() {
    setBusy(true);
    try {
      await api(`/admin/home/${sec}`, { method: "PUT", json: {
        hero: hero.map(limpiar), bloques: bloques.map(limpiar),
        secciones: filas.filter((f) => f.titulo.trim()).map((f) => ({ titulo: f.titulo, tipo: f.tipo, productos: f.productos, filtro: { rubro: f.rubro, temporada: f.temporada, categoria: f.categoria }, link: f.link, oculto: f.oculto })),
        banner_grilla: banner && (banner.img || banner.titulo) ? banner : null,
        banners_catalogo: cats.map(limpiar),
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
          {hero.map((h) => <BloqueForm key={h._k} b={h} onChange={(nb) => setHero(hero.map((x) => x._k === h._k ? { ...nb, _k: h._k } : x))} onQuitar={() => setHero(hero.filter((x) => x._k !== h._k))} conTag previewAspect="1125/340" />)}
          {hero.length < 3 && <button onClick={() => setHero([...hero, { ...vacio(), _k: nk() }])} className="btn btn-light btn-sm">+ Agregar imagen</button>}
        </div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Bloques destacados</Kicker><Muted className="mt-1">Hasta 3: uno «doble» (grande, a la izquierda) y dos «simples» apilados a la derecha. Con dos, lado a lado.</Muted>
        <div className="mt-3 space-y-3">
          {bloques.map((b) => <BloqueForm key={b._k} b={b} onChange={(nb) => setBloques(bloques.map((x) => x._k === b._k ? { ...nb, _k: b._k } : x))} onQuitar={() => setBloques(bloques.filter((x) => x._k !== b._k))} conSubtitulo conAncho />)}
          {bloques.length < 3 && <button onClick={() => setBloques([...bloques, { ...vacio(), _k: nk() }])} className="btn btn-light btn-sm">+ Agregar bloque</button>}
        </div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Filas de productos</Kicker>
        <Muted className="mt-1">Cada fila muestra hasta 8 productos con flechas. <b>destacados</b> = los marcados en Catálogo (completa con lo más nuevo) · <b>ofertas</b> = con descuento · <b>manual</b> = los códigos que pongas, en ese orden · <b>filtro</b> = por tipo de producto, categoría y/o temporada. Destildá «Visible» para guardar una fila sin mostrarla.</Muted>
        <table className="vt mt-3 text-[12.5px]">
          <thead><tr><th>Visible</th><th>Título</th><th>Tipo</th><th>Códigos (manual)</th><th>Tipo de producto (filtro)</th><th>Categoría (filtro)</th><th>Temporada (filtro)</th><th>Link «Ver todo»</th><th /></tr></thead>
          <tbody>{filas.map((f, i) => {
            const set = (k: keyof Fila, v: string) => setFilas(filas.map((x, kk) => kk === i ? { ...x, [k]: v } : x));
            return (
              <tr key={i} className={f.oculto ? "opacity-50" : ""}>
                <td><Check checked={!f.oculto} onChange={(v) => setFilas(filas.map((x, kk) => kk === i ? { ...x, oculto: !v } : x))} /></td>
                <td><input className="input !py-1" value={f.titulo} onChange={(e) => set("titulo", e.target.value)} /></td>
                <td><select className="input !py-1" value={f.tipo} onChange={(e) => set("tipo", e.target.value)}>{Object.entries(r.tipos_seccion).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
                <td><input className="input !py-1" value={f.productos} onChange={(e) => set("productos", e.target.value)} placeholder="M211, BP171" disabled={f.tipo !== "manual"} /></td>
                <td><input className="input !py-1" value={f.rubro} onChange={(e) => set("rubro", e.target.value)} placeholder="Mochilas, Bolsos y totes" disabled={f.tipo !== "filtro"} /></td>
                <td><input className="input !py-1" value={f.categoria} onChange={(e) => set("categoria", e.target.value)} placeholder="Bazar, Librería" disabled={f.tipo !== "filtro"} /></td>
                <td><input className="input !py-1" value={f.temporada} onChange={(e) => set("temporada", e.target.value)} placeholder="Summer 2027" disabled={f.tipo !== "filtro"} /></td>
                <td><input className="input !py-1" value={f.link} onChange={(e) => set("link", e.target.value)} placeholder={`/c/${sec}?rubro=Mochilas`} /></td>
                <td><button onClick={() => setFilas(filas.filter((_, k) => k !== i))} className="text-faint hover:text-[#aa0b56]">×</button></td>
              </tr>
            );
          })}</tbody>
        </table>
        <button onClick={() => setFilas([...filas, { titulo: "", tipo: "destacados", productos: "", rubro: "", temporada: "", categoria: "", link: `/c/${sec}`, oculto: false }])} className="btn btn-light btn-sm mt-3">+ Agregar fila</button>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Banner dentro de la grilla del catálogo</Kicker><Muted className="mt-1">Franja angosta después de la segunda fila de productos del catálogo de esta sección. Vacío = no se muestra.</Muted>
        <div className="mt-3">{banner ? <BloqueForm b={banner} onChange={setBanner} onQuitar={() => setBanner(null)} conSubtitulo previewAspect="1200/160" /> : <button onClick={() => setBanner(vacio())} className="btn btn-light btn-sm">+ Agregar banner</button>}</div>
      </Panel>
      <Panel className="mt-5">
        <Kicker>Banners por colección / temporada (arriba del catálogo)</Kicker>
        <Muted className="mt-1">Cuando el cliente entra a una temporada que tenga banner, lo ve arriba de la grilla (como «Verano 2027» en el diseño). Los banners de una <b>categoría</b> o un <b>tipo de producto</b> se editan en su propia página dentro de <Link href="/admin/categorias" className="underline">Categorías</Link>. Imagen ideal 1600×420.</Muted>
        <div className="mt-3 space-y-3">
          {cats.map((b) => {
            // `tipo` es estado explícito de la fila: no se deriva del valor (con «—» elegido se volvía a Categoría).
            const valores = listaDe(b.tipo);
            const set = (nb: Partial<CatBanner>) => setCats(cats.map((x) => x._k === b._k ? { ...x, ...nb, _k: b._k } : x));
            return (
              <div key={b._k} className="rounded border border-line p-3">
                <div className="mb-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Se muestra cuando el filtro es"><select className="input" value={b.tipo} onChange={(e) => { const t = e.target.value as TipoBanner; set({ tipo: t, temporada: "", rubro: "", categoria: "", [t]: listaDe(t)[0]?.valor || "" }); }}><option value="temporada">Temporada</option><option value="rubro">Tipo de producto</option><option value="categoria">Categoría</option></select></Field>
                  <Field label="Valor"><select className="input" value={b[b.tipo] || ""} onChange={(e) => set({ [b.tipo]: e.target.value })}><option value="">—</option>{valores.map((v) => <option key={v.valor} value={v.valor}>{v.valor}</option>)}</select></Field>
                </div>
                {!b[b.tipo] && <Muted className="mb-2 text-[#aa0b56]">Sin valor elegido, este banner no se muestra nunca.</Muted>}
                <BloqueForm b={b} onChange={(nb) => set(nb)} onQuitar={() => setCats(cats.filter((x) => x._k !== b._k))} conKicker previewAspect="1125/300" />
              </div>
            );
          })}
          <button onClick={() => setCats([...cats, { ...vacio(), tipo: "temporada", temporada: ops?.temporadas?.[0]?.valor || "", cta: "Ver productos", _k: nk() }])} className="btn btn-light btn-sm">+ Agregar banner de colección</button>
        </div>
      </Panel>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={guardar} disabled={busy} className="btn btn-primary">{busy ? "Guardando…" : "Guardar home"}</button>
        {r.personalizada && (!confirmReset ? <button onClick={() => setConfirmReset(true)} className="btn btn-ghost">Volver a los valores por defecto</button> : <Confirm busy={busy} texto="Se descarta lo personalizado de esta sección y vuelve la home por defecto." onYes={async () => { setBusy(true); try { await api(`/admin/home/${sec}`, { method: "DELETE" }); setConfirmReset(false); notify("Home restaurada"); await cargar(); } catch (e) { notify(e instanceof ClientError ? e.message : "Error", "error"); } finally { setBusy(false); } }} onNo={() => setConfirmReset(false)} />)}
      </div>
    </>
  );
}
