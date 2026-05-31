/**
 * ChatPanel.test.tsx — in-game chat panel: list render, loading + error
 * branches, the typed Send path, and the all-important stored-XSS render test.
 *
 * HTTP is mocked with MSW (setupServer) so the real api/client.ts code path is
 * exercised end-to-end. The component does no routing, so no MemoryRouter.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect } from "vitest";

import ChatPanel from "../src/components/ChatPanel";
import type { ChatMessage } from "../src/types";

const TABLE_ID = "11111111-1111-1111-1111-111111111111";
const GET_URL = `/api/chat/holdem/${TABLE_ID}/messages`;
const POST_URL = GET_URL;

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: crypto.randomUUID(),
    table_kind: "holdem",
    table_id: TABLE_ID,
    user_id: "uuuuuuuu-uuuu-uuuu-uuuu-uuuuuuuuuuuu",
    username: "alice",
    body: "hello table",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ChatPanel", () => {
  it("renders a returned list of messages (username + body visible)", async () => {
    server.use(
      http.get(GET_URL, () =>
        HttpResponse.json([
          makeMessage({ username: "alice", body: "nice hand" }),
          makeMessage({ username: "bob", body: "raise it up" }),
        ]),
      ),
    );

    render(<ChatPanel tableKind="holdem" tableId={TABLE_ID} />);

    await waitFor(() => {
      expect(screen.getByText("nice hand")).toBeInTheDocument();
    });
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("raise it up")).toBeInTheDocument();
  });

  it("renders the loading branch before the fetch resolves", () => {
    // Never-resolving handler keeps the panel in its loading state.
    server.use(http.get(GET_URL, () => new Promise<never>(() => {})));

    render(<ChatPanel tableKind="holdem" tableId={TABLE_ID} />);
    const loading = document.querySelector("[role='status'][aria-busy='true']");
    expect(loading).toBeTruthy();
  });

  it("renders the error branch when the fetch fails (500)", async () => {
    server.use(
      http.get(GET_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render(<ChatPanel tableKind="holdem" tableId={TABLE_ID} />);

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
    });
  });

  // ─── The important one: stored XSS must NOT become live DOM ─────────────────
  it("renders a malicious body as inert text, never as injected HTML", async () => {
    const scriptPayload = "<script>alert('xss')</script>";
    const imgPayload = "<img src=x onerror=alert(1)>";
    server.use(
      http.get(GET_URL, () =>
        HttpResponse.json([
          makeMessage({ username: "mallory", body: scriptPayload }),
          makeMessage({ username: "mallory", body: imgPayload }),
        ]),
      ),
    );

    const { container } = render(<ChatPanel tableKind="holdem" tableId={TABLE_ID} />);

    await waitFor(() => {
      expect(container.textContent).toContain(scriptPayload);
    });
    // The literal payload text is present...
    expect(container.textContent).toContain(imgPayload);
    // ...but NOT as live DOM nodes — React escaped it as a text child.
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("typing + Send posts the typed body to the chat endpoint", async () => {
    const user = userEvent.setup();
    const posted: Array<{ body: string }> = [];

    server.use(
      http.get(GET_URL, () => HttpResponse.json([])),
      http.post(POST_URL, async ({ request }) => {
        const json = (await request.json()) as { body: string };
        posted.push(json);
        return HttpResponse.json(makeMessage({ body: json.body }), { status: 201 });
      }),
    );

    render(<ChatPanel tableKind="holdem" tableId={TABLE_ID} />);

    // Wait past the initial loading state.
    await waitFor(() => {
      expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
    });

    const input = screen.getByTestId("chat-input");
    await user.type(input, "good game");
    await user.click(screen.getByTestId("chat-send"));

    await waitFor(() => expect(posted.length).toBeGreaterThan(0));
    expect(posted[0].body).toBe("good game");
  });
});
