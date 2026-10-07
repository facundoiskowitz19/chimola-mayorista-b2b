"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import type { Faceta, Me, Menu, Seccion } from "@/lib/types";
import { api } from "@/lib/client";
import { useCart } from "./CartContext";
import { CartIcon, Chevron, Chimola, Lima, UserIcon, Wordmark } from "./Brand";
import SearchBox from "./SearchBox";

const TABS: { key: Seccion; label: React.ReactNode }[] = [
  { key: "marro", label: "Marroquinería" },
  { key: "indu", label: "Indumentaria" },
  { key: "lima", label: <Lima className="text-[19px]" /> },
];

export default function Header({ me, menu, topbar }: { me: Me; menu: Menu; topbar: string }) {
  const path = usePathname();
  const router = useRouter();
  const { unidades } = useCart();
  const [open, setOpen] = useState<Seccion | null>(null);
  const closeT = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activa: Seccion | null = (path.match(/^\/(?:h|c)\/(marro|indu|lima)/)?.[1] as Seccion) || null;

  function enter(k: Seccion) { if (closeT.current) clearTimeout(closeT.current); setOpen(k); }
  function leave() { closeT.current = setTimeout(() => setOpen(null), 160); }

  async function salir() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  const nombre = me.user.nombre || me.cliente?.nombre || me.user.email;

  return (
    <header className="relative z-40 bg-bg">
      {topbar && (
        <div className="bg-black py-[7px] text-center font-sans text-[11.5px] text-white">
          <span className="mx-2">★</span>{topbar}<span className="mx-2">★</span>
        </div>
      )}
      <div className="container-lt">
        <div className="flex h-[66px] items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Wordmark />
            <span className="pill hidden sm:inline-flex">Venta exclusiva mayorista</span>
          </div>
          <nav className="flex items-center gap-3 sm:gap-5">
            <span className="hidden items-center gap-2 font-sans text-[13px] md:inline-flex"><UserIcon /> Hola, <b className="font-bold">{nombre}</b></span>
            {me.es_franquicia && <Link href="/reposicion" className="nav-link hidden md:inline">Reposición</Link>}
            <Link href="/pedidos" className="nav-link">Mis Pedidos</Link>
            <Link href="/mis-datos" className="nav-link">Mis Datos</Link>
            {me.es_admin && <Link href="/admin" className="nav-link font-bold">Admin</Link>}
            <button onClick={salir} className="font-sans text-[11px] text-muted hover:text-ink">Salir &gt;</button>
          </nav>
        </div>
        <div className="relative border-t border-line-2" onMouseLeave={leave}>
          <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2 md:flex-nowrap md:py-0">
            <div className="flex h-[42px] items-center md:h-full">
              <Link href="/h/marro" className="mr-2 hidden items-center sm:mr-4 sm:flex"><Chimola className="text-[20px]" /></Link>
              <div className="flex h-full items-stretch">
                {TABS.map((t, i) => (
                  <div key={t.key} className="flex items-stretch">
                    {i > 0 && t.key !== "lima" && <span className="my-auto h-5 w-px bg-line-2" />}
                    {t.key === "lima" && <span className="my-auto mx-2 h-5 w-px bg-transparent" />}
                    <Link href={`/h/${t.key}`} onMouseEnter={() => enter(t.key)} onClick={() => setOpen(null)}
                      className={`relative flex items-center px-2 font-sans text-[14px] transition-colors sm:px-4 sm:text-[15px] ${
                        open === t.key ? "bg-white" : ""} ${activa === t.key || open === t.key ? "text-ink" : "text-ink-2 hover:text-ink"}`}>
                      {(activa === t.key || open === t.key) && <span className="absolute inset-x-0 top-0 h-[3px] bg-ink" />}
                      {t.label}
                    </Link>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex w-full items-center gap-3 md:w-auto" onMouseEnter={() => { if (closeT.current) clearTimeout(closeT.current); setOpen(null); }}>
              <SearchBox />
              {me.puede_pedir && (
                <Link href="/carrito" className="btn btn-primary !py-[10px] !pl-5 !pr-3" aria-label="Carrito">
                  <span className="font-brand text-[14px] font-semibold">{unidades}</span>
                  <CartIcon />
                  <Chevron size={16} />
                </Link>
              )}
            </div>
          </div>
          {open && <div onClick={() => setOpen(null)}><MegaMenu sec={open} data={menu[open]} onEnter={() => enter(open)} /></div>}
        </div>
      </div>
    </header>
  );
}

function MegaMenu({ sec, data, onEnter }: { sec: Seccion; data: Menu[Seccion]; onEnter: () => void }) {
  const temps = data.temporadas;
  const actuales = temps.filter((t) => !t.anterior);
  const anteriores = temps.filter((t) => t.anterior);
  const col = "space-y-[7px] font-sans text-[13px]";
  const nombre = (t: Faceta) => t.nombre || t.valor;
  return (
    <div onMouseEnter={onEnter} className="fade-in absolute inset-x-0 top-full z-50 bg-white px-9 pb-9 pt-7 shadow-[0_18px_30px_-20px_rgba(0,0,0,.35)]">
      <div className="grid grid-cols-2 gap-8" style={{ gridTemplateColumns: `repeat(${3 + Math.max(1, (data.grupos || []).length)}, minmax(0, 1fr))` }}>
        <div>
          <h4 className="kicker mb-3">Temporada</h4>
          <ul className={col}>
            {actuales.map((t) => (
              <li key={t.valor}><Link href={`/c/${sec}?temporada=${encodeURIComponent(t.valor)}`} className="hover:underline">{nombre(t)}</Link>
                {t.nuevo && <span className="ml-2 rounded-full bg-ink px-2 py-[2px] font-brand text-[8px] font-bold uppercase text-white">New</span>}</li>
            ))}
          </ul>
          {anteriores.length > 0 && (
            <>
              <h5 className="mb-2 mt-5 font-sans text-[13px] font-bold">Temporadas anteriores</h5>
              <ul className={col}>{anteriores.map((t) => <li key={t.valor}><Link href={`/c/${sec}?temporada=${encodeURIComponent(t.valor)}`} className="hover:underline">{nombre(t)}</Link></li>)}</ul>
            </>
          )}
        </div>
        {(data.grupos || []).length > 0 ? (data.grupos || []).map((g) => (
          <div key={g.titulo}>
            <h4 className="kicker mb-3"><Link href={`/c/${sec}?categoria=${encodeURIComponent(g.categoria)}`} className="hover:underline">{g.titulo}</Link></h4>
            <ul className={col}>{g.tipos.map((t) => <li key={t.valor}><Link href={`/c/${sec}?categoria=${encodeURIComponent(g.categoria)}&rubro=${encodeURIComponent(t.valor)}`} className="hover:underline">{nombre(t)}</Link></li>)}</ul>
          </div>
        )) : (
          <div>
            <h4 className="kicker mb-3">Tipo de producto</h4>
            <ul className={col}>{data.tipos.map((t) => <li key={t.valor}><Link href={`/c/${sec}?rubro=${encodeURIComponent(t.valor)}`} className="hover:underline">{nombre(t)}</Link></li>)}</ul>
          </div>
        )}
        <div>
          <h4 className="kicker mb-3">Tendencia</h4>
          <ul className={col}>
            {data.tendencias.map((t) => <li key={t.valor}><Link href={`/c/${sec}?categoria=${encodeURIComponent(t.valor)}`} className="hover:underline">{nombre(t)}</Link></li>)}
            {data.tendencias.length === 0 && <li className="text-muted">—</li>}
          </ul>
        </div>
        <div>
          <h4 className="kicker mb-3"><Link href={`/c/${sec}?solo_desc=1`} className="hover:underline">Oportunidades</Link></h4>
          <ul className={col}>
            {(data.oportunidades_items || []).map((o) => <li key={o.link + o.nombre}><Link href={o.link} className="hover:underline">{o.nombre}</Link></li>)}
          </ul>
        </div>
      </div>
    </div>
  );
}
