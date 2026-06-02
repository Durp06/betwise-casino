/**
 * TableAutoLeave.test.tsx — regression test for StrictMode double-mount bug.
 *
 * ASSERTION 1 (regression): StrictMode's throwaway unmount must NOT call
 *   leaveTable. Before the fix the cleanup fires leaveTable on the
 *   first-mount/teardown cycle → user lands unseated.
 *
 * ASSERTION 2 (intent preserved): pagehide event triggers leaveTable exactly once,
 *   proving the tab-close path still works after the fix.
 */

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeAll, afterAll, afterEach, describe, it, expect, vi, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

// ── vi.hoisted: create mocks before the vi.mock factory is hoisted ────────────
const { leaveTableMock, getTableStateMock } = vi.hoisted(() => {
  const tableStateData = {
    id: "t1",
    name: "Test Table",
    status: "open",
    seats: [{ id: "s1", user_id: "dev-user", seat_number: 1, username: "Dev", chip_balance: 100000 }],
    session: null,
    hands: [],
  };
  return {
    leaveTableMock: vi.fn().mockResolvedValue({ data: { message: "left" }, error: null }),
    getTableStateMock: vi.fn().mockResolvedValue({ data: tableStateData, error: null }),
  };
});

// ── Mock the API client BEFORE importing Table ────────────────────────────────
vi.mock("../src/api/client", () => ({
  leaveTable: leaveTableMock,
  getTableState: getTableStateMock,
  streamPreAdvice: vi.fn(
    async (
      _handId: string,
      _onChunk: (t: string) => void,
      onDone: () => void,
      _onError: (m: string) => void,
    ) => {
      onDone();
    },
  ),
  streamAdvice: vi.fn(),
  dealHand: vi.fn().mockResolvedValue({ data: null, error: null }),
  takeAction: vi.fn().mockResolvedValue({ data: null, error: null }),
  getHandActions: vi.fn().mockResolvedValue({ data: [], error: null }),
  getSessionReview: vi.fn().mockResolvedValue({ data: null, error: null }),
  gradePractice: vi.fn().mockResolvedValue({ data: null, error: null }),
  // ChatPanel (added to Table.tsx by the poker merge) polls these — stub so the
  // panel mounts without an unhandled rejection during this Table render test.
  getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
  postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
}));

// ── Mock supabase / useSession ────────────────────────────────────────────────
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

// ── Production component under test ──────────────────────────────────────────
// Import AFTER mocks are established.
import Table from "../src/pages/Table";

// ── MSW server (safety net for unhandled requests) ────────────────────────────
const server = setupServer(
  http.get("/api/tables/:id/state", () =>
    HttpResponse.json({
      id: "t1",
      name: "Test Table",
      status: "open",
      seats: [{ id: "s1", user_id: "dev-user", seat_number: 1, username: "Dev", chip_balance: 100000 }],
      session: null,
      hands: [],
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

// Restore mock implementations after clearAllMocks resets them
beforeEach(() => {
  leaveTableMock.mockResolvedValue({ data: { message: "left" }, error: null });
  getTableStateMock.mockResolvedValue({
    data: {
      id: "t1",
      name: "Test Table",
      status: "open",
      seats: [{ id: "s1", user_id: "dev-user", seat_number: 1, username: "Dev", chip_balance: 100000 }],
      session: null,
      hands: [],
    },
    error: null,
  });
});

// ── Helper: render Table wrapped in StrictMode + MemoryRouter ─────────────────
function renderTable() {
  return render(
    <React.StrictMode>
      <MemoryRouter initialEntries={["/table/t1"]}>
        <Routes>
          <Route path="/table/:id" element={<Table />} />
        </Routes>
      </MemoryRouter>
    </React.StrictMode>,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 1: StrictMode double-mount must NOT call leaveTable
// ─────────────────────────────────────────────────────────────────────────────
describe("Table — StrictMode regression", () => {
  it("ASSERTION 1: leaveTable is NOT called during StrictMode initial mount/unmount cycle", async () => {
    renderTable();

    // Wait for the loading spinner to disappear (component settled)
    await waitFor(() => {
      // Either the loading state resolves, or we just wait a bit
      expect(screen.queryByText(/Pulling up a chair/i)).not.toBeInTheDocument();
    }, { timeout: 1000 }).catch(() => {
      // Component may never have shown loading state — that's fine
    });

    // Give effects a full tick to run
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });

    // THE KEY ASSERTION: StrictMode double-mount cleanup must NOT have fired leaveTable.
    // Before the fix this fails because the useEffect cleanup calls leaveTable.
    expect(leaveTableMock).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 2: intent preserved — pagehide triggers leaveTable exactly once
// ─────────────────────────────────────────────────────────────────────────────
describe("Table — pagehide still leaves", () => {
  it("ASSERTION 2: dispatching pagehide fires leaveTable exactly once", async () => {
    renderTable();

    // Wait for component to mount and effects to run
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });

    // Reset call count so we only measure what pagehide does
    leaveTableMock.mockClear();

    // Simulate tab close / browser unload
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });

    expect(leaveTableMock).toHaveBeenCalledTimes(1);
    expect(leaveTableMock).toHaveBeenCalledWith("t1");
  });
});
