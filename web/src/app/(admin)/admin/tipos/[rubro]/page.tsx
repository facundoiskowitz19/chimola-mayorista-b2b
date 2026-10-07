import TipoAdmin from "@/components/admin/TipoAdmin";

export default async function Page({ params, searchParams }: { params: Promise<{ rubro: string }>; searchParams: Promise<{ categoria?: string }> }) {
  const { rubro } = await params;
  const { categoria } = await searchParams;
  return <TipoAdmin rubro={rubro} categoria={categoria || null} />;
}
