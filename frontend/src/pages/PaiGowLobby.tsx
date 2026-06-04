/**
 * PaiGowLobby.tsx — Pai Gow Poker table browser at /pai-gow/lobby.
 *
 * Same shared chrome (GameLobbyShell) + cream-plaque table rows as the
 * Blackjack / Hold'em lobbies, so every game's table list looks the same.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPaiGowTable, joinPaiGowTable, listPaiGowTables } from "../api/client";
import type { PaiGowTableListItem } from "../types";
import { t } from "../i18n";
import { formatMoney } from "../utils/money";
import GameLobbyShell from "../components/GameLobbyShell";
import PaiGowRulesModal from "../components/PaiGowRulesModal";
import { StaggerList, StaggerItem } from "../motion/presence/StaggerList";
import { AnimatePresence } from "framer-motion";

export default function PaiGowLobby() {
  const navigate = useNavigate();
  const [tables, setTables] = useState<PaiGowTableListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [showRules, setShowRules] = useState(false);

  const fetchTables = useCallback(async () => {
    const res = await listPaiGowTables();
    if (res.data === null) {
      setError(res.error);
      setLoading(false);
      return;
    }
    setTables(res.data);
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    void fetchTables();
    const id = setInterval(() => { void fetchTables(); }, 5000);
    return () => clearInterval(id);
  }, [fetchTables]);

  async function handleCreate(): Promise<void> {
    if (newName.trim() === "") return;
    setActionError(null);
    setCreating(true);
    const res = await createPaiGowTable({ name: newName.trim() });
    setCreating(false);
    if (res.data === null) {
      setActionError(res.error);
      return;
    }
    setShowCreate(false);
    setNewName("");
    await fetchTables();
  }

  async function handleJoin(tableId: string): Promise<void> {
    setActionError(null);
    setJoining(tableId);
    const res = await joinPaiGowTable(tableId);
    setJoining(null);
    if (res.data === null) {
      setActionError(res.error);
      return;
    }
    void navigate(`/pai-gow/table/${tableId}`);
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
        type="button"
        onClick={() => setShowCreate((v) => !v)}
        className="ink-outline-thick ink-shadow font-display tracking-wider
          px-5 py-3 rounded-md text-cream text-lg uppercase min-h-[52px]"
        style={{ backgroundColor: "#C0392B" }}
      >
        {t("New Table")}
      </button>
    </div>
  );

  return (
    <GameLobbyShell
      title={t("Pai Gow Poker")}
      subtitle={t("House-banked. Split 7 cards into front + back. Beat the dealer.")}
      action={headerActions}
    >
      {actionError !== null && (
        <p role="alert" className="font-flavor text-action-hit text-sm mb-3 italic">
          {actionError}
        </p>
      )}

      {/* Create form */}
      {showCreate && (
        <div
          className="ink-outline-thick paper-grain rounded-md p-4 mb-4 space-y-2"
          style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
        >
          <label className="block font-ui text-ink text-xs uppercase tracking-widest">
            {t("Table name")}
          </label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={100}
            className="w-full px-2 py-2 border-[3px] border-ink rounded-md font-body text-ink"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={creating || newName.trim() === ""}
              className="ink-outline ink-shadow px-4 py-2 rounded-md bg-gold-bright text-ink
                font-ui uppercase text-xs tracking-widest disabled:opacity-40"
            >
              {creating ? t("Creating…") : t("Create")}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="ink-outline px-4 py-2 rounded-md bg-cream text-ink
                font-ui uppercase text-xs tracking-widest"
            >
              {t("Cancel")}
            </button>
          </div>
        </div>
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
      {!loading && error !== null && (
        <div role="alert" className="text-center py-8">
          <p className="font-flavor text-action-hit italic">
            {t("Failed to load tables:")} {error}
          </p>
          <button
            onClick={() => void fetchTables()}
            className="mt-3 font-ui text-cream uppercase tracking-wider text-sm underline"
          >
            {t("Try again")}
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && error === null && tables !== null && tables.length === 0 && (
        <div className="text-center py-12">
          <p className="font-flavor text-cream italic mt-3 mb-1">{t("No tables yet. Create one.")}</p>
        </div>
      )}

      {/* Table list */}
      {!loading && error === null && tables !== null && tables.length > 0 && (
        <StaggerList className="flex flex-col gap-4">
          {tables.map((tbl) => {
            const isFull = tbl.seats_taken >= tbl.max_seats;
            return (
              <StaggerItem key={tbl.id}>
              <div
                className="ink-outline-thick paper-grain rounded-md p-5
                  flex flex-col sm:flex-row items-start sm:items-center gap-3"
                style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
              >
                <div className="flex-1 min-w-0">
                  <span className="font-display text-ink text-3xl truncate">{tbl.name}</span>
                  <div className="font-flavor text-ink/70 text-xs mt-1 flex items-center gap-2 flex-wrap">
                    <span className="text-action-double">
                      {formatMoney(tbl.min_bet_cents)}–{formatMoney(tbl.max_bet_cents)}
                    </span>
                    <span>·</span>
                    <span>{tbl.seats_taken}/{tbl.max_seats} {t("seated")}</span>
                    {tbl.active_round_status !== null && (
                      <>
                        <span>·</span>
                        <span>{tbl.active_round_status}</span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void handleJoin(tbl.id)}
                  disabled={joining !== null || isFull}
                  className={`ink-outline-thick ink-shadow font-display tracking-wider
                    px-5 py-3 rounded-md text-base text-cream uppercase min-h-[52px]
                    ${isFull ? "bg-ink/40 cursor-not-allowed opacity-50" : "bg-action-stand"}`}
                  aria-busy={joining === tbl.id}
                >
                  {joining === tbl.id ? t("…") : isFull ? t("Full") : t("Sit Down")}
                </button>
              </div>
              </StaggerItem>
            );
          })}
        </StaggerList>
      )}

      <AnimatePresence>
        {showRules && <PaiGowRulesModal key="rules" onClose={() => setShowRules(false)} />}
      </AnimatePresence>
    </GameLobbyShell>
  );
}
