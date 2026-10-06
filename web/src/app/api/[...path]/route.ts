/* Proxy same-origin → API FastAPI. Reenvía cookies/headers y deja pasar Set-Cookie. */
import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = new URL(`${API_URL}/${path.join("/")}`);
  url.search = req.nextUrl.search;
  const headers = new Headers();
  for (const h of ["cookie", "content-type", "accept", "authorization"]) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();
  const res = await fetch(url, { method: req.method, headers, body, redirect: "manual" });
  const out = new Headers();
  for (const h of ["content-type", "content-disposition", "cache-control"]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  // Set-Cookie puede venir repetido: getSetCookie lo preserva.
  for (const sc of res.headers.getSetCookie?.() ?? []) out.append("set-cookie", sc);
  return new Response(res.body, { status: res.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH };
