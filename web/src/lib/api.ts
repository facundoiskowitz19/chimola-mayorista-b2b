/* Acceso a la API FastAPI.
 *  - Server Components: `apiServer()` llama a API_URL directo y reenvía la cookie de sesión.
 *  - Client Components: `apiClient()` llama a /api/... (route handler que hace de proxy same-origin).
 */
import { cookies } from "next/headers";

export const API_URL = process.env.API_URL || "http://localhost:8000";
export const COOKIE = "mayorista_session";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { mensaje?: string })?.mensaje || `Error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiServer<T>(path: string, init?: RequestInit): Promise<T> {
  const jar = await cookies();
  const tok = jar.get(COOKIE)?.value;
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(init?.headers || {}), ...(tok ? { cookie: `${COOKIE}=${tok}` } : {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try { detail = JSON.parse(detail as string).detail ?? detail; } catch { /* texto plano */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiServerOpcional<T>(path: string): Promise<T | null> {
  try { return await apiServer<T>(path); } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
    throw e;
  }
}
