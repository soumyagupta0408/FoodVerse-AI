import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { tokens } from "../lib/api";
import { AuthProvider } from "../lib/auth";

export type Handler = (req: { url: string; method: string; body: any }) => { status?: number; json?: unknown } | undefined;

/** Replaces fetch with a router: first matching handler wins. Returns the call log. */
export function mockFetch(handlers: Handler[]) {
  const calls: { url: string; method: string; body: any }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input).replace(/^https?:\/\/[^/]+/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    let body: any = init?.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* keep */ } }
    const call = { url, method, body };
    calls.push(call);
    for (const h of handlers) {
      const r = h(call);
      if (r) return new Response(r.status === 204 ? null : JSON.stringify(r.json ?? {}), { status: r.status ?? 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ error: { code: "not_mocked", message: `Unmocked ${method} ${url}` } }), { status: 404 });
  }));
  return calls;
}

export const USER = { id: "u1", email: "me@example.com", role: "user", profile: { display_name: "Asha", diet_pattern: null, allergies: [], excluded_ingredients: [], nutrition_goals: {}, cuisines: [] } };
export const meHandler: Handler = (r) => (r.url === "/api/v1/users/me" && r.method === "GET" ? { json: USER } : undefined);

export function renderApp(route = "/", { loggedIn = true } = {}) {
  localStorage.clear();
  if (loggedIn) tokens.set("access", "refresh"); else tokens.clear();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter initialEntries={[route]}><AuthProvider><App /></AuthProvider></MemoryRouter></QueryClientProvider>,
  );
}
