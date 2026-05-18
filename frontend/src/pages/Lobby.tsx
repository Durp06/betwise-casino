/**
 * Lobby.tsx — Table list with auto-refresh every 5s, Create Table button.
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
  waiting:  "Waiting",
  playing:  "Playing",
  finished: "Finished",
};

const STATUS_COLORS: Record<string, string> = {
  waiting:  "text-green-400",
  playing:  "text-chip-gold",
  finished: "text-white/40",
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
    <div className="min-h-screen bg-felt-green flex flex-col">
      {/* Nav */}
      <header className="bg-chipy-dark px-4 py-3 flex items-center justify-between">
        <h1 className="font-display text-chip-gold font-bold text-xl">{t("BetWise Casino")}</h1>
        <nav className="flex gap-3 text-sm">
          <button onClick={() => void navigate("/profile")} className="text-white/60 hover:text-white">
            {t("Profile")}
          </button>
          <button onClick={() => void navigate("/leaderboard")} className="text-white/60 hover:text-white">
            {t("Leaderboard")}
          </button>
        </nav>
      </header>

      <main className="flex-1 px-4 py-6 max-w-2xl mx-auto w-full">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-bold text-lg">{t("Open Tables")}</h2>
          <button
            onClick={() => void handleCreateTable()}
            disabled={creating}
            className="px-4 py-2 bg-chip-gold text-chipy-dark font-bold rounded-lg
              disabled:opacity-40 hover:bg-yellow-400 active:scale-95 transition-all
              min-h-[44px] text-sm"
            aria-busy={creating}
          >
            {creating ? <span role="status">{t("Creating...")}</span> : t("+ Create Table")}
          </button>
        </div>

        {actionError && (
          <p role="alert" className="text-card-red text-sm mb-3">{actionError}</p>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div role="status" aria-busy="true" className="flex flex-col gap-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-white/10 rounded-xl animate-pulse" />
            ))}
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div role="alert" className="text-card-red text-center py-8">
            {error}
            <button
              onClick={() => void fetchTables()}
              className="block mx-auto mt-2 text-white/60 underline text-sm"
            >
              {t("Retry")}
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && tables !== null && tables.length === 0 && (
          <p className="text-white/40 text-center py-8">
            {t("No tables open. Create one to start playing!")}
          </p>
        )}

        {/* Table list */}
        {!loading && !error && tables !== null && tables.length > 0 && (
          <div className="flex flex-col gap-2">
            {tables.map((table) => (
              <div
                key={table.id}
                className="bg-chipy-dark rounded-xl p-4 flex flex-col sm:flex-row
                  items-start sm:items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white font-medium truncate">{table.name}</span>
                    <span className={`text-xs font-bold ${STATUS_COLORS[table.status] ?? "text-white/60"}`}>
                      {STATUS_LABELS[table.status] ?? table.status}
                    </span>
                  </div>
                  <div className="text-xs text-white/40 mt-0.5">
                    {t("Bet:")} {formatCents(table.min_bet)}–{formatCents(table.max_bet)}
                    {" · "}
                    {table.seats_taken}/{table.max_seats} {t("players")}
                  </div>
                </div>
                <button
                  onClick={() => void handleJoin(table.id)}
                  disabled={joining !== null || table.seats_taken >= table.max_seats}
                  className="px-4 py-2 bg-felt-green text-white font-bold rounded-lg
                    disabled:opacity-40 disabled:cursor-not-allowed
                    hover:bg-green-700 active:scale-95 transition-all
                    min-h-[44px] text-sm whitespace-nowrap"
                  aria-busy={joining === table.id}
                >
                  {joining === table.id
                    ? <span role="status">{t("Joining...")}</span>
                    : table.seats_taken >= table.max_seats
                    ? t("Full")
                    : t("Join")}
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
