/**
 * Login.tsx — Supabase email/password auth + upsert on first login.
 *
 * Saloon styling: dim room with a single oxblood-leather booth panel in the
 * center, brass trim, candle-amber CTA, wood-type "BetWise Casino" logo.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { supabase, useSession } from "../auth/supabase";
import { createMe } from "../api/client";
import { t } from "../i18n";

export default function Login() {
  const navigate = useNavigate();
  const { session, loading: sessionLoading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionLoading && session) {
      void navigate("/lobby");
    }
  }, [session, sessionLoading, navigate]);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);

    if (mode === "sign-up") {
      if (username.length < 3 || username.length > 20) {
        setError(t("Username must be 3–20 characters"));
        setLoading(false);
        return;
      }
      const { error: authError } = await supabase.auth.signUp({ email, password });
      if (authError) {
        setError(authError.message);
        setLoading(false);
        return;
      }
      const result = await createMe(username);
      if (result.error) {
        setError(result.error);
        setLoading(false);
        return;
      }
      setMessage(t("Account created! Check your email to confirm."));
      setLoading(false);
    } else {
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) {
        setError(authError.message);
        setLoading(false);
        return;
      }
      await createMe(username || (email.split("@")[0] ?? "player"));
      void navigate("/lobby");
    }
  }

  if (sessionLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-saloon-parchment/60 animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-10">
      <div
        className="saloon-panel w-full max-w-sm rounded-2xl p-7 flex flex-col gap-5
          ring-1 ring-saloon-brass/30"
      >
        {/* Logo — engraved brass wordmark */}
        <div className="flex flex-col items-center gap-1 chrome-in">
          <h1 className="wordmark text-5xl text-center leading-none">
            BetWise
          </h1>
          <p
            className="text-saloon-brass tracking-[0.45em] text-xs uppercase engraved"
            style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
          >
            · Casino ·
          </p>
        </div>

        {/* Tagline — embossed serif */}
        <p className="text-saloon-ash text-sm text-center italic">
          {t("Fake money. Real strategy.")}
        </p>

        {/* Mode toggle */}
        <div className="flex rounded-md overflow-hidden ring-1 ring-saloon-brass/40">
          <button
            onClick={() => setMode("sign-in")}
            className={`flex-1 py-2 text-sm font-semibold transition-colors uppercase tracking-wider
              ${mode === "sign-in"
                ? "bg-saloon-amber/90 text-saloon-ink"
                : "text-saloon-ash hover:text-saloon-parchment"}`}
          >
            {t("Sign In")}
          </button>
          <button
            onClick={() => setMode("sign-up")}
            className={`flex-1 py-2 text-sm font-semibold transition-colors uppercase tracking-wider
              ${mode === "sign-up"
                ? "bg-saloon-amber/90 text-saloon-ink"
                : "text-saloon-ash hover:text-saloon-parchment"}`}
          >
            {t("Sign Up")}
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          {mode === "sign-up" && (
            <input
              type="text"
              placeholder={t("Username (3–20 chars)")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              maxLength={20}
              className="w-full px-3 py-3 rounded-md bg-saloon-night/60 text-saloon-parchment
                placeholder-saloon-ash/70 ring-1 ring-saloon-brass/30
                focus:outline-none focus:ring-saloon-amber/70
                min-h-[44px]"
            />
          )}
          <input
            type="email"
            placeholder={t("Email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-3 py-3 rounded-md bg-saloon-night/60 text-saloon-parchment
              placeholder-saloon-ash/70 ring-1 ring-saloon-brass/30
              focus:outline-none focus:ring-saloon-amber/70
              min-h-[44px]"
          />
          <input
            type="password"
            placeholder={t("Password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full px-3 py-3 rounded-md bg-saloon-night/60 text-saloon-parchment
              placeholder-saloon-ash/70 ring-1 ring-saloon-brass/30
              focus:outline-none focus:ring-saloon-amber/70
              min-h-[44px]"
          />

          {error && (
            <p role="alert" className="text-saloon-blood text-sm text-center italic">
              {error}
            </p>
          )}
          {message && (
            <p className="text-saloon-amber text-sm text-center italic">{message}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="btn-leather w-full py-3 rounded-md
              font-bold tracking-wider uppercase text-sm
              disabled:opacity-40 disabled:cursor-not-allowed
              min-h-[44px]"
            aria-busy={loading}
          >
            {loading ? (
              <span role="status">{t("Loading...")}</span>
            ) : mode === "sign-in" ? (
              t("Enter")
            ) : (
              t("Create Account")
            )}
          </button>
        </form>
      </div>

      {/* Tiny footer flourish */}
      <p className="mt-6 text-saloon-ash/60 text-xs tracking-widest uppercase">
        Est. 2026 · House Always Watches
      </p>
    </div>
  );
}
