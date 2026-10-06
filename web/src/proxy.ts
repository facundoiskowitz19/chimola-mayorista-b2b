/* Guard de sesión: sin cookie → /login. La validez del JWT la verifica la API. */
import { NextResponse, type NextRequest } from "next/server";

const COOKIE = "mayorista_session";

export function proxy(req: NextRequest) {
  const tiene = req.cookies.has(COOKIE);
  const { pathname, search } = req.nextUrl;
  if (pathname === "/login") {
    if (tiene) return NextResponse.redirect(new URL("/h/marro", req.url));
    return NextResponse.next();
  }
  if (!tiene) {
    const login = new URL("/login", req.url);
    if (pathname !== "/") login.searchParams.set("next", pathname + search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|banners|logo_lautin.png|.*\\.(?:png|jpg|svg|ico)$).*)"],
};
