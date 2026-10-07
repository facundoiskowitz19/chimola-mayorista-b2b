import { notFound } from "next/navigation";
import { ApiError, apiServer } from "@/lib/api";
import type { Me, Producto } from "@/lib/types";
import Ficha from "@/components/Ficha";

export default async function ProductoPage({ params }: { params: Promise<{ cod: string }> }) {
  const { cod } = await params;
  let p: Producto;
  try { p = await apiServer<Producto>(`/productos/${encodeURIComponent(cod)}`); }
  catch (e) { if (e instanceof ApiError && e.status === 404) notFound(); throw e; }
  const me = await apiServer<Me>("/auth/me");
  return <Ficha p={p} puedePedir={me.puede_pedir} />;
}
