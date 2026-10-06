import ClienteAdmin from "@/components/admin/ClienteAdmin";

export default async function Page({ params }: { params: Promise<{ email: string }> }) {
  const { email } = await params;
  return <ClienteAdmin email={decodeURIComponent(email)} />;
}
