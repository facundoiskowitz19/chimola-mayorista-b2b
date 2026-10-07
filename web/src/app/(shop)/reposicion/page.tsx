import Link from "next/link";
import { apiServer } from "@/lib/api";
import type { Me } from "@/lib/types";
import ReposicionClient from "@/components/ReposicionClient";

export const metadata = { title: "Reposición — Lautin Mayorista" };

export default async function ReposicionPage() {
  const me = await apiServer<Me>("/auth/me");
  if (!me.es_franquicia) {
    return (
      <div className="container-lt pb-10 pt-8">
        <h1 className="font-brand text-[28px] font-extrabold">Reposición sugerida</h1>
        <div className="mt-6 bg-white p-10 font-sans text-[14px]">
          <p>La reposición sugerida está disponible para las franquicias con punto de venta propio.</p>
          <Link href="/h/marro" className="btn btn-primary mt-6">Volver al catálogo</Link>
        </div>
      </div>
    );
  }
  return <ReposicionClient />;
}
