import Link from "next/link";
import type { HomeBloque } from "@/lib/types";
import { Chevron, Chimola, Lima } from "./Brand";

/* Banner de arriba del catálogo para una colección / categoría (vista 10_1 de Vale):
   panel claro a la izquierda con kicker, título y botón; foto a la derecha. */
export default function CatalogoBanner({ b, seccion }: { b: HomeBloque; seccion: string }) {
  const [l1, l2] = (b.titulo || "").split("\n");
  return (
    <section className="relative mb-8 aspect-[1125/300] w-full overflow-hidden bg-[#e9e2d8]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {b.img && <img src={b.img} alt="" className="absolute inset-y-0 right-0 h-full w-[68%] object-cover" />}
      <div className="absolute inset-y-0 left-0 w-[40%] bg-gradient-to-r from-[#e9e2d8] via-[#e9e2d8]/95 to-transparent" />
      <div className="absolute inset-y-0 left-[6%] flex flex-col justify-center">
        {b.kicker && <span className="font-sans text-[12px] text-ink-2">{b.kicker.replace(/_\s*/, "_ ")}</span>}
        <h2 className="hero-title mt-1 whitespace-pre-line">{l1}{l2 ? <><br />{l2}</> : null}</h2>
        {b.link && <Link href={b.link} className="btn btn-primary mt-5 w-fit !px-6 !py-3">{b.cta || "Ver productos"} <Chevron size={16} /></Link>}
      </div>
      <div className="absolute right-5 top-1/2 -translate-y-1/2 rotate-180 text-white [writing-mode:vertical-rl]">
        {seccion === "lima" ? <Lima className="text-[34px]" /> : <Chimola className="text-[34px]" />}
      </div>
    </section>
  );
}
