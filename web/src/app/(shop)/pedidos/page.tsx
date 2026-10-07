import { apiServer } from "@/lib/api";
import type { Me, PedidoResumen } from "@/lib/types";
import PedidosClient from "@/components/PedidosClient";

export const metadata = { title: "Mis pedidos — Lautin Mayorista" };

export default async function PedidosPage() {
  const [me, lista] = await Promise.all([apiServer<Me>("/auth/me"), apiServer<{ items: PedidoResumen[] }>("/pedidos")]);
  return <PedidosClient me={me} lista={lista.items} />;
}
