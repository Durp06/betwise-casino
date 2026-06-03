/**
 * PaiGowLobby.tsx — Pai Gow Poker table list + create form.
 *
 * Minimal additive — does NOT touch the existing blackjack Lobby. The main
 * Lobby gets a one-line link to /pai-gow/lobby.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPaiGowTable, joinPaiGowTable, listPaiGowTables } from "../api/client";
import type { PaiGowTableListItem } from "../types";
import { t } from "../i18n";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(0)}`;
}

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

  return (
    <main className="min-h-screen bg-felt-green p-4 sm:p-6">
      <header className="max-w-3xl mx-auto mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-cream text-3xl sm:text-4xl tracking-wider">
            {t("Pai Gow Poker")}
          </h1>
          <p className="font-flavor text-cream/70 text-sm italic">
            {t("House-banked. Split 7 cards into front + back. Beat the dealer.")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void navigate("/lobby")}
          className="px-3 py-2 rounded-md border-[3px] border-ink bg-cream text-ink
            font-ui uppercase text-xs"
        >
          {t("← All games")}
        </button>
      </header>

      <section className="max-w-3xl mx-auto" aria-busy={loading}>
        {loading && <p className="text-cream font-ui">{t("Loading…")}</p>}
        {error !== null && (
          <p role="alert" className="text-red-300 font-ui">
            {t("Failed to load tables:")} {error}
          </p>
        )}

        {tables !== null && tables.length === 0 && (
          <p className="text-cream/70 font-flavor italic">
            {t("No tables yet. Create one.")}
          </p>
        )}

        {tables !== null && tables.length > 0 && (
          <ul className="space-y-3">
            {tables.map((tbl) => (
              <li
                key={tbl.id}
                className="ink-outline-thick shadow-[4px_4px_0_0_#1A0A00] rounded-md p-3 sm:p-4
                  bg-cream text-ink flex flex-col sm:flex-row sm:items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <h2 className="font-display text-xl tracking-wider truncate">{tbl.name}</h2>
                  <p className="font-ui text-xs">
                    {t("Min")} {formatCents(tbl.min_bet_cents)} · {t("Max")}{" "}
                    {formatCents(tbl.max_bet_cents)} · {tbl.seats_taken}/{tbl.max_seats}{" "}
                    {t("seated")}
                    {tbl.active_round_status !== null && (
                      <> · {tbl.active_round_status}</>
                    )}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleJoin(tbl.id)}
                  disabled={joining !== null || tbl.seats_taken >= tbl.max_seats}
                  className="px-4 py-3 rounded-md border-[3px] border-ink bg-gold-bright
                    font-ui uppercase text-xs tracking-widest min-h-[44px]
                    disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {joining === tbl.id ? t("Joining…") : t("Sit down")}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6">
          {!showCreate && (
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="px-4 py-3 rounded-md border-[3px] border-ink bg-cream text-ink
                font-ui uppercase tracking-widest min-h-[44px]"
            >
              {t("Create table")}
            </button>
          )}
          {showCreate && (
            <div className="ink-outline-thick rounded-md p-3 bg-cream text-ink space-y-2">
              <label className="block font-ui text-xs uppercase tracking-widest">
                {t("Table name")}
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                maxLength={100}
                className="w-full px-2 py-2 border-[3px] border-ink rounded-md font-body"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={creating || newName.trim() === ""}
                  className="px-4 py-2 rounded-md border-[3px] border-ink bg-gold-bright
                    font-ui uppercase text-xs tracking-widest disabled:opacity-40"
                >
                  {creating ? t("Creating…") : t("Create")}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-md border-[3px] border-ink bg-cream text-ink
                    font-ui uppercase text-xs tracking-widest"
                >
                  {t("Cancel")}
                </button>
              </div>
            </div>
          )}
          {actionError !== null && (
            <p role="alert" className="text-red-300 font-ui mt-2">
              {actionError}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
