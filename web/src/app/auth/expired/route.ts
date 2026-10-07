/* Sesión vencida o inválida: borra la cookie (si no, /login y el shop se rebotan entre sí) y manda a /login. */
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { COOKIE } from "@/lib/api";
import { destinoSeguro } from "@/lib/nav";

export async function GET(req: NextRequest) {
  const jar = await cookies();
  jar.delete(COOKIE);
  const login = new URL("/login", req.url);
  login.searchParams.set("expired", "1");
  const next = destinoSeguro(req.nextUrl.searchParams.get("next"), "");
  if (next) login.searchParams.set("next", next);
  const res = NextResponse.redirect(login);
  res.cookies.delete(COOKIE); // además del jar: la cookie va sí o sí en esta respuesta
  return res;
}
