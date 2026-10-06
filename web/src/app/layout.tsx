import type { Metadata } from "next";
import { Montserrat, Roboto, Anton } from "next/font/google";
import "./globals.css";

const montserrat = Montserrat({ variable: "--font-montserrat", subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const roboto = Roboto({ variable: "--font-roboto", subsets: ["latin"], weight: ["300", "400", "500", "700"] });
const anton = Anton({ variable: "--font-condensed", subsets: ["latin"], weight: "400" });

export const metadata: Metadata = {
  title: "Lautin Mayorista",
  description: "Venta exclusiva mayorista — Chimola · Lima",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-AR" className={`${montserrat.variable} ${roboto.variable} ${anton.variable} h-full`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
