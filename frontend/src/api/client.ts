/**
 * api/client.ts — typed fetch wrapper for all BetWise Casino backend endpoints.
 *
 * Rules (CLAUDE.md §8, §15):
 * - Every function returns Promise<ApiResult<T>> — never throws.
 * - 401 responses navigate to /login via a custom event.
 * - The streamAdvice function is separate because SSE cannot fit in ApiResult.
 */
import { supabase } from "../auth/supabase";
import type {
  Action,
  AdviceResult,
  ApiResult,
  HandReplayAction,
  LeaderboardRow,
  SessionReview,
  TableListRow,
  TableOut,
  TableState,
  UserStats,
  WeakSpot,
  Hand,
} from "../types";

// ─── Auth header helper ───────────────────────────────────────────────────────

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

// ─── Base fetch wrapper ───────────────────────────────────────────────────────

const SESSION_EXPIRED_MSG = "Session expired — please sign in again";
const NETWORK_ERROR_MSG = "Network error — please retry";

/** Fires a custom event that AuthGate listens to for redirect-to-login. */
function fireSessionExpired(): void {
  window.dispatchEvent(new CustomEvent("betwise:session-expired"));
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<ApiResult<T>> {
  try {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...(options.headers as Record<string, string> | undefined),
      },
    });

    if (res.status === 401) {
      fireSessionExpired();
      return { data: null, error: SESSION_EXPIRED_MSG };
    }

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body.detail) {
          message = body.detail;
        }
      } catch {
        // ignore JSON parse failure
      }
      return { data: null, error: message };
    }

    const data = (await res.json()) as T;
    return { data, error: null };
  } catch {
    return { data: null, error: NETWORK_ERROR_MSG };
  }
}

// ─── Users ────────────────────────────────────────────────────────────────────

export async function getMe(): Promise<ApiResult<UserStats>> {
  return apiFetch<UserStats>("/api/users/me");
}

