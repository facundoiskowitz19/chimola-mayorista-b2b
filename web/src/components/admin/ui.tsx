"use client";
/* Piezas chicas compartidas por las pantallas de admin. */
import Link from "next/link";
import { money } from "@/lib/format";

export function H1({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-brand text-[26px] font-extrabold">{children}</h1>
      {right}
    </div>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`bg-white p-5 ${className}`}>{children}</section>;
}

export function Kicker({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`kicker text-[11px] text-ink-2 ${className}`}>{children}</div>;
}

export function Muted({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`font-sans text-[12.5px] leading-snug text-muted ${className}`}>{children}</p>;
}

export function Metric({ label, value, sub, href }: { label: string; value: React.ReactNode; sub?: React.ReactNode; href?: string }) {
  return (
    <div className="border-t-2 border-ink bg-white px-4 pb-4 pt-3">
      <div className="font-sans text-[12px] text-muted">{label}</div>
      <div className="mt-1 font-brand text-[24px] font-bold leading-none">{value}</div>
      {sub && <div className="mt-2 font-sans text-[12px] text-muted">{sub}</div>}
      {href && <Link href={href} className="mt-2 inline-block font-sans text-[12px] font-bold hover:underline">Ver ›</Link>}
    </div>
  );
}

export function Tag({ estado }: { estado: string }) {
  const cls: Record<string, string> = {
    confirmado: "bg-[#e9f8ff] text-[#006786]", procesado: "bg-[#e6f6ec] text-[#1d7a44]", cancelado: "bg-[#fff1f4] text-[#aa0b56]",
  };
  return <span className={`inline-block rounded-sm px-2 py-[3px] font-sans text-[11px] font-medium ${cls[estado] || "bg-[#eee]"}`}>{estado}</span>;
}

export function Manual({ children = "manual" }: { children?: React.ReactNode }) {
  return <span className="font-sans text-[11px] font-semibold text-[#006786]">{children}</span>;
}

export function Pills<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string; n?: number }[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)} className={`pill !py-[5px] ${value === o.value ? "!border-ink !bg-ink !text-white" : "hover:!border-ink"}`}>
          {o.label}{o.n !== undefined && <span className={value === o.value ? "text-white/70" : "text-muted"}> {o.n}</span>}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, children, hint, className = "" }: { label: string; children: React.ReactNode; hint?: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="font-sans text-[12px] text-ink-2">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block font-sans text-[11px] text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex items-center gap-3 text-left font-sans text-[13px]">
      <span className={`relative inline-block h-[20px] w-[36px] rounded-full transition-colors ${checked ? "bg-ink" : "bg-line-2"}`}>
        <span className={`absolute top-[2px] h-[16px] w-[16px] rounded-full bg-white transition-all ${checked ? "left-[18px]" : "left-[2px]"}`} />
      </span>
      {label}
    </button>
  );
}

export function Check({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: React.ReactNode }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 font-sans text-[12.5px]">
      <span className="cb !h-[16px] !w-[16px] text-[10px]" data-on={checked}>{checked && "✓"}</span>{label}
    </button>
  );
}

export const fmt = money;

export function Confirm({ texto, onYes, onNo, busy }: { texto: React.ReactNode; onYes: () => void; onNo: () => void; busy?: boolean }) {
  return (
    <div className="rounded-md border border-[#f3b7cc] bg-[#fff1f4] p-3 font-sans text-[12.5px]">
      {texto}
      <div className="mt-2 flex gap-2">
        <button onClick={onYes} disabled={busy} className="btn btn-sm !bg-[#aa0b56] text-white">{busy ? "…" : "Sí, aplicar"}</button>
        <button onClick={onNo} className="btn btn-light btn-sm">No</button>
      </div>
    </div>
  );
}

export function Spinner() {
  return <div className="h-24 animate-pulse rounded bg-[#f1f1f1]" />;
}
