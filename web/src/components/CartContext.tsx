"use client";
import { createContext, useCallback, useContext, useState } from "react";
import { api } from "@/lib/client";
import type { Carrito } from "@/lib/types";

interface CartCtx {
  unidades: number;
  setUnidades: (n: number) => void;
  /** `recortar: false` (picker de variantes): si algo supera lo disponible NO se agrega nada y vuelve `ajustes`. */
  agregar: (items: { sku: string; cantidad: number }[], opts?: { recortar?: boolean }) => Promise<Carrito>;
}

const Ctx = createContext<CartCtx>({ unidades: 0, setUnidades: () => {}, agregar: async () => { throw new Error("sin provider"); } });

export function CartProvider({ children, unidadesIniciales }: { children: React.ReactNode; unidadesIniciales: number }) {
  const [unidades, setUnidades] = useState(unidadesIniciales);
  const agregar = useCallback(async (items: { sku: string; cantidad: number }[], opts?: { recortar?: boolean }) => {
    const c = await api<Carrito>("/carrito/items", { method: "POST", json: { items, recortar: opts?.recortar ?? true } });
    setUnidades(c.totales.unidades);
    return c;
  }, []);
  return <Ctx.Provider value={{ unidades, setUnidades, agregar }}>{children}</Ctx.Provider>;
}

export const useCart = () => useContext(Ctx);
