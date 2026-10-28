import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import * as client from "./api";
import { api } from "./api";
import type { User } from "./types";

interface AuthState { user: User | null; loading: boolean; signIn: (e: string, p: string) => Promise<void>; signUp: (e: string, p: string, n?: string) => Promise<void>; signOut: () => Promise<void>; reload: () => Promise<void> }
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const reload = useCallback(async () => { setUser(await api<User>("/users/me")); }, []);
  useEffect(() => {
    (async () => {
      try { if (await client.restoreSession()) await reload(); } catch { client.tokens.clear(); }
      setLoading(false);
    })();
  }, [reload]);

  const value: AuthState = {
    user, loading, reload,
    signIn: async (e, p) => { await client.login(e, p); await reload(); },
    signUp: async (e, p, n) => { await client.register(e, p, n); await reload(); },
    signOut: async () => { await client.logout(); qc.clear(); setUser(null); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <p className="p-8 text-muted" role="status">Loading…</p>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}
