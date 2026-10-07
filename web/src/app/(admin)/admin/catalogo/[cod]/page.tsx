import ProductoAdmin from "@/components/admin/ProductoAdmin";

export default async function Page({ params }: { params: Promise<{ cod: string }> }) {
  const { cod } = await params;
  return <ProductoAdmin cod={cod.toUpperCase()} />;
}
