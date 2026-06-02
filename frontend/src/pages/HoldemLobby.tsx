/**
 * HoldemLobby.tsx — browse / create / sit down at multiplayer Hold'em tables.
 *
 * Mirrors Lobby.tsx conventions: 5-second auto-refresh, loading + error +
 * empty states, the {data,error} client contract. Joining buys in (default =
 * the table minimum) and navigates to the live table.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { HoldemTableListRow } from "../types";
import { listHoldemTables, createHoldemTable, joinHoldemTable } from "../api/client";
import { t } from "../i18n";

function money(n: number): string {
  return `$${(n / 100).toFixed(2)}`;
}

export default function HoldemLobby() {
  const navigate = useNavigate();
  const [tables, setTables] = useState<HoldemTableListRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [buyIns, setBuyIns] = useState<Record<string, number>>({});

  const fetchTables = useCallback(async () => {
    const result = await listHoldemTables();
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

  async function handleCreate(): Promise<void> {
    setCreating(true);
    setActionError(null);
    const result = await createHoldemTable({
      name: `Hold'em ${Date.now() % 10000}`,
      small_blind: 50,
      big_blind: 100,
      min_buy_in: 2_000,
      max_buy_in: 20_000,
      max_seats: 6,
    });
    setCreating(false);
    if (result.error) setActionError(result.error);
    else await fetchTables();
  }

  async function handleJoin(table: HoldemTableListRow): Promise<void> {
    setJoining(table.id);
    setActionError(null);
    const buyIn = buyIns[table.id] ?? table.min_buy_in;
    const result = await joinHoldemTable(table.id, buyIn);
    setJoining(null);
    if (result.error) setActionError(result.error);
    else void navigate(`/holdem/table/${table.id}`);
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      <header
        className="flex items-center justify-between px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <h1 className="font-display text-cream text-3xl sm:text-4xl gold-drop leading-none">
          {t("Multiplayer Hold'em")}
        </h1>
        <button
          onClick={() => void navigate("/lobby")}
          className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
        >
          {t("Back to Lobby")}
        </button>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6 gap-2 flex-wrap">
          <span className="font-flavor text-cream/70 text-sm italic">
            {t("Cash ring games — buy in, sit down, play real hands against real people.")}
          </span>
          <button
            onClick={() => void handleCreate()}
            disabled={creating}
            className="ink-outline-thick ink-shadow font-display tracking-wider px-5 py-3 rounded-md text-cream text-lg uppercase disabled:opacity-40 min-h-[52px]"
            style={{ backgroundColor: "#C0392B" }}
            aria-busy={creating}
            data-testid="holdem-create-table"
          >
            {creating ? t("Dealing…") : t("New Table")}
          </button>
        </div>

        {actionError && (
          <p role="alert" className="font-flavor text-action-hit text-sm mb-3 italic">
            {actionError}
          </p>
        )}

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

        {!loading && !error && tables !== null && tables.length === 0 && (
          <div className="text-center py-12">
            <p className="font-flavor text-cream italic mt-3 mb-1">{t("No tables running.")}</p>
            <p className="font-flavor text-cream/60 text-sm">
              {t("Start one and wait for the table to fill.")}
            </p>
          </div>
        )}

        {!loading && !error && tables !== null && tables.length > 0 && (
          <div className="flex flex-col gap-4">
            {tables.map((table) => {
              const isFull = table.seats_taken >= table.max_seats;
              const buyIn = buyIns[table.id] ?? table.min_buy_in;
              return (
                <div
                  key={table.id}
                  className="ink-outline-thick paper-grain rounded-md p-5 flex flex-col sm:flex-row items-start sm:items-center gap-3"
                  style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
                  data-testid={`holdem-table-row-${table.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <span className="font-display text-ink text-2xl truncate">{table.name}</span>
                    <div className="font-flavor text-ink/70 text-xs mt-1 flex items-center gap-2 flex-wrap">
                      <span className="text-action-double">
                        {t("Blinds")} {money(table.small_blind)}/{money(table.big_blind)}
                      </span>
                      <span>·</span>
                      <span>{table.seats_taken}/{table.max_seats} {t("seated")}</span>
                      <span>·</span>
                      <span>{t("Buy-in")} {money(table.min_buy_in)}–{money(table.max_buy_in)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={table.min_buy_in}
                      max={table.max_buy_in}
                      step={table.big_blind}
                      value={buyIn}
                      onChange={(e) =>
                        setBuyIns((prev) => ({ ...prev, [table.id]: Number(e.target.value) }))
                      }
                      className="w-24 px-2 py-2 text-sm font-mono border-2 border-ink rounded bg-cream text-ink"
                      aria-label={t("Buy-in amount")}
                      data-testid={`holdem-buyin-${table.id}`}
                    />
                    <button
                      onClick={() => void handleJoin(table)}
                      disabled={joining !== null || isFull}
                      className={`ink-outline-thick ink-shadow font-display tracking-wider px-5 py-3 rounded-md text-base text-cream uppercase min-h-[52px] ${
                        isFull ? "bg-ink/40 cursor-not-allowed opacity-50" : "bg-action-stand"
                      }`}
                      aria-busy={joining === table.id}
                      data-testid={`holdem-join-${table.id}`}
                    >
                      {joining === table.id ? t("…") : isFull ? t("Full") : t("Sit Down")}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
