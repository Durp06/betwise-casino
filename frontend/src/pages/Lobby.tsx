/**
 * Lobby.tsx — table list with auto-refresh + Cuphead styling.
 *
 * Dark background, cream plaques with thick ink outlines + offset shadows,
 * stamped status marks, waving Chipy in the corner.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { TableListRow } from "../types";
import { listTables, createTable, joinTable } from "../api/client";
import { t } from "../i18n";
import Chipy from "../components/Chipy";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(0)}`;
}

const STATUS_LABELS: Record<string, string> = {
  waiting:  "Open",
  playing:  "Playing",
  finished: "Closed",
};

const STATUS_COLORS: Record<string, string> = {
  waiting:  "text-action-stand",
  playing:  "text-action-hit",
  finished: "text-ink/40",
};

export default function Lobby() {
  const navigate = useNavigate();
  const [tables, setTables] = useState<TableListRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchTables = useCallback(async () => {
    const result = await listTables();
    if (result.error) setError(result.error);
    else {
      setTables(result.data);
      setError(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void fetchTables();
    const id = setInterval(() => { void fetchTables(); }, 5000);
    return () => clearInterval(id);
  }, [fetchTables]);

  async function handleCreateTable(): Promise<void> {
    setCreating(true);
    setActionError(null);
    const result = await createTable({ name: `Table ${Date.now() % 10000}` });
    setCreating(false);
    if (result.error) setActionError(result.error);
    else await fetchTables();
  }

  async function handleJoin(tableId: string): Promise<void> {
    setJoining(tableId);
    setActionError(null);
    const result = await joinTable(tableId);
    setJoining(null);
    if (result.error) setActionError(result.error);
    else void navigate(`/table/${tableId}`);
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <div className="flex items-center gap-3">
          <h1 className="font-display text-cream text-4xl sm:text-5xl gold-drop leading-none">
            BetWise
          </h1>
          <span className="font-display text-gold-mid text-xl tracking-widest hidden sm:inline">
            CASINO
          </span>
        </div>
        <nav className="flex items-center gap-4">
          <button
            onClick={() => void navigate("/profile")}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("Profile")}
          </button>
          <button
            onClick={() => void navigate("/leaderboard")}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("Leaderboard")}
          </button>
          <div className="chipy-animate-idle ml-2 hidden sm:block">
            <Chipy size={80} expression="idle" animation="none" pose="wave" />
          </div>
        </nav>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6 gap-2 flex-wrap">
          <div className="flex flex-col">
            <h2
              className="text-cream text-4xl sm:text-5xl gold-drop leading-tight"
              style={{ fontFamily: "'Luckiest Guy', Impact, sans-serif", letterSpacing: "0.04em" }}
            >
              Open Tables
            </h2>
            <span className="font-flavor text-cream/70 text-sm italic">
              {t("Find a seat — house always watches.")}
            </span>
          </div>
          <button
            onClick={() => void handleCreateTable()}
            disabled={creating}
            className="ink-outline-thick ink-shadow font-display tracking-wider
              px-5 py-3 rounded-md text-cream text-lg uppercase
              disabled:opacity-40 min-h-[52px]"
            style={{ backgroundColor: "#C0392B" }}
            aria-busy={creating}
          >
            {creating ? t("Dealing…") : t("Open Table")}
          </button>
        </div>

        {actionError && (
          <p role="alert" className="font-flavor text-action-hit text-sm mb-3 italic">
            {actionError}
          </p>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div role="status" aria-busy="true" className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="ink-outline h-20 rounded-md animate-pulse"
                style={{ backgroundColor: "#F5F0E8", opacity: 0.5 }}
              />
            ))}
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div role="alert" className="text-center py-8">
            <p className="font-flavor text-action-hit italic">{error}</p>
            <button
              onClick={() => void fetchTables()}
              className="mt-3 font-ui text-cream uppercase tracking-wider text-sm underline"
            >
              {t("Try again")}
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && tables !== null && tables.length === 0 && (
          <div className="text-center py-12">
            <Chipy size={120} expression="thinking" animation="idle" pose="rest" />
            <p className="font-flavor text-cream italic mt-3 mb-1">
              {t("Empty house tonight.")}
            </p>
            <p className="font-flavor text-cream/60 text-sm">
              {t("Open a table and someone'll wander in.")}
            </p>
          </div>
        )}

        {/* Table list */}
        {!loading && !error && tables !== null && tables.length > 0 && (
          <div className="flex flex-col gap-4">
            {tables.map((table) => {
              const isFull = table.seats_taken >= table.max_seats;
              const statusKey = table.status as keyof typeof STATUS_LABELS;
              return (
                <div
                  key={table.id}
                  className="ink-outline-thick paper-grain rounded-md p-5
                    flex flex-col sm:flex-row items-start sm:items-center gap-3 wobble"
                  style={{
                    backgroundColor: "#F5F0E8",
                    boxShadow: "5px 5px 0 0 #1A0A00",
                    animationDelay: `${Math.random() * 2}s`,
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-display text-ink text-3xl truncate">
                        {table.name}
                      </span>
                      <span
                        className={`stamped text-xl ${STATUS_COLORS[table.status] ?? "text-ink/60"}`}
                      >
                        {STATUS_LABELS[statusKey] ?? table.status}
                      </span>
                    </div>
                    <div className="font-flavor text-ink/70 text-xs mt-1 flex items-center gap-2">
                      <span className="text-action-double">
                        {formatCents(table.min_bet)}–{formatCents(table.max_bet)}
                      </span>
                      <span>·</span>
                      <span>{table.seats_taken}/{table.max_seats} {t("seated")}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => void handleJoin(table.id)}
                    disabled={joining !== null || isFull}
                    className={`ink-outline-thick ink-shadow font-display tracking-wider
                      px-5 py-3 rounded-md text-base text-cream uppercase
                      ${isFull ? "bg-ink/40 cursor-not-allowed opacity-50" : "bg-action-stand"}
                      min-h-[52px]`}
                    aria-busy={joining === table.id}
                  >
                    {joining === table.id
                      ? t("…")
                      : isFull
                      ? t("Full")
                      : t("Take Seat")}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
