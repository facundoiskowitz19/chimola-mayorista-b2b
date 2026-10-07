"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS: { href: string; label: string; exact?: boolean; tambien?: string[] }[] = [
  { href: "/admin", label: "Inicio", exact: true },
  { href: "/admin/catalogo", label: "Catálogo" },
  { href: "/admin/categorias", label: "Categorías", tambien: ["/admin/tipos"] },
  { href: "/admin/clientes", label: "Clientes" },
  { href: "/admin/pedidos", label: "Pedidos" },
  { href: "/admin/home", label: "Home del sitio" },
  { href: "/admin/menu", label: "Menú" },
  { href: "/admin/config", label: "Config" },
  { href: "/admin/emails", label: "Emails" },
];

export default function AdminNav() {
  const path = usePathname();
  return (
    <aside className="hidden w-[190px] shrink-0 md:block">
      <ul className="space-y-[2px]">
        {ITEMS.map((it) => {
          const on = it.exact ? path === it.href : [it.href, ...(it.tambien || [])].some((h) => path.startsWith(h));
          return (
            <li key={it.href}>
              <Link href={it.href} className={`block rounded-sm px-3 py-2 font-sans text-[13.5px] ${on ? "bg-ink text-white" : "text-ink-2 hover:bg-white"}`}>{it.label}</Link>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
