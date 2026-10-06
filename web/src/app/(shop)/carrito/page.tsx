import { apiServer } from "@/lib/api";
import type { Me } from "@/lib/types";
import CarritoClient from "@/components/CarritoClient";

export const metadata = { title: "Carrito — Lautin Mayorista" };

export default async function CarritoPage() {
  const me = await apiServer<Me>("/auth/me");
  return <CarritoClient me={me} />;
}
