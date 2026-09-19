import { loadStoredToken } from "./auth";

/** Every request goes through the Gateway (contracts/gateway-routing.md); the
 * frontend never addresses a backend service directly. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = loadStoredToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path, { ...init, headers });
}

export async function apiGetJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return (await res.json()) as T;
}
