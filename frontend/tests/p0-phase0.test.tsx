/**
 * p0-phase0.test.tsx — Phase 0 frontend acceptance criteria (TDD RED phase).
 *
 * Covers:
 *   P0-1a  auto-join on create: navigate called with /table/<id>
 *   P0-1b  auto-join join error: alert shown, no navigation
 *   P0-1c  createTable error: unchanged path, no join attempt
 *   P0-2c  tableName util: returns non-empty string not matching /^Table \d+$/
 *   P0-2d  defensive client filter: finished row absent from DOM
 *   P0-3a  deterministic wobble: animation-delay identical across renders
 *   P0-4a  ink-shadow on action buttons (poker + holdem)
 *   P0-4b  busy state on action buttons (poker + holdem)
 *   P0-5a  "Choose a Game" heading appears before game cards and table list
 *   P0-6a  win state: banner-pulse + sparkle on banner
 *   P0-6b  loss/bust state: banner-pulse present, sparkle absent
 *   P0-7a  Chipy imageRendering === "crisp-edges" + spritePosition formula unchanged
 *   P0-7b  Chipy container has circular clip-path
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect, vi, beforeEach } from "vitest";

// ─── vi.hoisted mocks (must be declared before vi.mock factories) ─────────────

const { navigateMock, listTablesMock, createTableMock, joinTableMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  listTablesMock: vi.fn(),
  createTableMock: vi.fn(),
  joinTableMock: vi.fn(),
}));

// ─── Mock react-router-dom navigate ──────────────────────────────────────────

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

// ─── Mock API client ──────────────────────────────────────────────────────────

vi.mock("../src/api/client", () => ({
  listTables: listTablesMock,
  createTable: createTableMock,
  joinTable: joinTableMock,
  // BalanceHeader (mounted in Lobby / Table headers) fetches the bankroll on mount.
  getMe: vi.fn().mockResolvedValue({
    data: {
      id: "u", username: "tester", chip_balance: 5_000_000, total_hands: 0,
      correct_decisions: 0, accuracy: 0, current_streak: 0, best_streak: 0,
      created_at: "2026-06-03T00:00:00Z",
    },
    error: null,
  }),
  // Stubs for other imports inside Lobby/Table subcomponents
  leaveTable: vi.fn().mockResolvedValue({ data: { message: "left" }, error: null }),
  getTableState: vi.fn().mockResolvedValue({ data: null, error: null }),
  streamPreAdvice: vi.fn((_id: string, _chunk: unknown, onDone: () => void) => { onDone(); }),
  actPoker: vi.fn().mockResolvedValue({ data: {}, error: null }),
  actHoldem: vi.fn().mockResolvedValue({ data: {}, error: null }),
  getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
  postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
  getHandActions: vi.fn().mockResolvedValue({ data: [], error: null }),
  getSessionReview: vi.fn().mockResolvedValue({ data: null, error: null }),
  gradePractice: vi.fn().mockResolvedValue({ data: null, error: null }),
  streamAdvice: vi.fn(),
  dealHand: vi.fn().mockResolvedValue({ data: null, error: null }),
  takeAction: vi.fn().mockResolvedValue({ data: null, error: null }),
  listHoldemTables: vi.fn().mockResolvedValue({ data: [], error: null }),
}));

// ─── Mock supabase / useSession ───────────────────────────────────────────────

vi.mock("../src/auth/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  },
  useSession: vi.fn().mockReturnValue({
    session: { user: { id: "dev-user" } },
    loading: false,
  }),
}));

// ─── MSW server ───────────────────────────────────────────────────────────────

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterAll(() => server.close());
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

// ─── Restore mock implementations after clearAllMocks ────────────────────────

beforeEach(() => {
  navigateMock.mockImplementation(() => undefined);
  listTablesMock.mockResolvedValue({ data: [], error: null });
  createTableMock.mockResolvedValue({ data: null, error: null });
  joinTableMock.mockResolvedValue({ data: null, error: null });
});

// ─── Lazy imports (after mocks are set up) ───────────────────────────────────

// We import Lobby lazily so all vi.mock factories are established first.
// The dynamic import is inside each test/describe that needs it.

// ─────────────────────────────────────────────────────────────────────────────
// P0-1a: auto-join on create → navigate to /table/<id>
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-1a: createTable success → joinTable → navigate /table/:id", () => {
  it("calls navigate with /table/<id> after successful create+join", async () => {
    const TABLE_ID = "auto-join-table-id";
    createTableMock.mockResolvedValue({
      data: {
        id: TABLE_ID,
        name: "Fresh Table",
        min_bet: 500,
        max_bet: 50000,
        max_seats: 3,
        status: "waiting",
        created_at: new Date().toISOString(),
      },
      error: null,
    });
    joinTableMock.mockResolvedValue({ data: { id: "seat-1", user_id: "dev-user", seat_number: 1 }, error: null });
    listTablesMock.mockResolvedValue({ data: [], error: null });

    const Lobby = (await import("../src/pages/BlackjackLobby")).default;

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/lobby"]}>
        <Routes>
          <Route path="/lobby" element={<Lobby />} />
          <Route path="/table/:id" element={<div data-testid="table-sentinel" />} />
        </Routes>
      </MemoryRouter>,
    );

    // Wait for loading to settle
    await waitFor(() => expect(listTablesMock).toHaveBeenCalled());

    const openBtn = await screen.findByRole("button", { name: /open table/i });
    await user.click(openBtn);

    await waitFor(() => {
      expect(joinTableMock).toHaveBeenCalledWith(TABLE_ID);
      expect(navigateMock).toHaveBeenCalledWith(`/table/${TABLE_ID}`);
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-1b: joinTable error → role="alert", no navigate
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-1b: join error shows alert, no navigation", () => {
  it("shows role=alert and does NOT navigate when join fails", async () => {
    const TABLE_ID = "conflict-table-id";
    createTableMock.mockResolvedValue({
      data: {
        id: TABLE_ID,
        name: "Conflict Table",
        min_bet: 500,
        max_bet: 50000,
        max_seats: 3,
        status: "waiting",
        created_at: new Date().toISOString(),
      },
      error: null,
    });
    // Simulate 409 / join fails
    joinTableMock.mockResolvedValue({ data: null, error: "Table is full" });
    listTablesMock.mockResolvedValue({ data: [], error: null });

    const Lobby = (await import("../src/pages/BlackjackLobby")).default;

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/lobby"]}>
        <Routes>
          <Route path="/lobby" element={<Lobby />} />
          <Route path="/table/:id" element={<div data-testid="table-sentinel" />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(listTablesMock).toHaveBeenCalled());

    const openBtn = await screen.findByRole("button", { name: /open table/i });
    await user.click(openBtn);

    // Alert must appear
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    // No navigation must occur
    expect(navigateMock).not.toHaveBeenCalledWith(expect.stringMatching(/^\/table\//));
    // Sentinel should not be in the DOM
    expect(screen.queryByTestId("table-sentinel")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-1c: createTable error → unchanged path, no join attempt
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-1c: createTable error → no join attempt", () => {
  it("shows alert and does NOT call joinTable when createTable fails", async () => {
    createTableMock.mockResolvedValue({ data: null, error: "Server error" });
    listTablesMock.mockResolvedValue({ data: [], error: null });

    const Lobby = (await import("../src/pages/BlackjackLobby")).default;

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/lobby"]}>
        <Routes>
          <Route path="/lobby" element={<Lobby />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(listTablesMock).toHaveBeenCalled());

    const openBtn = await screen.findByRole("button", { name: /open table/i });
    await user.click(openBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    // joinTable must NOT have been called
    expect(joinTableMock).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-2c: tableName util returns a friendly name
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-2c: tableName util — friendly name generator", () => {
  it("returns a non-empty string that does NOT match /^Table \\d+$/", async () => {
    const mod = await import("../src/utils/tableName");
    // The implementer must export generateTableName (named) or a default function.
    const generateName: () => string =
      (mod.generateTableName as (() => string) | undefined) ??
      (mod.default as (() => string) | undefined) ??
      (() => {
        throw new Error(
          "AC P0-2c: tableName module exports neither generateTableName nor a default function",
        );
      });

    const name = generateName();

    expect(typeof name).toBe("string");
    expect(name.length).toBeGreaterThan(0);
    // This FAILS against the stub (which returns "Table NNNN").
    // It will pass once the implementer replaces the stub with a real generator.
    expect(name).not.toMatch(/^Table \d+$/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-2d: defensive client filter — finished row absent from DOM
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-2d: defensive filter — finished table name absent from DOM", () => {
  it("does not render a finished table even if API returns one", async () => {
    listTablesMock.mockResolvedValue({
      data: [
        {
          id: "active-id",
          name: "Live Table",
          min_bet: 500,
          max_bet: 50000,
          max_seats: 3,
          status: "waiting",
          seats_taken: 0,
        },
        {
          id: "stale-id",
          name: "Ghost Table",
          min_bet: 500,
          max_bet: 50000,
          max_seats: 3,
          status: "finished",
          seats_taken: 3,
        },
      ],
      error: null,
    });

    const Lobby = (await import("../src/pages/BlackjackLobby")).default;

    render(
      <MemoryRouter initialEntries={["/lobby"]}>
        <Routes>
          <Route path="/lobby" element={<Lobby />} />
        </Routes>
      </MemoryRouter>,
    );

    // Wait for table list to render
    await waitFor(() => {
      expect(screen.getByText("Live Table")).toBeInTheDocument();
    });

    // The finished table's name must NOT appear
    expect(screen.queryByText("Ghost Table")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-3a: deterministic wobble — animation-delay identical across renders
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-3a: deterministic wobble — animation-delay is index-derived, not random", () => {
  it("renders the same animation-delay for the first card across two identical renders", async () => {
    const TABLES = [
      { id: "t1", name: "Alpha Table", min_bet: 500, max_bet: 50000, max_seats: 3, status: "waiting", seats_taken: 0 },
      { id: "t2", name: "Beta Table",  min_bet: 500, max_bet: 50000, max_seats: 3, status: "waiting", seats_taken: 1 },
    ];

    listTablesMock.mockResolvedValue({ data: TABLES, error: null });

    const Lobby = (await import("../src/pages/BlackjackLobby")).default;

    // First render
    const { unmount, container: c1 } = render(
      <MemoryRouter>
        <Lobby />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Alpha Table")).toBeInTheDocument();
    });

    // Grab animation-delay of first card element
    const firstCard1 = c1.querySelector("[style*='animation-delay']");
    const delay1 = (firstCard1 as HTMLElement | null)?.style?.animationDelay ?? null;

    unmount();

    // Second render (new React tree)
    const { container: c2 } = render(
      <MemoryRouter>
        <Lobby />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Alpha Table")).toBeInTheDocument();
    });

    const firstCard2 = c2.querySelector("[style*='animation-delay']");
    const delay2 = (firstCard2 as HTMLElement | null)?.style?.animationDelay ?? null;

    expect(delay1).not.toBeNull();
    expect(delay2).not.toBeNull();
    expect(delay1).toBe(delay2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-4a: ink-shadow class on poker + holdem action buttons
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-4a: ink-shadow on PokerActionBar buttons", () => {
  it("fold button has ink-shadow class", async () => {
    const { default: PokerActionBar } = await import("../src/components/PokerActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 5, big_blind: 10,
      ante: 0, board: [], pot_total: 30, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 10, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 10, status: "active", seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, hole_cards: [], starting_stack: 1500, final_stack: 1490,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    render(<PokerActionBar tournamentId="t1" hand={hand} yourSeat={seat} />);

    const foldBtn = screen.getByTestId("poker-action-fold");
    expect(foldBtn.className).toContain("ink-shadow");
  });

  it("all-in button has ink-shadow class", async () => {
    const { default: PokerActionBar } = await import("../src/components/PokerActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 5, big_blind: 10,
      ante: 0, board: [], pot_total: 30, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 10, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 10, status: "active", seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, hole_cards: [], starting_stack: 1500, final_stack: 1490,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    render(<PokerActionBar tournamentId="t1" hand={hand} yourSeat={seat} />);

    const allInBtn = screen.getByTestId("poker-action-all_in");
    expect(allInBtn.className).toContain("ink-shadow");
  });
});

describe("P0-4a: ink-shadow on HoldemActionBar buttons", () => {
  it("fold button has ink-shadow class", async () => {
    const { default: HoldemActionBar } = await import("../src/components/HoldemActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 50, big_blind: 100,
      board: [], pot_total: 150, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 0, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 100, status: "active", result: null, seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, table_seat_number: 0, user_id: "u1", username: "alice",
      hole_cards: [], starting_stack: 10000, final_stack: 10000,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    render(<HoldemActionBar tableId="t1" hand={hand} yourSeat={seat} />);

    const foldBtn = screen.getByTestId("holdem-action-fold");
    expect(foldBtn.className).toContain("ink-shadow");
  });

  it("check button has ink-shadow class (when nothing to call)", async () => {
    const { default: HoldemActionBar } = await import("../src/components/HoldemActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 50, big_blind: 100,
      board: [], pot_total: 150, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 0, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 100, status: "active", result: null, seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, table_seat_number: 0, user_id: "u1", username: "alice",
      hole_cards: [], starting_stack: 10000, final_stack: 10000,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    render(<HoldemActionBar tableId="t1" hand={hand} yourSeat={seat} />);

    const checkBtn = screen.getByTestId("holdem-action-check");
    expect(checkBtn.className).toContain("ink-shadow");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-4b: busy state — aria-busy="true" and label "…" while submitting
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-4b: PokerActionBar — busy state on fold while submitting", () => {
  it("shows aria-busy=true and '…' label while actPoker is pending", async () => {
    // Override actPoker mock to return a never-resolving promise so the
    // component stays in the submitting state long enough to assert.
    const { actPoker } = await import("../src/api/client");
    const actPokerMock = actPoker as ReturnType<typeof vi.fn>;
    actPokerMock.mockImplementation(
      () => new Promise<{ data: unknown; error: null }>(() => {/* never resolves */}),
    );

    const { default: PokerActionBar } = await import("../src/components/PokerActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 5, big_blind: 10,
      ante: 0, board: [], pot_total: 30, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 10, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 10, status: "active", seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, hole_cards: [], starting_stack: 1500, final_stack: 1490,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    const user = userEvent.setup();
    render(<PokerActionBar tournamentId="t1" hand={hand} yourSeat={seat} />);

    const foldBtn = screen.getByTestId("poker-action-fold");
    await user.click(foldBtn);

    // While submitting, the fold button should show "…" and aria-busy="true"
    await waitFor(() => {
      expect(foldBtn).toHaveAttribute("aria-busy", "true");
      expect(foldBtn.textContent).toContain("…");
    });
  });
});

