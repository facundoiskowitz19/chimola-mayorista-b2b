import TemporadaAdmin from "@/components/admin/TemporadaAdmin";

export default async function Page({ params }: { params: Promise<{ valor: string }> }) {
  const { valor } = await params;
  return <TemporadaAdmin valor={valor} />;
}
