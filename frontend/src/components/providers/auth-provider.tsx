"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useMe } from "@/lib/hooks";
import { NyaApi } from "@/lib/api";
import type { MeResponse } from "@/lib/types";

const TOKEN_KEY = "nya.token";
const SESSION_MARKER = "session";

type AuthContextValue = {
  token: string | null;
  setToken: (token: string | null) => void;
  login: (username: string, password: string, remember?: boolean) => Promise<MeResponse>;
  register: (username: string, password: string, inviteCode?: string, remember?: boolean) => Promise<MeResponse>;
  logout: () => Promise<void>;
  ready: boolean;
  me: MeResponse | null;
  meLoading: boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [sessionVersion, setSessionVersion] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  const setToken = useCallback((next: string | null) => {
    if (next === null) {
      void NyaApi.logout().finally(() => setSessionVersion((value) => value + 1));
    }
  }, []);

  const login = useCallback(async (username: string, password: string, remember = true) => {
    const me = await NyaApi.login(username, password, remember);
    setSessionVersion((value) => value + 1);
    return me;
  }, []);

  const register = useCallback(
    async (username: string, password: string, inviteCode?: string, remember = true) => {
      const me = await NyaApi.register(username, password, inviteCode, remember);
      setSessionVersion((value) => value + 1);
      return me;
    },
    []
  );

  const logout = useCallback(async () => {
    await NyaApi.logout();
    setSessionVersion((value) => value + 1);
  }, []);

  const meQuery = useMe(sessionVersion);
  const me = meQuery.data ?? null;
  const token = me && me.role !== "guest" ? SESSION_MARKER : null;
  const authReady = ready && !meQuery.isLoading;

  const value = useMemo(
    () => ({
      token,
      setToken,
      login,
      register,
      logout,
      ready: authReady,
      me,
      meLoading: meQuery.isFetching,
    }),
    [token, setToken, login, register, logout, authReady, me, meQuery.isFetching]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
