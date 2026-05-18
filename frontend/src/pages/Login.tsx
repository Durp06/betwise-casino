/**
 * Login.tsx — Supabase email/password auth + upsert on first login.
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

  // Redirect if already authenticated
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
      // Upsert user profile
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
      // Upsert user profile (idempotent)
      await createMe(username || (email.split("@")[0] ?? "player"));
      void navigate("/lobby");
    }
  }

  if (sessionLoading) {
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-white animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-felt-green flex flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm bg-chipy-dark rounded-2xl p-6 flex flex-col gap-4">
        {/* Logo */}
        <h1 className="font-display text-chip-gold text-3xl font-bold text-center">
          {t("BetWise Casino")}
        </h1>
        <p className="text-white/60 text-sm text-center">
          {t("Fake money. Real strategy.")}
        </p>

        {/* Mode toggle */}
        <div className="flex rounded-lg overflow-hidden border border-white/20">
          <button
            onClick={() => setMode("sign-in")}
            className={`flex-1 py-2 text-sm font-medium transition-colors
              ${mode === "sign-in" ? "bg-chip-gold text-chipy-dark" : "text-white/60 hover:text-white"}`}
          >
            {t("Sign In")}
          </button>
          <button
            onClick={() => setMode("sign-up")}
            className={`flex-1 py-2 text-sm font-medium transition-colors
              ${mode === "sign-up" ? "bg-chip-gold text-chipy-dark" : "text-white/60 hover:text-white"}`}
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
              className="w-full px-3 py-3 rounded-lg bg-white/10 text-white
                placeholder-white/40 border border-white/20
                focus:outline-none focus:border-chip-gold
                min-h-[44px]"
            />
          )}
          <input
            type="email"
            placeholder={t("Email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-3 py-3 rounded-lg bg-white/10 text-white
              placeholder-white/40 border border-white/20
              focus:outline-none focus:border-chip-gold
              min-h-[44px]"
          />
          <input
            type="password"
            placeholder={t("Password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full px-3 py-3 rounded-lg bg-white/10 text-white
              placeholder-white/40 border border-white/20
              focus:outline-none focus:border-chip-gold
              min-h-[44px]"
          />

          {error && (
            <p role="alert" className="text-card-red text-sm text-center">
              {error}
            </p>
          )}
          {message && (
            <p className="text-green-400 text-sm text-center">{message}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-chip-gold text-chipy-dark font-bold rounded-lg
              disabled:opacity-40 disabled:cursor-not-allowed
              hover:bg-yellow-400 active:scale-95 transition-all
              min-h-[44px]"
            aria-busy={loading}
          >
            {loading ? (
              <span role="status">{t("Loading...")}</span>
            ) : mode === "sign-in" ? (
              t("Sign In")
            ) : (
              t("Create Account")
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
