/**
 * Lobby.tsx — Table list with auto-refresh every 5s, Create Table button.
 *
 * Saloon styling: panels feel like wooden seat cards, brass dividers,
 * amber CTAs, oxblood "Join" buttons.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { TableListRow } from "../types";
import { listTables, createTable, joinTable } from "../api/client";
import { t } from "../i18n";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(0)}`;
}

const STATUS_LABELS: Record<string, string> = {
  waiting:  "Open",
  playing:  "In Hand",
  finished: "Closed",
};

const STATUS_COLORS: Record<string, string> = {
  waiting:  "text-saloon-amber",
  playing:  "text-saloon-blood",
  finished: "text-saloon-ash/60",
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
    if (result.error) {
      setError(result.error);
    } else {
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
    if (result.error) {
      setActionError(result.error);
    } else {
      await fetchTables();
    }
  }

  async function handleJoin(tableId: string): Promise<void> {
    setJoining(tableId);
    setActionError(null);
    const result = await joinTable(tableId);
    setJoining(null);
    if (result.error) {
      setActionError(result.error);
    } else {
      void navigate(`/table/${tableId}`);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header — walnut panel with brass underline */}
      <header className="saloon-panel px-4 py-3 flex items-center justify-between
        border-b border-saloon-brass/40">
        <h1 className="wordmark text-2xl">
          {t("BetWise")}
        </h1>
        <nav className="flex gap-4 text-sm uppercase tracking-wider">
          <button
            onClick={() => void navigate("/profile")}
            className="text-saloon-ash hover:text-saloon-parchment transition-colors"
          >
            {t("Profile")}
          </button>
          <button
            onClick={() => void navigate("/leaderboard")}
            className="text-saloon-ash hover:text-saloon-parchment transition-colors"
          >
            {t("Leaderboard")}
          </button>
        </nav>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        <div className="flex items-center justify-between mb-5">
          <div className="flex flex-col">
            <h2 className="text-saloon-parchment text-2xl">{t("Open Tables")}</h2>
            <span className="text-saloon-ash/70 text-xs uppercase tracking-widest">
              {t("Find a seat")}
            </span>
          </div>
          <button
            onClick={() => void handleCreateTable()}
            disabled={creating}
            className="btn-leather px-4 py-2 rounded-md font-bold uppercase tracking-wider
              text-xs disabled:opacity-40 min-h-[44px]"
            aria-busy={creating}
          >
            {creating ? <span role="status">{t("Dealing...")}</span> : t("Open Table")}
          </button>
        </div>

        {/* Hairline brass divider */}
        <div className="h-px bg-saloon-brass/30 mb-5" />

        {actionError && (
          <p role="alert" className="text-saloon-blood text-sm mb-3 italic">{actionError}</p>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div role="status" aria-busy="true" className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 saloon-panel rounded-md animate-pulse opacity-50" />
            ))}
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div role="alert" className="text-center py-8">
            <p className="text-saloon-blood italic">{error}</p>
            <button
              onClick={() => void fetchTables()}
              className="mt-3 text-saloon-amber underline text-sm uppercase tracking-wider"
            >
              {t("Try again")}
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && tables !== null && tables.length === 0 && (
          <div className="text-center py-12">
            <p className="text-saloon-ash italic mb-2">
              {t("Empty house tonight.")}
            </p>
            <p className="text-saloon-ash/60 text-sm">
              {t("Open a table and someone'll wander in.")}
            </p>
          </div>
        )}

        {/* Table list */}
        {!loading && !error && tables !== null && tables.length > 0 && (
          <div className="flex flex-col gap-3 stagger-rows">
            {tables.map((table) => {
              const isFull = table.seats_taken >= table.max_seats;
              return (
                <div
                  key={table.id}
                  className="saloon-panel hoverable-card chrome-in rounded-md p-4
                    flex flex-col sm:flex-row items-start sm:items-center gap-3
                    ring-1 ring-saloon-brass/25 hover:ring-saloon-brass/55"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span
                        className="text-saloon-parchment font-semibold text-lg truncate"
                        style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
                      >
                        {table.name}
                      </span>
                      <span
                        className={`text-[10px] font-bold uppercase tracking-widest
                          px-2 py-0.5 rounded-sm ring-1 ring-current/40
                          ${STATUS_COLORS[table.status] ?? "text-saloon-ash"}`}
                      >
                        {STATUS_LABELS[table.status] ?? table.status}
                      </span>
                    </div>
                    <div className="text-xs text-saloon-ash mt-1 flex items-center gap-2">
                      <span className="text-saloon-amber/90">
                        {formatCents(table.min_bet)}–{formatCents(table.max_bet)}
                      </span>
                      <span className="text-saloon-ash/40">·</span>
                      <span>{table.seats_taken}/{table.max_seats} {t("seated")}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => void handleJoin(table.id)}
                    disabled={joining !== null || isFull}
                    className={`px-4 py-2 rounded-md text-xs font-bold uppercase tracking-wider
                      min-h-[44px] whitespace-nowrap transition-all
                      ${isFull
                        ? "bg-saloon-night/40 text-saloon-ash/60 cursor-not-allowed"
                        : "bg-saloon-leather text-saloon-parchment hover:bg-saloon-blood active:scale-95"}
                      ring-1 ring-saloon-brass/40`}
                    aria-busy={joining === table.id}
                  >
                    {joining === table.id
                      ? <span role="status">{t("...")}</span>
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
