/**
 * ChatPanel.tsx — in-game player chat for both multiplayer games.
 *
 * Polls GET /api/chat/{tableKind}/{tableId}/messages every 3s (paused while the
 * tab is hidden, mirroring useHoldemPoll) and posts via postChatMessage. Shows
 * explicit loading + error states for BOTH the fetch and the send (CLAUDE.md).
 *
 * SECURITY — stored-XSS defense (client half):
 * The message body is rendered EXCLUSIVELY as a React text child (`{m.body}`).
 * React auto-escapes text children, so a body like `<script>alert(1)</script>`
 * or `<img src=x onerror=...>` renders as inert literal text and cannot execute.
 * This component never uses dangerouslySetInnerHTML and never places the body
 * into an href/src/style/onClick attribute, eval, or a constructed DOM node.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getChatMessages, postChatMessage } from "../api/client";
import type { ChatMessage, ChatTableKind } from "../types";
import { t } from "../i18n";

const POLL_INTERVAL_MS = 3000;
const MAX_BODY_LEN = 500;

interface ChatPanelProps {
  tableKind: ChatTableKind;
  tableId: string;
}

export default function ChatPanel({ tableKind, tableId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);

  const refetch = useCallback(async (): Promise<void> => {
    const result = await getChatMessages(tableKind, tableId);
    if (result.error !== null) {
      setFetchError(result.error);
    } else {
      setMessages(result.data);
      setFetchError(null);
    }
    setLoading(false);
  }, [tableKind, tableId]);

  // 3s poll with a document.visibilityState pause (mirrors useHoldemPoll).
  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      if (document.visibilityState === "hidden") return;
      const result = await getChatMessages(tableKind, tableId);
      if (cancelled) return;
      if (result.error !== null) {
        setFetchError(result.error);
      } else {
        setMessages(result.data);
        setFetchError(null);
      }
      setLoading(false);
    }

    void poll();
    const intervalId = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);

    function handleVisibilityChange(): void {
      if (document.visibilityState === "visible") void poll();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [tableKind, tableId]);

  // Keep the scrollback pinned to the newest message.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function handleSend(): Promise<void> {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setSendError(null);
    const result = await postChatMessage(tableKind, tableId, body);
    setSending(false);
    if (result.error) {
      setSendError(result.error);
      return;
    }
    setDraft("");
    await refetch();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleSend();
    }
  }

  const canSend = draft.trim().length > 0 && !sending;

  return (
    <section
      aria-label={t("Table chat")}
      data-testid="chat-panel"
      className="flex flex-col w-full max-w-sm h-80 ink-outline rounded-xl bg-ink/70 overflow-hidden"
    >
      <header className="px-3 py-2 border-b-2 border-ink bg-ink/80">
        <h2 className="font-ui text-cream text-xs uppercase tracking-widest">
          {t("Table Chat")}
        </h2>
      </header>

      <div
        ref={listRef}
        data-testid="chat-messages"
        className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-1.5"
      >
        {loading && (
          <span
            role="status"
            aria-busy="true"
            className="font-flavor text-cream/60 text-xs italic animate-pulse"
          >
            {t("Loading chat…")}
          </span>
        )}

        {!loading && fetchError && (
          <p role="alert" className="font-flavor text-action-hit text-xs italic">
            {fetchError}
          </p>
        )}

        {!loading && !fetchError && messages.length === 0 && (
          <p className="font-flavor text-cream/50 text-xs italic">
            {t("No messages yet. Say hello!")}
          </p>
        )}

        {messages.map((m) => (
          <div key={m.id} className="text-sm leading-snug break-words">
            <span className="font-ui text-gold-bright mr-1">{m.username}</span>
            {/* Body rendered as a TEXT node — React escapes it, so markup is inert. */}
            <span className="font-flavor text-cream/90">{m.body}</span>
          </div>
        ))}
      </div>

      {sendError && (
        <p role="alert" className="font-flavor text-action-hit text-xs italic px-3 py-1">
          {sendError}
        </p>
      )}

      <div className="flex items-center gap-2 p-2 border-t-2 border-ink">
        <input
          type="text"
          value={draft}
          maxLength={MAX_BODY_LEN}
          disabled={sending}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("Type a message…")}
          aria-label={t("Chat message")}
          data-testid="chat-input"
          className="flex-1 min-w-0 rounded-md px-2 py-1.5 text-sm font-flavor bg-cream/95 text-ink
            placeholder:text-ink/40 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-gold-bright"
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={!canSend}
          data-testid="chat-send"
          className="ink-outline font-ui text-xs uppercase tracking-wider px-3 py-1.5 rounded-md
            text-ink bg-gold-bright disabled:opacity-40 min-h-[36px]"
        >
          {sending ? t("Sending…") : t("Send")}
        </button>
      </div>
    </section>
  );
}
