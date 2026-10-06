import Link from "next/link";

export const metadata = { title: "Reposición — Lautin Mayorista" };

export default function ReposicionPage() {
  return (
    <div className="container-lt pb-10 pt-8">
      <h1 className="font-brand text-[28px] font-extrabold">Reposición sugerida</h1>
      <div className="mt-6 bg-white p-10 font-sans text-[14px]">
        <p>La reposición sugerida para franquicias se está migrando al nuevo sitio.</p>
        <p className="mt-2 text-muted">Mientras tanto seguí usándola desde el sitio anterior.</p>
        <Link href="/h/marro" className="btn btn-primary mt-6">Volver al catálogo</Link>
      </div>
    </div>
  );
}
