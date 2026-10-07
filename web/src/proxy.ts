/* Guard de sesión: sin cookie → /login. La validez del JWT la verifica la API
 * (si la cookie existe pero venció, el layout manda a /auth/expired, que la borra). */
import { NextResponse, type NextRequest } from "next/server";

const COOKIE = "mayorista_session";

export function proxy(req: NextRequest) {
  const tiene = req.cookies.has(COOKIE);
  const { pathname, search } = req.nextUrl;
  if (pathname === "/login") return NextResponse.next();
  if (!tiene) {
    const login = new URL("/login", req.url);
    if (pathname !== "/") login.searchParams.set("next", pathname + search);
    return NextResponse.redirect(login);
  }
  // El layout no conoce la ruta actual: se la pasamos para que /auth/expired pueda volver acá.
  const headers = new Headers(req.headers);
  headers.set("x-ruta-actual", pathname + search);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/((?!api|auth/expired|_next/static|_next/image|favicon.ico|banners|logo_lautin.png|.*\\.(?:png|jpg|svg|ico)$).*)"],
};
