# BetWise Motion System — deck-dealing, flips, multiplayer presence

Status: in progress (branch `feat/animations`)
Date: 2026-06-03
Goal (user, verbatim): "add animations to poker and the whole website. i want some
indicator of other people betting, and playing cards, and folding. i dont want
things to just appear and disappear, cards should be dealt from somewhere."

## North star
Nothing pops. Every element that enters/exits/changes value does so with motion;
every card flies from a single shared **deck origin** and flips face-up on reveal.
One motion vocabulary (spring + AnimatePresence + measured FLIP) across all five
surfaces (blackjack, solo poker, multiplayer Hold'em, Pai Gow, site-wide UI).
Multiplayer presence is legible: when another player bets/folds/is on the clock you
SEE it (chips fly to pot, cards muck, seat pulses) — derived purely from 3s
polled-state diffs + the existing action logs, **no new realtime infra, no backend
changes required**. Everything respects `prefers-reduced-motion` (degrades to
eased opacity, never a jarring pop). Built on the installed framer-motion v12 + the
existing CSS keyframes — no new dependency.

## Shared motion system (build once, consume everywhere)
1. **MotionConfig + tokens** — `motion/tokens.ts` (DEAL_SPRING, FLIP_TRANSITION,
   POP_IN, CHIP_FLY, BADGE_POP, STAGGER_STEP=0.11), `motion/useMotionPrefs.ts`
   (wraps `useReducedMotion`); wrap App in `<MotionConfig reducedMotion="user">`.
2. **DeckProvider + useDeckOrigin + DeckStack** — context holding deck/pot/per-seat
   rects (ResizeObserver). A visible `<DeckStack>` sits at a per-game felt spot;
   `useDeckOrigin(ref)` returns the measured `{x,y,rotate,scale}` delta a card flies
   from (read in `useLayoutEffect` on mount, reflow-safe).
3. **DealtCard** — the single animated card: flies from deck origin, lands with the
   rubber-hose bounce, 3D-flips on reveal (drives the dormant `.card-3d` CSS),
   muck-exit for folds. Replaces the index-keyed `.card-deal` path. `PlayingCard`
   keeps a `noAnimate` static path (replay thumbnails).
4. **AnimatedCardRow** — identity-keyed (`suit-value-slot`) AnimatePresence wrapper
   fixing the "keyed by index can't re-animate" bug; used by CardHand, Board, seats.
5. **ChipFly + AnimatedCounter + ChipStack motion + chipMath util** — bets arc from
   seat→pot; pot/stack numbers tween with a gold flash; chip denomination math
   centralized in `utils/chipMath.ts`.
6. **ActionBadge + SeatMotion** — transient badge ('RAISE +500'/'FOLD'/'CHECK'/
   'CALL'/'ALL-IN'/'YOUR TURN') above a seat; seat fold-dim + turn-ring pulse +
   card muck. Dumb/presentational, fed booleans + lastAction by the diff hook.
7. **useTableActionFeed** (the engine) — turns each 3s snapshot into idempotent
   action events. Hold'em/Poker: cursor on `hand.actions[].action_index` (replays
   only new indices, staggered). Blackjack/Pai Gow: prev/next snapshot diffs
   (card-count up = hit/dealt, bet up = ChipFly, status/result change = stand/fold).
   The ONLY place that reads prev-vs-current; store stays a plain overwrite.
8. **Presence wrappers** — ModalShell / FadeSlide / StaggerList / RouteFade for the
   ~60 site-wide pop spots (modals, lobby rows, chat, banners, loading/empty,
   route changes).

## Phases (each independently shippable, CI-green)
- **P0 Foundation** — tokens, MotionConfig, DeckProvider/useDeckOrigin/DeckStack,
  usePrevious + useTableActionFeed scaffold. (M)
- **P1 Card primitives** — DealtCard, AnimatedCardRow, identity keying; swap
  CardHand + Board; remove `noAnimate` on Board. The "cards fly from a deck + flip"
  payoff, everywhere at once. (L)
- **P2 Chips/pot/counters** — ChipFly, AnimatedCounter, ChipStack layout, chipMath. (M)
- **P3 Seat presence + wire Hold'em** — SeatMotion + ActionBadge; useTableActionFeed
  on HoldemHandState.actions. First multiplayer payoff (other people bet/fold/clock). (L)
- **P4 Solo Poker parity** — same system on the SNG (bots). (M)
- **P5 Blackjack** — shoe-origin deals, dealer hole-card flip gating the outcome
  banner, hand-value pulse, inferred peer HIT/STAND badges. (L)
- **P6 Pai Gow** — 7-card deal+flip, HandSetter set choreography, dramatic dealer
  reveal, fortune ticker, peer deal/set indicators. (L)
- **P7 Site-wide enter/exit** — presence wrappers across modals/lists/banners/routes. (M)

## Backend
NONE required. Optional polish (deferred): a nullable per-hand `last_action` in the
blackjack table-state for exact peer HIT/STAND badges (value already in
`player_actions`); same idea for Pai Gow fold/forfeit.

## Risks (mitigations)
- Fly origins read at fire time (not render), portal'd to a fixed felt layer, short
  (0.6s) lifetimes — reflow-safe under the responsive seat grid.
- 3s polls can collapse multiple real actions; action-log path replays each
  `action_index` in order; inference paths show net change (acceptable v1).
- Cap `layout`/FLIP to where it matters; prefer plain x/y deals; reduced-motion drops
  transforms.
- Keep AnimatePresence on stable parents keyed by `hand.id`/`action_index`/card
  identity so exits run instead of remounts.
- P1 makes DealtCard the single card path first, so no long-lived mixed state.

Full per-surface audit + design: workflow run `wf_e9cb3777-732` output.
