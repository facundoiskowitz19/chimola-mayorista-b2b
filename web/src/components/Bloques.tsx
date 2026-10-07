import Link from "next/link";
import type { HomeBloque } from "@/lib/types";
import { Chevron } from "./Brand";

function Bloque({ b, alto }: { b: HomeBloque; alto: string }) {
  return (
    <div className={`relative overflow-hidden bg-[#9a9a9a] ${alto}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {b.img && <img src={b.img} alt="" className="absolute inset-0 h-full w-full object-cover" />}
      <div className="absolute inset-0 bg-black/10" />
      <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
        <h3 className="bloque-title">{b.titulo}</h3>
        {b.subtitulo && <p className="mt-2 max-w-[260px] font-sans text-[13px] font-medium leading-snug text-white drop-shadow">{b.subtitulo}</p>}
        {b.link && (
          <Link href={b.link} className="btn btn-light mt-5 !bg-white/90 !px-6">{b.cta || "Ver"} <Chevron size={15} /></Link>
        )}
      </div>
    </div>
  );
}

export default function Bloques({ bloques }: { bloques: HomeBloque[] }) {
  if (!bloques.length) return null;
  const doble = bloques.find((b) => b.ancho === "doble") || bloques[0];
  const simples = bloques.filter((b) => b !== doble);
  if (simples.length === 0) return <div className="mt-6"><Bloque b={doble} alto="h-[340px]" /></div>;
  if (simples.length === 1) {
    return <div className="mt-6 grid gap-[18px] md:grid-cols-2"><Bloque b={doble} alto="h-[340px]" /><Bloque b={simples[0]} alto="h-[340px]" /></div>;
  }
  return (
    <div className="mt-6 grid gap-[18px] md:grid-cols-2">
      <Bloque b={doble} alto="h-[340px]" />
      <div className="grid gap-[18px]">
        {simples.slice(0, 2).map((b, i) => <Bloque key={i} b={b} alto="h-[161px]" />)}
      </div>
    </div>
  );
}
