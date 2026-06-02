/**
 * auth/supabase.ts — singleton Supabase client.
 *
 * Reads VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY from import.meta.env.
 * Logs a clear warning instead of throwing if env vars are missing — build
 * must not fail in CI without Supabase configured.
 */
import { createClient, type Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "[BetWise] VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY is not set. " +
      "Auth features will not work. Set these in your .env file.",
  );
}

export const supabase = createClient(
  supabaseUrl ?? "https://placeholder.supabase.co",
  supabaseAnonKey ?? "placeholder-anon-key",
);

// ─── useSession ──────────────────────────────────────────────────────────────

interface UseSessionResult {
  session: Session | null;
  loading: boolean;
}

/**
 * useSession — subscribes to Supabase auth state changes.
 * Returns { session, loading } where loading is true until the initial
 * session check completes.
 */
export function useSession(): UseSessionResult {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    // Local-dev bypass: if VITE_DEV_USER_ID is set, fabricate a synthetic
    // Session so the AuthGate lets us through. Mirrors the backend's
    // BETWISE_DEV_USER_ID bypass. Never set this in production builds —
    // import.meta.env.DEV is the second guard.
    const devUserId = import.meta.env.VITE_DEV_USER_ID as string | undefined;
    if (import.meta.env.DEV && devUserId) {
      // Minimal Session shape — only what AuthGate / apiFetch consume.
      const fakeSession = {
        access_token: "dev-token",
        token_type: "bearer",
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        refresh_token: "dev-refresh",
        user: {
          id: devUserId,
          aud: "authenticated",
          email: "dev@local",
          app_metadata: {},
          user_metadata: {},
          created_at: new Date().toISOString(),
        },
      } as unknown as Session;
      setSession(fakeSession);
      setLoading(false);
      return;
    }

    // Get initial session
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    // Subscribe to changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  return { session, loading };
}
