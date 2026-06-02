/**
 * HoldemTablePage.test.tsx — guards the leave-on-unmount effect against React
 * StrictMode's dev-only mount→cleanup→mount double-invoke. Without the guard the
 * synthetic unmount cashes out a just-seated player (reviewer finding #6); with
 * it, leave fires only on a genuine unmount.
 *
 * We mock the network seam (api/client) and the poll hook so the test is
 * deterministic with fake timers — asserting "leave was NOT called" needs a
 * timer model, not a real-clock race.
 */
import { render, act } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../src/api/client";
import HoldemTablePage from "../src/pages/HoldemTablePage";

vi.mock("../src/hooks/useHoldemPoll", () => ({ useHoldemPoll: () => {} }));
vi.mock("../src/auth/supabase", () => ({ useSession: () => ({ session: null }) }));
vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    leaveHoldemTable: vi.fn(async () => ({ data: { status: "left" }, error: null })),
  };
});

function renderTablePage() {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={["/holdem/table/tbl-1"]}>
        <Routes>
          <Route path="/holdem/table/:id" element={<HoldemTablePage />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  );
}

describe("HoldemTablePage leave-on-unmount StrictMode guard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(client.leaveHoldemTable).mockClear();
  });
  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("does NOT leave the table on StrictMode's synthetic mount→cleanup→mount", () => {
    renderTablePage();
    act(() => {
      vi.runAllTimers();
    });
    expect(client.leaveHoldemTable).not.toHaveBeenCalled();
  });

  it("leaves the table exactly once on a genuine unmount", () => {
    const { unmount } = renderTablePage();
    act(() => {
      vi.runAllTimers();
    });
    unmount();
    act(() => {
      vi.runAllTimers();
    });
    expect(client.leaveHoldemTable).toHaveBeenCalledTimes(1);
    expect(client.leaveHoldemTable).toHaveBeenCalledWith("tbl-1");
  });
});