describe("P0-4b: HoldemActionBar — busy state on fold while submitting", () => {
  it("shows aria-busy=true and '…' label while actHoldem is pending", async () => {
    const { actHoldem } = await import("../src/api/client");
    const actHoldemMock = actHoldem as ReturnType<typeof vi.fn>;
    actHoldemMock.mockImplementation(
      () => new Promise<{ data: unknown; error: null }>(() => {/* never resolves */}),
    );

    const { default: HoldemActionBar } = await import("../src/components/HoldemActionBar");

    const hand = {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 50, big_blind: 100,
      board: [], pot_total: 150, side_pots: [], street: "preflop" as const,
      current_bet_to_match: 0, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 100, status: "active", result: null, seats: [], actions: [],
    };
    const seat = {
      seat_number: 0, table_seat_number: 0, user_id: "u1", username: "alice",
      hole_cards: [], starting_stack: 10000, final_stack: 10000,
      current_bet: 0, is_folded: false, is_all_in: false,
    };

    const user = userEvent.setup();
    render(<HoldemActionBar tableId="t1" hand={hand} yourSeat={seat} />);

    const foldBtn = screen.getByTestId("holdem-action-fold");
    await user.click(foldBtn);

    await waitFor(() => {
      expect(foldBtn).toHaveAttribute("aria-busy", "true");
      expect(foldBtn.textContent).toContain("…");
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-5a: "Choose a Game" heading in Lobby — before game cards and table list
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-5a: Choose a Game heading precedes the four game cards in the picker", () => {
  it("renders a 'Choose a Game' heading followed by Blackjack/Hold'em/Poker/Pai Gow cards", async () => {
    const Lobby = (await import("../src/pages/Lobby")).default;

    render(
      <MemoryRouter>
        <Lobby />
      </MemoryRouter>,
    );

    // Heading present
    const heading = await screen.findByText(/choose a game/i);
    expect(heading).toBeInTheDocument();

    // All four game cards present (one consistent picker)
    expect(screen.getByTestId("blackjack-lobby-card")).toBeInTheDocument();
    expect(screen.getByTestId("holdem-lobby-card")).toBeInTheDocument();
    expect(screen.getByTestId("poker-lobby-card")).toBeInTheDocument();
    expect(screen.getByTestId("paigow-lobby-card")).toBeInTheDocument();

    // Heading precedes the first game card in DOM order
    const html = document.body.innerHTML;
    expect(html.indexOf("Choose a Game")).toBeGreaterThanOrEqual(0);
    expect(html.indexOf("Choose a Game")).toBeLessThan(html.indexOf("blackjack-lobby-card"));
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-6a/b: outcome banner classes — banner-pulse always; sparkle on wins only
//
// Seeds the gameStore directly (no polling needed), then renders Table and
// asserts on the DOM. These fail until Table.tsx applies banner-pulse/sparkle.
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-6a: Table.tsx — win outcome banner has banner-pulse + sparkle", () => {
  it("the outcome banner rendered by Table.tsx in a win state has banner-pulse and sparkle classes", async () => {
    // Seed the store with a completed winning hand BEFORE rendering.
    const { useGameStore } = await import("../src/store/gameStore");

    const winHand = {
      id: "hand-win-001",
      session_id: "sess-001",
      user_id: "dev-user",
      cards: [
        { suit: "hearts" as const, value: "A" as const },
        { suit: "spades" as const, value: "K" as const },
      ],
      bet: 1000,
      status: "blackjack",
      outcome: "blackjack",
      payout: 2500,
    };

    const tableStateWin = {
      id: "t1",
      name: "Win Table",
      status: "playing",
      seats: [{ id: "s1", user_id: "dev-user", seat_number: 1, username: "Dev", chip_balance: 100000 }],
      session: {
        id: "sess-001",
        table_id: "t1",
        game_type: "blackjack",
        dealer_cards: [
          { suit: "clubs" as const, value: "6" as const },
          { suit: "diamonds" as const, value: "10" as const },
        ],
        status: "finished",
        created_at: new Date().toISOString(),
      },
      hands: [winHand],
    };

    // Set store state synchronously before render
    act(() => {
      useGameStore.setState({
        tableState: tableStateWin,
        myHand: winHand,
        lastFinishedHandId: "hand-win-001",
      });
    });

    const Table = (await import("../src/pages/Table")).default;

    render(
      <MemoryRouter initialEntries={["/table/t1"]}>
        <Routes>
          <Route path="/table/:id" element={<Table />} />
        </Routes>
      </MemoryRouter>,
    );

    // Wait for the banner to appear — it's gated on isHandFinished + lastFinishedHandId
    await waitFor(() => {
      // Table.tsx renders the outcome text from chipyMood.title
      const banner = document.querySelector(".banner-pulse");
      expect(banner).toBeInTheDocument();
    }, { timeout: 3000 });

    const banner = document.querySelector(".banner-pulse");
    expect(banner).not.toBeNull();
    expect((banner as HTMLElement).className).toContain("sparkle");
  });
});

describe("P0-6b: Table.tsx — loss/bust banner has banner-pulse but NOT sparkle", () => {
  it("the outcome banner rendered by Table.tsx in a bust state has banner-pulse but not sparkle", async () => {
    const { useGameStore } = await import("../src/store/gameStore");

    const bustHand = {
      id: "hand-bust-001",
      session_id: "sess-002",
      user_id: "dev-user",
      cards: [
        { suit: "hearts" as const, value: "K" as const },
        { suit: "spades" as const, value: "Q" as const },
        { suit: "clubs" as const, value: "5" as const },
      ],
      bet: 1000,
      status: "bust",
      outcome: null,
      payout: 0,
    };

    const tableStateBust = {
      id: "t1",
      name: "Bust Table",
      status: "playing",
      seats: [{ id: "s1", user_id: "dev-user", seat_number: 1, username: "Dev", chip_balance: 99000 }],
      session: {
        id: "sess-002",
        table_id: "t1",
        game_type: "blackjack",
        dealer_cards: [{ suit: "clubs" as const, value: "6" as const }],
        status: "dealer_turn",
        created_at: new Date().toISOString(),
      },
      hands: [bustHand],
    };

    act(() => {
      useGameStore.setState({
        tableState: tableStateBust,
        myHand: bustHand,
        lastFinishedHandId: "hand-bust-001",
      });
    });

    const Table = (await import("../src/pages/Table")).default;

    render(
      <MemoryRouter initialEntries={["/table/t1"]}>
        <Routes>
          <Route path="/table/:id" element={<Table />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      const banner = document.querySelector(".banner-pulse");
      expect(banner).toBeInTheDocument();
    }, { timeout: 3000 });

    const banner = document.querySelector(".banner-pulse");
    expect(banner).not.toBeNull();
    expect((banner as HTMLElement).className).not.toContain("sparkle");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-7a: Chipy imageRendering === "crisp-edges" + spritePosition formula unchanged
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-7a: Chipy imageRendering is crisp-edges", () => {
  it("renders with imageRendering: crisp-edges in the inline style", async () => {
    const { default: Chipy } = await import("../src/components/Chipy");

    render(<Chipy size={80} expression="idle" />);

    // Chipy renders a motion.div with the sprite style. We look for the role=img element.
    const chipyEl = screen.getByRole("img", { name: /chipy/i });
    expect(chipyEl).toBeInTheDocument();
    expect((chipyEl as HTMLElement).style.imageRendering).toBe("crisp-edges");
  });
});

describe("P0-7a: spritePosition formula is unchanged (col / (COLS-1) * 100)", () => {
  it("spritePosition for col=0 returns 0%", async () => {
    // Import the source to validate the formula output.
    // We do this by rendering Chipy with a known expression and checking
    // the backgroundPosition style value.

    const { default: Chipy } = await import("../src/components/Chipy");

    // expression "surprised" maps to row:2, col:0 → x=0%, y=~66.67%
    render(<Chipy size={80} expression="surprised" />);

    const chipyEl = screen.getByRole("img", { name: /chipy/i });
    const bgPos = (chipyEl as HTMLElement).style.backgroundPosition;

    // col=0 → x = (0/(4-1))*100 = 0%
    expect(bgPos.startsWith("0%")).toBe(true);
  });

  it("spritePosition for col=3 (last col) returns 100%", async () => {
    const { default: Chipy } = await import("../src/components/Chipy");

    // expression "happy" maps to row:0, col:3 → x=100%, y=0%
    render(<Chipy size={80} expression="happy" />);

    const chipyEl = screen.getByRole("img", { name: /chipy/i });
    const bgPos = (chipyEl as HTMLElement).style.backgroundPosition;

    // col=3 → x = (3/(4-1))*100 = 100%
    expect(bgPos.startsWith("100%")).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// P0-7b: Chipy container has circular clip-path
// ─────────────────────────────────────────────────────────────────────────────

describe("P0-7b: Chipy has circular clip-path", () => {
  it("the rendered Chipy element has a clip-path that includes 'circle'", async () => {
    const { default: Chipy } = await import("../src/components/Chipy");

    render(<Chipy size={80} expression="idle" />);

    const chipyEl = screen.getByRole("img", { name: /chipy/i });
    const inlineClipPath = (chipyEl as HTMLElement).style.clipPath;
    const className = (chipyEl as HTMLElement).className;

    // Accept either inline style or a Tailwind class that applies clip-path
    const hasClipPath =
      (inlineClipPath && inlineClipPath.toLowerCase().includes("circle")) ||
      className.includes("[clip-path") ||
      className.includes("clip-path") ||
      className.includes("clip-circle") ||
      // jsdom may compute it differently — also accept a data attribute as fallback
      chipyEl.hasAttribute("data-clip-circle");

    expect(hasClipPath).toBe(true);
  });
});
