"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

type Tipo = "ok" | "aviso" | "error";
interface T { id: number; msg: string; tipo: Tipo }
const Ctx = createContext<{ notify: (msg: string, tipo?: Tipo) => void }>({ notify: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [list, setList] = useState<T[]>([]);
  const seq = useRef(0);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  useEffect(() => { const ts = timers.current; return () => { ts.forEach(clearTimeout); ts.clear(); }; }, []);
  const notify = useCallback((msg: string, tipo: Tipo = "ok") => {
    const id = ++seq.current;
    setList((l) => [...l, { id, msg, tipo }]);
    const t = setTimeout(() => { timers.current.delete(t); setList((l) => l.filter((x) => x.id !== id)); }, tipo === "ok" ? 3500 : 6000);
    timers.current.add(t);
  }, []);
  return (
    <Ctx.Provider value={{ notify }}>
      {children}
      <div className="pointer-events-none fixed bottom-6 left-1/2 z-[100] flex w-[min(520px,92vw)] -translate-x-1/2 flex-col gap-2">
        {list.map((t) => (
          <div key={t.id} className={`fade-in pointer-events-auto rounded-md px-4 py-3 font-sans text-[13px] shadow-lg ${
            t.tipo === "ok" ? "bg-ink text-white" : t.tipo === "aviso" ? "bg-[#fff6d6] text-ink border border-[#f1d77a]" : "bg-[#fff1f4] text-[#aa0b56] border border-[#f3b7cc]"}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
