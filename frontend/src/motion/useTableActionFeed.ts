/**
 * useTableActionFeed — turn polled hand state into discrete action events.
 *
 * Hold'em and poker both carry a per-hand action log with a monotonic
 * `action_index`. This hook keeps a cursor (per hand id) of the highest index
 * it has emitted and, on each poll, returns ONLY the new actions in order.
 * Idempotent across the 3s re-polls and React re-renders — re-seeing the same
 * index never re-fires. On a fresh hand it seeds the cursor to the current max
 * so we don't replay a whole hand's worth of actions on mount.
 *
 * The diff runs in an effect (not render) so it's a clean side effect; the store
 * stays a plain overwrite.
 */
import { useEffect, useRef, useState } from "react";

export interface TableActionEvent {
  seatNumber: number;
  action: string;
  amount: number;
  actionIndex: number;
}

interface ActionLike {
  seat_number: number;
  action: string;
  amount: number;
  action_index: number;
}
interface HandLike {
  id: string;
  actions?: ActionLike[];
}

function maxIndex(actions: ActionLike[] | undefined): number {
  return (actions ?? []).reduce((m, a) => Math.max(m, a.action_index), -1);
}

export function useTableActionFeed(hand: HandLike | null | undefined): TableActionEvent[] {
  const cursor = useRef<{ handId: string | null; maxIndex: number }>({ handId: null, maxIndex: -1 });
  const [events, setEvents] = useState<TableActionEvent[]>([]);

  useEffect(() => {
    if (!hand) return;
    // New hand: seed the cursor to the latest action so we don't replay history.
    if (cursor.current.handId !== hand.id) {
      cursor.current = { handId: hand.id, maxIndex: maxIndex(hand.actions) };
      setEvents([]);
      return;
    }
    const fresh = (hand.actions ?? []).filter((a) => a.action_index > cursor.current.maxIndex);
    if (fresh.length === 0) return;
    cursor.current.maxIndex = maxIndex(fresh);
    setEvents(
      fresh
        .slice()
        .sort((a, b) => a.action_index - b.action_index)
        .map((a) => ({
          seatNumber: a.seat_number,
          action: a.action,
          amount: a.amount,
          actionIndex: a.action_index,
        })),
    );
  }, [hand]);

  return events;
}
