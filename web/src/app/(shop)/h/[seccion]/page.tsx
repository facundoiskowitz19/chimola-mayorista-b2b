import { notFound } from "next/navigation";
import { apiServer } from "@/lib/api";
import type { Home, Me } from "@/lib/types";
import Hero from "@/components/Hero";
import Bloques from "@/components/Bloques";
import ProductRow from "@/components/ProductRow";

const SECS = ["marro", "indu", "lima"] as const;

export default async function HomePage({ params }: { params: Promise<{ seccion: string }> }) {
  const { seccion } = await params;
  if (!SECS.includes(seccion as (typeof SECS)[number])) notFound();
  const [home, me] = await Promise.all([apiServer<Home>(`/home/${seccion}`), apiServer<Me>("/auth/me")]);
  return (
    <div className="container-lt relative pb-10">
      <Hero slides={home.hero} seccion={home.seccion} />
      <Bloques bloques={home.bloques} />
      {home.secciones.map((s) => (
        <ProductRow key={s.titulo} titulo={s.titulo} link={s.link} items={s.productos} puedePedir={me.puede_pedir} />
      ))}
    </div>
  );
}
