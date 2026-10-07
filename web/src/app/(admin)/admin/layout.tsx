import Link from "next/link";
import { redirect } from "next/navigation";
import { apiServerOpcional } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ToastProvider } from "@/components/Toast";
import AdminNav from "@/components/admin/AdminNav";
import { Wordmark } from "@/components/Brand";

export const metadata = { title: "Administración — Lautin Mayorista" };

export default async function AdminLayout({ children }: LayoutProps<"/">) {
  const me = await apiServerOpcional<Me>("/auth/me");
  if (!me) redirect("/login?next=/admin");
  if (!me.es_admin) redirect("/h/marro");
  return (
    <ToastProvider>
      <div className="flex min-h-screen flex-col">
        <header className="border-b border-line-2 bg-white">
          <div className="container-lt flex h-[58px] items-center justify-between">
            <div className="flex items-center gap-4">
              <Wordmark href="/admin" />
              <span className="pill">Administración</span>
            </div>
            <nav className="flex items-center gap-5 font-sans text-[13px]">
              <span className="hidden text-muted md:inline">{me.user.email}</span>
              <Link href="/h/marro" className="nav-link">Ver el sitio ›</Link>
            </nav>
          </div>
        </header>
        <div className="container-lt flex flex-1 gap-8 py-8">
          <AdminNav />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
        <footer className="border-t border-line-2 py-4 text-center font-sans text-[11px] text-muted">
          BigQuery es de solo lectura · lo que edites vive en Firestore y pisa a Aleph
        </footer>
      </div>
    </ToastProvider>
  );
}
