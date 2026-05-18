/**
 * Login.tsx — rubber-hose Cuphead pivot.
 *
 * Centered cream card with thick ink outline + offset shadow.
 * Chipy waving above. Frontier vintage casino vibe.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { supabase, useSession } from "../auth/supabase";
import { createMe } from "../api/client";
import { t } from "../i18n";
import Chipy from "../components/Chipy";

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
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#1A0A00" }}>
        <span role="status" aria-busy="true" className="font-flavor text-cream/70 animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-4 py-10 gap-6"
      style={{ backgroundColor: "#1A0A00" }}
    >
      {/* Chipy mascot greeting — large + idle bob */}
      <div className="chipy-animate-idle">
        <Chipy size={200} expression="happy" animation="none" pose="wave" />
      </div>

      {/* Card */}
      <div
        className="ink-outline-thick paper-grain w-full max-w-sm rounded-lg px-6 py-7 flex flex-col gap-4 wobble"
        style={{
          backgroundColor: "#F5F0E8",
          boxShadow: "8px 8px 0 0 #1A0A00",
        }}
      >
        {/* Wordmark */}
        <div className="text-center">
          <h1 className="font-display text-6xl text-action-hit gold-drop leading-none">
            BetWise
          </h1>
          <p className="font-display text-gold-mid text-2xl tracking-widest mt-1">
            CASINO
          </p>
          <p className="font-flavor text-ink/70 text-sm mt-2 italic">
            Est. 2026 · Fake Money, Real Strategy
          </p>
        </div>

        {/* Mode toggle */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode("sign-in")}
            className={`ink-outline ink-shadow-sm flex-1 py-2 rounded-md font-ui
              uppercase tracking-wider text-xs
              ${mode === "sign-in" ? "bg-action-hit text-cream" : "bg-cream text-ink"}`}
          >
            {t("Sign In")}
          </button>
          <button
            type="button"
            onClick={() => setMode("sign-up")}
            className={`ink-outline ink-shadow-sm flex-1 py-2 rounded-md font-ui
              uppercase tracking-wider text-xs
              ${mode === "sign-up" ? "bg-action-double text-cream" : "bg-cream text-ink"}`}
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
              className="ink-outline font-flavor w-full px-3 py-2 bg-cream text-ink
                placeholder-ink/40 focus:outline-none focus:ring-2 focus:ring-action-double
                min-h-[44px]"
            />
          )}
          <input
            type="email"
            placeholder={t("Email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="ink-outline font-flavor w-full px-3 py-2 bg-cream text-ink
              placeholder-ink/40 focus:outline-none focus:ring-2 focus:ring-action-double
              min-h-[44px]"
          />
          <input
            type="password"
            placeholder={t("Password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="ink-outline font-flavor w-full px-3 py-2 bg-cream text-ink
              placeholder-ink/40 focus:outline-none focus:ring-2 focus:ring-action-double
              min-h-[44px]"
          />

          {error && (
            <p role="alert" className="font-flavor text-action-hit text-sm text-center italic">
              {error}
            </p>
          )}
          {message && (
            <p className="font-flavor text-action-stand text-sm text-center italic">
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="ink-outline ink-shadow w-full py-3 rounded-md font-display
              text-2xl tracking-wider uppercase
              disabled:opacity-40 disabled:cursor-not-allowed
              min-h-[52px]"
            style={{ backgroundColor: "#C0392B", color: "#F5F0E8" }}
            aria-busy={loading}
          >
            {loading
              ? t("Loading...")
              : mode === "sign-in"
              ? t("Step Inside")
              : t("Sign Up")}
          </button>
        </form>
      </div>
    </div>
  );
}