export async function createMe(username: string): Promise<ApiResult<UserStats>> {
  return apiFetch<UserStats>("/api/users/me", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export async function resetChips(): Promise<ApiResult<UserStats>> {
  return apiFetch<UserStats>("/api/users/me/reset-chips", { method: "POST" });
}

export async function getUserHands(userId: string): Promise<ApiResult<Hand[]>> {
  return apiFetch<Hand[]>(`/api/users/${userId}/hands`);
}

// ─── Tables ───────────────────────────────────────────────────────────────────

export async function listTables(): Promise<ApiResult<TableListRow[]>> {
  return apiFetch<TableListRow[]>("/api/tables");
}

export async function createTable(payload: {
  name: string;
  min_bet?: number;
  max_bet?: number;
  game_type?: string;
}): Promise<ApiResult<TableOut>> {
  return apiFetch<TableOut>("/api/tables", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function joinTable(tableId: string): Promise<ApiResult<{ message: string }>> {
  return apiFetch<{ message: string }>(`/api/tables/${tableId}/join`, {
    method: "POST",
  });
}

export async function leaveTable(tableId: string): Promise<ApiResult<{ message: string }>> {
  return apiFetch<{ message: string }>(`/api/tables/${tableId}/leave`, {
    method: "POST",
  });
}

export async function getTableState(tableId: string): Promise<ApiResult<TableState>> {
  return apiFetch<TableState>(`/api/tables/${tableId}/state`);
}

// ─── Game ─────────────────────────────────────────────────────────────────────

export async function dealHand(
  tableId: string,
  bet: number,
): Promise<ApiResult<Hand>> {
  return apiFetch<Hand>(`/api/tables/${tableId}/deal`, {
    method: "POST",
    body: JSON.stringify({ bet }),
  });
}

export async function takeAction(
  tableId: string,
  action: Action,
): Promise<ApiResult<Hand>> {
  return apiFetch<Hand>(`/api/tables/${tableId}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export async function getHandActions(
  handId: string,
): Promise<ApiResult<HandReplayAction[]>> {
  return apiFetch<HandReplayAction[]>(`/api/hands/${handId}/actions`);
}

export async function getSessionReview(
  sessionId: string,
): Promise<ApiResult<SessionReview>> {
  return apiFetch<SessionReview>(`/api/sessions/${sessionId}/review`);
}

// ─── Leaderboard ─────────────────────────────────────────────────────────────

export async function getLeaderboard(): Promise<ApiResult<LeaderboardRow[]>> {
  return apiFetch<LeaderboardRow[]>("/api/leaderboard");
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export async function getWeakness(): Promise<ApiResult<WeakSpot[]>> {
  return apiFetch<WeakSpot[]>("/api/analytics/weakness");
}

// ─── Streaming advice (SSE) ───────────────────────────────────────────────────

/**
 * streamAdvice — POSTs a player_guess to /api/advice/:handId and consumes
 * the Server-Sent Events stream.
 *
 * SSE line format from backend (matches conftest _FakeStream):
 *   data: <text chunk>\n\n         — intermediate text chunk
 *   data: {"optimal_action":...}\n\n — final JSON event (AdviceResult shape)
 *
 * The caller provides:
 *   onChunk(text)  — called for each intermediate text fragment
 *   onDone(result) — called once with the final AdviceResult JSON
 *   onError(msg)   — called on network/parse errors
 */
/**
 * streamPreAdvice — POSTs to /api/advice/:handId/pre with no body. Used by
 * ChipyCoach to chime in proactively the moment it's the player's turn.
 *
 * Unlike streamAdvice this does NOT require a player_guess and does NOT
 * update the user's streak. The final SSE event has {optimal_action, phase:"pre"};
 * we don't surface that to the caller — onDone fires regardless.
 */
export async function streamPreAdvice(
  handId: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (message: string) => void,
): Promise<void> {
  try {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`/api/advice/${handId}/pre`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders },
    });

    if (res.status === 401) {
      fireSessionExpired();
      onError(SESSION_EXPIRED_MSG);
      return;
    }
    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body.detail) message = body.detail;
      } catch {
        // ignore
      }
      onError(message);
      return;
    }
    if (!res.body) {
      onError("No response body from advice endpoint");
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        if (!event.trim()) continue;
        const dataLines = event
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice("data: ".length));
        for (const dataPayload of dataLines) {
          if (!dataPayload.trim()) continue;
          try {
            const parsed = JSON.parse(dataPayload) as Record<string, unknown>;
            if ("optimal_action" in parsed) {
              // Final event for /pre — we don't need the payload, just close.
              onDone();
              return;
            }
            if (typeof parsed.text === "string") {
              onChunk(parsed.text);
            } else {
              onChunk(dataPayload);
            }
          } catch {
            onChunk(dataPayload);
          }
        }
      }
    }
    onDone();
  } catch {
    onError(NETWORK_ERROR_MSG);
  }
}

export async function streamAdvice(
  handId: string,
  guess: Action,
  onChunk: (text: string) => void,
  onDone: (result: AdviceResult) => void,
  onError: (message: string) => void,
): Promise<void> {
  try {
    const authHeaders = await getAuthHeaders();
    const res = await fetch(`/api/advice/${handId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
      },
      body: JSON.stringify({ player_guess: guess }),
    });

    if (res.status === 401) {
      fireSessionExpired();
      onError(SESSION_EXPIRED_MSG);
      return;
    }

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body.detail) message = body.detail;
      } catch {
        // ignore
      }
      onError(message);
      return;
    }

    if (!res.body) {
      onError("No response body from advice endpoint");
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Split on double-newline SSE boundaries
      const events = buffer.split("\n\n");
      // Last element may be incomplete — keep it in buffer
      buffer = events.pop() ?? "";

      for (const event of events) {
        if (!event.trim()) continue;

        // Extract all `data:` lines from the event block
        const dataLines = event
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice("data: ".length));

        for (const dataPayload of dataLines) {
          if (!dataPayload.trim()) continue;

          // Try to parse as JSON (final event)
          try {
            const parsed = JSON.parse(dataPayload) as Record<string, unknown>;
            // If it has optimal_action, it's the final AdviceResult
            if ("optimal_action" in parsed) {
              onDone(parsed as unknown as AdviceResult);
            } else if (typeof parsed.text === "string") {
              // Text chunk wrapped in JSON, e.g. {"text":"...","error":"..."}
              onChunk(parsed.text);
            } else {
              // Unrecognized JSON shape — fall back to raw payload
              onChunk(dataPayload);
            }
          } catch {
            // Not JSON — plain text chunk
            onChunk(dataPayload);
          }
        }
      }
    }
  } catch {
    onError(NETWORK_ERROR_MSG);
  }
}
