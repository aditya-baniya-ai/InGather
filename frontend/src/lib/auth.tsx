import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Me, type TokenOut } from "./api";

interface AuthValue {
  me: Me | undefined;
  isLoading: boolean;
  signedIn: boolean;
  signIn: (t: TokenOut) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [token, setToken] = useState(api.token);

  const signOut = useCallback(() => {
    api.setToken(null);
    setToken(null);
    qc.clear();
    navigate("/login", { replace: true });
  }, [qc, navigate]);

  useEffect(() => {
    api.onUnauthorized = () => {
      setToken(null);
      qc.clear();
      navigate("/login", { replace: true });
    };
  }, [qc, navigate]);

  const signIn = useCallback((t: TokenOut) => {
    qc.clear(); // never let one account's cached data render for another
    api.setToken(t.access_token);
    setToken(t.access_token);
    qc.setQueryData(["me"], t.user);
  }, [qc]);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: api.me, enabled: !!token, staleTime: 30_000 });

  const value = useMemo<AuthValue>(() => ({
    me: meQuery.data,
    isLoading: !!token && meQuery.isPending,
    signedIn: !!token,
    signIn,
    signOut,
  }), [meQuery.data, meQuery.isPending, token, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
