"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { HomeBloque, Seccion } from "@/lib/types";
import { Chevron, Chimola, Lima } from "./Brand";

export default function Hero({ slides, seccion }: { slides: HomeBloque[]; seccion: Seccion }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return;
    const t = setInterval(() => setI((x) => (x + 1) % slides.length), 6000);
    return () => clearInterval(t);
  }, [slides.length]);
  if (!slides.length) return null;
  const s = slides[i];
  const [l1, l2] = (s.titulo || "").split("\n");
  return (
    <section className="relative mt-2">
      <div className="relative aspect-[1125/340] w-full overflow-hidden bg-[#d8d2c8]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {s.img && <img key={s.img} src={s.img} alt="" className="fade-in absolute inset-0 h-full w-full object-cover" />}
        <div className="absolute inset-y-0 left-[8%] flex flex-col justify-end pb-[12%]">
          <h1 className="hero-title whitespace-pre-line">{l1}{l2 ? <><br />{l2}</> : null}</h1>
          {s.link && <Link href={s.link} className="btn btn-primary mt-6 w-fit !px-7 !py-4 !text-[15px]">{s.cta || "Ver colección"} <Chevron size={18} /></Link>}
        </div>
        {s.tag && <span className="absolute right-[18%] top-[48%] rounded-full bg-white px-4 py-[6px] font-sans text-[12px]">{s.tag}</span>}
        <div className="absolute right-6 top-1/2 origin-center -translate-y-1/2 rotate-180 text-white [writing-mode:vertical-rl]">
          {seccion === "lima" ? <Lima className="text-[40px]" /> : <Chimola className="text-[40px]" />}
        </div>
      </div>
      {slides.length > 1 && (
        <>
          <button onClick={() => setI((i - 1 + slides.length) % slides.length)} className="absolute -left-12 top-1/2 hidden -translate-y-1/2 text-ink-2 lg:block" aria-label="Anterior"><Chevron dir="left" size={44} /></button>
          <button onClick={() => setI((i + 1) % slides.length)} className="absolute -right-12 top-1/2 hidden -translate-y-1/2 text-ink-2 lg:block" aria-label="Siguiente"><Chevron size={44} /></button>
          <div className="mt-3 flex justify-center gap-2">
            {slides.map((_, k) => <button key={k} onClick={() => setI(k)} className={`h-[7px] w-[7px] rounded-full ${k === i ? "bg-ink" : "bg-line-2"}`} aria-label={`Slide ${k + 1}`} />)}
          </div>
        </>
      )}
    </section>
  );
}
