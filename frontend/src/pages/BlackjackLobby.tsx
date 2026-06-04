/**
 * BlackjackLobby.tsx — Blackjack's own table browser at /blackjack.
 *
 * Same shape as the Hold'em / Pai Gow lobbies (via GameLobbyShell): browse
 * live tables, open a new one (which drops you straight onto the felt), or
 * take a seat at an existing table.
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { TableListRow } from "../types";
import { listTables, createTable, joinTable } from "../api/client";
import { t } from "../i18n";
import { generateTableName } from "../utils/tableName";
import { formatMoney } from "../utils/money";
import GameLobbyShell from "../components/GameLobbyShell";
import Chipy from "../components/Chipy";
import BlackjackRulesModal from "../components/BlackjackRulesModal";

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

export default function BlackjackLobby() {
  const navigate = useNavigate();
  const [tables, setTables] = useState<TableListRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showRules, setShowRules] = useState(false);

  const fetchTables = useCallback(async () => {
    const result = await listTables();
    if (result.error) setError(result.error);
    else {
      setTables(result.data?.filter((tbl) => tbl.status !== "finished") ?? null);
      setError(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void fetchTables();
    const id = setInterval(() => { void fetchTables(); }, 5000);
    return () => clearInterval(id);
  }, [fetchTables]);

  // Open a table AND drop the player straight onto the felt.
  async function handleCreateTable(): Promise<void> {
    setCreating(true);
    setActionError(null);
    const result = await createTable({ name: generateTableName() });
    setCreating(false);
    if (result.error) {
      setActionError(result.error);
      return;
    }
    if (result.data) {
      const id = result.data.id;
      const joinResult = await joinTable(String(id));
      if (joinResult.error) {
        setActionError(joinResult.error);
        return;
      }
      void navigate(`/table/${String(id)}`);
    } else {
      await fetchTables();
    }
  }

  async function handleJoin(tableId: string): Promise<void> {
    setJoining(tableId);
    setActionError(null);
    const result = await joinTable(tableId);
    setJoining(null);
    if (result.error) setActionError(result.error);
    else void navigate(`/table/${tableId}`);
  }

  const headerActions = (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => setShowRules(true)}
        className="ink-outline ink-shadow-sm font-ui uppercase tracking-wider
          text-xs sm:text-sm px-4 py-3 rounded-md bg-cream text-ink min-h-[52px]"
      >
        {t("How to Play")}
      </button>
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
  );

  return (
    <GameLobbyShell
      title={t("Blackjack")}
      subtitle={t("Beat the dealer to 21 — Chipy coaches every hand.")}
      action={headerActions}
    >
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
          {tables.map((table, index) => {
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
                  animationDelay: `${index * 0.15}s`,
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
                      {formatMoney(table.min_bet)}–{formatMoney(table.max_bet)}
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

      {showRules && <BlackjackRulesModal onClose={() => setShowRules(false)} />}
    </GameLobbyShell>
  );
}
