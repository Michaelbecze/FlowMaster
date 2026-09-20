import { loadStoredToken, storeToken } from "./auth";

/** Every request goes through the Gateway (contracts/gateway-routing.md); the
 * frontend never addresses a backend service directly. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = loadStoredToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });

  // A stale/expired session token (identity's default TTL is 1 hour) must not just
  // fail silently forever — every page that calls through here shares this one
  // redirect-to-login path instead of each needing its own 401 handling.
  if (res.status === 401 && location.pathname !== "/login") {
    storeToken(null);
    location.href = "/login";
  }

  return res;
}

export async function apiGetJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return (await res.json()) as T;
}
