// src/auth.tsx — receives the shell-issued SSO JWT (see
// shell-dashboard/docs/JWT_CONTRACT.md) rather than doing its own
// Google login. The shell's Launcher opens this dashboard at
// http://localhost:5181/?token=<jwt> (or, once this dashboard shows
// its own "not signed in" screen, a manual paste of the token for
// local dev without the shell running). We persist it in
// localStorage exactly like VLS does with its own JWT, and verify it
// server-side via GET /me on load (this dashboard's own backend
// re-checks elektrica.staff_user, per the contract's fail-closed
// re-check discipline -- never trust the token's baked-in role).
import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

const STORAGE_KEY = 'elektrica_dashboard_token';
const API_BASE = import.meta.env.VITE_API_BASE_URL as string;

export interface StaffSession {
  person_id: number;
  google_email: string;
  role: 'owner' | 'staff';
  staff_user_id: number;
}

interface AuthContextValue {
  token: string | null;
  staff: StaffSession | null;
  loading: boolean;
  error: string | null;
  setToken: (t: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => {
    // A token in the URL (?token=...), as the shell's Launcher would
    // pass it, always wins over a stale stored one.
    const fromUrl = new URLSearchParams(window.location.search).get('token');
    if (fromUrl) {
      localStorage.setItem(STORAGE_KEY, fromUrl);
      // Strip it from the visible URL so it doesn't linger in
      // browser history / get shared accidentally.
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      window.history.replaceState({}, '', url.toString());
      return fromUrl;
    }
    return localStorage.getItem(STORAGE_KEY);
  });
  const [staff, setStaff] = useState<StaffSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const setToken = (t: string) => {
    localStorage.setItem(STORAGE_KEY, t);
    setTokenState(t);
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setTokenState(null);
    setStaff(null);
  };

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? `Sign-in check failed (${res.status})`);
        }
        return res.json();
      })
      .then((body: StaffSession) => setStaff(body))
      .catch((e: Error) => {
        setError(e.message);
        logout();
      })
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <AuthContext.Provider value={{ token, staff, loading, error, setToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}
