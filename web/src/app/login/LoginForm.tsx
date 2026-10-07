"use client";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ClientError } from "@/lib/client";
import type { Me } from "@/lib/types";
import { destinoSeguro } from "@/lib/nav";

export default function LoginForm() {
  const router = useRouter();
  const sp = useSearchParams();
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const expirada = sp.get("expired") === "1";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api<Me>("/auth/login", { method: "POST", json: { email, password: pwd } });
      router.replace(destinoSeguro(sp.get("next")));
      router.refresh();
    } catch (e) {
      setErr(e instanceof ClientError ? e.message : "No pudimos conectarnos. Probá de nuevo.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {expirada && !err && <p className="rounded-md bg-[#fff6d6] px-3 py-2 font-sans text-[13px] text-ink">Tu sesión venció, ingresá de nuevo.</p>}
      <label className="block">
        <span className="font-sans text-[12px] text-ink-2">E-Mail</span>
        <input className="input mt-1" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
      </label>
      <label className="block">
        <span className="font-sans text-[12px] text-ink-2">Contraseña</span>
        <input className="input mt-1 bg-[#eaeaea]" type="password" autoComplete="current-password" value={pwd} onChange={(e) => setPwd(e.target.value)} required />
      </label>
      {err && <p className="rounded-md bg-[#fff1f4] px-3 py-2 font-sans text-[13px] text-[#aa0b56]">{err}</p>}
      <button type="submit" className="btn btn-primary w-full justify-between px-6 py-4 text-[15px]" disabled={busy}>
        <span>{busy ? "Ingresando…" : "Ingresar ahora"}</span><span className="chev">›</span>
      </button>
      <p className="pt-1 font-sans text-[12px] text-muted">
        Olvidaste tu contraseña? <a className="font-bold text-ink" href="https://wa.me/5491136808217" target="_blank" rel="noreferrer">Clic aquí</a>
      </p>
    </form>
  );
}
