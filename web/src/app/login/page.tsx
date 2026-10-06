import Footer from "@/components/Footer";
import LoginForm from "./LoginForm";
import { Wordmark } from "@/components/Brand";

export const metadata = { title: "Ingresá — Lautin Mayorista" };

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="flex-1">
        <div className="container-lt pt-10 pb-16">
          <div className="mb-5 flex items-center gap-4">
            <Wordmark />
            <span className="pill">Venta exclusiva mayorista_</span>
            <span className="pill">Sólo clientes registrados_</span>
          </div>
          <div className="relative">
            <div className="relative h-[420px] w-full overflow-hidden bg-[#2a2320] lg:w-[calc(100%-60px)]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/banners/hero_marro.jpg" alt="" className="absolute inset-0 h-full w-full object-cover opacity-90" />
              <div className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/20 to-transparent" />
              <div className="absolute left-[10%] top-[28%] text-white">
                <h1 className="font-brand text-[44px] font-extrabold leading-[1.02]">Bienvenido<br />a Lautin<br />Accesorios_</h1>
                <p className="mt-3 font-sans text-[19px] font-light leading-tight">Ingresá y descubrí<br />nuestros productos.</p>
                <div className="mt-10 flex items-center gap-8">
                  <span className="font-brand text-[34px] font-bold lowercase leading-none">chimola<span className="align-top text-[16px]">®</span></span>
                  <span className="font-serif text-[30px] leading-none tracking-wide">LIMA</span>
                </div>
              </div>
              <div className="absolute right-[32%] top-[12%] hidden h-[90px] w-[90px] rotate-[-12deg] items-center justify-center rounded-full bg-[#d98fe0] text-center font-brand text-[22px] font-extrabold leading-[0.9] text-white md:flex">
                SS<br />27
              </div>
            </div>
            <div className="mt-6 w-full rounded-2xl bg-white p-8 shadow-sm lg:absolute lg:right-0 lg:top-[-50px] lg:mt-0 lg:w-[370px]">
              <h2 className="font-brand text-[26px] font-bold leading-tight">Ingresá a tu cuenta</h2>
              <p className="mt-1 font-sans text-[14px] leading-snug text-ink-2">Completá tus datos e ingresá<br />a nuestro catálogo mayorista</p>
              <LoginForm />
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
