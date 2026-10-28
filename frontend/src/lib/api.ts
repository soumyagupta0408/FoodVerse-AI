const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown, public requestId?: string) {
    super(message);
  }
}

// Access token lives in memory; the refresh token in localStorage so a reload keeps the session.
// (localStorage is readable by any script on the page: acceptable here because the app serves no third-party scripts.)
let access: string | null = null;
const RT = "fv_refresh";
export const tokens = {
  set(a: string, r: string) { access = a; localStorage.setItem(RT, r); },
  clear() { access = null; localStorage.removeItem(RT); },
  refresh: () => localStorage.getItem(RT),
  hasAccess: () => access !== null,
};

let refreshing: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  const rt = tokens.refresh();
  if (!rt) return false;
  refreshing ??= fetch(`${API}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) })
    .then(async (r) => { if (!r.ok) return false; const t = await r.json(); tokens.set(t.access_token, t.refresh_token); return true; })
    .catch(() => false)
    .finally(() => { refreshing = null; });
  return refreshing;
}

async function toError(res: Response): Promise<ApiError> {
  let body: any = null;
  try { body = await res.json(); } catch { /* not json */ }
  const e = body?.error;
  return new ApiError(res.status, e?.code ?? "http_error", e?.message ?? `Request failed (${res.status})`, e?.details, e?.request_id);
}

async function raw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (access) headers.set("Authorization", `Bearer ${access}`);
  let res: Response;
  try { res = await fetch(`${API}${path}`, { ...init, headers }); }
  catch { throw new ApiError(0, "network_error", "Cannot reach the server. Check that the backend is running."); }
  if (res.status === 401 && retry && (await tryRefresh())) return raw(path, init, false);
  if (!res.ok) throw await toError(res);
  return res;
}

export async function api<T>(path: string, opts: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method ?? (opts.json || opts.form ? "POST" : "GET") };
  if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers = { "Content-Type": "application/json" }; }
  if (opts.form) init.body = opts.form;
  const res = await raw(path, init);
  return res.status === 204 ? (undefined as T) : res.json();
}

export const mediaBlob = async (id: string) => URL.createObjectURL(await (await raw(`/media/${id}`)).blob());
export const exportText = async (path: string) => (await raw(path)).text();

export async function login(email: string, password: string) {
  const res = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  if (!res.ok) throw await toError(res);
  const t = await res.json(); tokens.set(t.access_token, t.refresh_token);
}
export async function register(email: string, password: string, display_name?: string) {
  const res = await fetch(`${API}/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, display_name: display_name || null }) });
  if (!res.ok) throw await toError(res);
  const t = await res.json(); tokens.set(t.access_token, t.refresh_token);
}
export async function logout() {
  const rt = tokens.refresh();
  tokens.clear();
  if (rt) await fetch(`${API}/auth/logout`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) }).catch(() => {});
}
export async function restoreSession(): Promise<boolean> { return tokens.hasAccess() || (await tryRefresh()); }
