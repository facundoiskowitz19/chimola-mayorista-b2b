import Link from "next/link";
import PedidoAdmin from "@/components/admin/PedidoAdmin";
import { H1 } from "@/components/admin/ui";

export default async function Page({ params }: { params: Promise<{ numero: string }> }) {
  const { numero } = await params;
  const n = parseInt(numero, 10);
  if (!Number.isFinite(n) || n <= 0) {
    return <><Link href="/admin/pedidos" className="font-sans text-[12px] text-muted hover:text-ink">← Pedidos</Link><H1>Pedido</H1><p className="text-[#aa0b56]">Número de pedido inválido.</p></>;
  }
  return (
    <>
      <Link href="/admin/pedidos" className="font-sans text-[12px] text-muted hover:text-ink">← Pedidos</Link>
      <H1>Pedido N° {String(n).padStart(6, "0")}</H1>
      <PedidoAdmin numero={n} />
    </>
  );
}
