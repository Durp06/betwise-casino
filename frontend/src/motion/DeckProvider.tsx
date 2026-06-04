/**
 * DeckProvider — the shared spatial anchors for table motion.
 *
 * Holds live refs to the felt's "deck" node (where cards fly FROM), the pot node
 * (where chips fly TO), and each seat's node (chip-fly source). Components register
 * their DOM node; animation primitives read getBoundingClientRect() at fire time so
 * everything is reflow-safe under the responsive seat grid.
 */
import { createContext, useContext, useMemo, useRef, type ReactNode, type MutableRefObject } from "react";

export interface DeckContextValue {
  deckRef: MutableRefObject<HTMLElement | null>;
  potRef: MutableRefObject<HTMLElement | null>;
  registerSeat: (seatNumber: number, el: HTMLElement | null) => void;
  getSeatRect: (seatNumber: number) => DOMRect | null;
}

const DeckContext = createContext<DeckContextValue | null>(null);

export function DeckProvider({ children }: { children: ReactNode }) {
  const deckRef = useRef<HTMLElement | null>(null);
  const potRef = useRef<HTMLElement | null>(null);
  const seats = useRef<Map<number, HTMLElement>>(new Map());

  const value = useMemo<DeckContextValue>(
    () => ({
      deckRef,
      potRef,
      registerSeat: (n, el) => {
        if (el) seats.current.set(n, el);
        else seats.current.delete(n);
      },
      getSeatRect: (n) => seats.current.get(n)?.getBoundingClientRect() ?? null,
    }),
    [],
  );

  return <DeckContext.Provider value={value}>{children}</DeckContext.Provider>;
}

export function useDeckContext(): DeckContextValue | null {
  return useContext(DeckContext);
}
