import CategoriaAdmin from "@/components/admin/CategoriaAdmin";

export default async function Page({ params }: { params: Promise<{ nombre: string }> }) {
  const { nombre } = await params;
  return <CategoriaAdmin nombre={decodeURIComponent(nombre)} />;
}
