import Link from "next/link";

export default function NotFound() {
  return (
    <div className="container-lt py-24 text-center font-sans">
      <h1 className="font-brand text-[28px] font-extrabold">No encontramos esa página</h1>
      <Link href="/h/marro" className="btn btn-primary mt-6">Ir al catálogo</Link>
    </div>
  );
}
