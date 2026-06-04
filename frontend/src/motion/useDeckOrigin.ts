/**
 * useDeckOrigin — compute the offset a card should fly FROM (the deck).
 *
 * Returns getFlyFrom(targetEl): the {x,y} delta, in the target card's OWN
 * coordinate space, from its laid-out position back to the deck center. Pass that
 * as the motion start so framer animates deck -> slot. Read at mount via
 * useLayoutEffect (before paint) so there's no flash and it's reflow-safe.
 */
import { useDeckContext } from "./DeckProvider";

export interface FlyFrom {
  x: number;
  y: number;
}

export function useDeckOrigin(): (targetEl: HTMLElement | null) => FlyFrom {
  const ctx = useDeckContext();
  return (targetEl) => {
    const deck = ctx?.deckRef.current;
    if (!deck || !targetEl) return { x: 0, y: 0 };
    const d = deck.getBoundingClientRect();
    const t = targetEl.getBoundingClientRect();
    return {
      x: d.left + d.width / 2 - (t.left + t.width / 2),
      y: d.top + d.height / 2 - (t.top + t.height / 2),
    };
  };
}
