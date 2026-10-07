import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { apiServer, apiServerOpcional } from "@/lib/api";
import type { Carrito, Me, Menu } from "@/lib/types";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { CartProvider } from "@/components/CartContext";
import { ToastProvider } from "@/components/Toast";

export default async function ShopLayout({ children }: LayoutProps<"/">) {
  const me = await apiServerOpcional<Me>("/auth/me");
  if (!me) {
    // Hay cookie (el proxy ya pasó) pero la API no la acepta: vencida o inválida → borrarla y volver al login.
    const ruta = (await headers()).get("x-ruta-actual");
    redirect(`/auth/expired${ruta && ruta !== "/" ? `?next=${encodeURIComponent(ruta)}` : ""}`);
  }
  const [menu, carrito, sitio] = await Promise.all([
    apiServer<Menu>("/catalogo/menu"),
    me.puede_pedir ? apiServerOpcional<Carrito>("/carrito") : Promise.resolve(null),
    apiServerOpcional<{ topbar: string }>("/config/sitio"),
  ]);
  return (
    <ToastProvider>
      <CartProvider unidadesIniciales={carrito?.totales.unidades ?? 0}>
        <div className="flex min-h-screen flex-col">
          <Header me={me} menu={menu} topbar={sitio?.topbar || ""} />
          <main className="flex-1">{children}</main>
          <Footer />
        </div>
      </CartProvider>
    </ToastProvider>
  );
}
