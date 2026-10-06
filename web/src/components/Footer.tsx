export default function Footer() {
  const env = process.env.NEXT_PUBLIC_APP_ENV || "dev";
  return (
    <footer className="mt-16 bg-black text-white">
      <div className="container-lt py-14">
        <div className="grid gap-10 md:grid-cols-[260px_1fr]">
          <div>
            <h3 className="font-brand text-[15px] font-bold leading-tight">Tenés dudas?<br />Contactanos.</h3>
            <p className="mt-4 font-sans text-[12px] leading-relaxed">
              <a href="https://wa.me/5491136808217" target="_blank" rel="noreferrer" className="hover:underline">+54 9 11 3680 8217</a><br />
              @chimolaoficial · @lima.oficial
            </p>
          </div>
          <div>
            <h3 className="font-brand text-[15px] font-bold leading-tight">Información<br />importante de pedidos</h3>
            <p className="mt-4 font-sans text-[12px] leading-relaxed">
              Los pedidos se confirman<br />por email con el Excel adjunto.<br />Sin pago online.<br />Lautin coordina entrega y facturación.
            </p>
          </div>
        </div>
        <div className="mt-12 border-t border-white/20 pt-6 font-sans text-[11px] text-white/80">
          © {new Date().getFullYear()} Lautin Accesorios. Todos los derechos reservados.{env !== "prod" && <> · Ambiente {env.toUpperCase()}</>}
        </div>
      </div>
    </footer>
  );
}
