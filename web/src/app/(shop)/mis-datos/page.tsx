import { apiServer } from "@/lib/api";
import type { Me } from "@/lib/types";
import MisDatosClient from "@/components/MisDatosClient";

export const metadata = { title: "Mis datos — Lautin Mayorista" };

export default async function MisDatosPage() {
  const me = await apiServer<Me>("/auth/me");
  return <MisDatosClient me={me} />;
}
