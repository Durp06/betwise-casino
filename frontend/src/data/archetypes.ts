/**
 * archetypes.ts — frontend display metadata for poker bot archetypes.
 *
 * Single source of truth on the client for "how does this bot play?". Mirrors
 * the behavioural parameters of the backend `ARCHETYPE_REGISTRY`
 * (backend/game/poker/archetypes.py) but in player-facing prose plus two
 * teaching axes:
 *
 *   - looseness  (0 = nit-tight / folds almost everything,
 *                 100 = plays nearly every hand)
 *   - aggression (0 = passive / calls and checks,
 *                 100 = relentless betting and raising)
 *
 * Those two axes are the classic poker player-type matrix (Tight↔Loose ×
 * Passive↔Aggressive). The ArchetypeBadge tooltip renders them as meters so a
 * learner can place each opponent at a glance.
 *
 * Strings here are raw English content; the component routes every visible
 * string through the i18n `t()` helper at render time (convention #12).
 */

export interface ArchetypeMeta {
  /** Registry key, e.g. "TAG" — matches PokerSeat.archetype_name. */
  name: string;
  /** Short tagline / expansion shown under the name, e.g. "Tight-Aggressive". */
  tagline: string;
  /** Hellmuth-style animal nickname, or null if the archetype has none. */
  animal: string | null;
  /** 1–2 sentences: how this player actually plays. */
  style: string;
  /** One sentence: how to beat them. */
  exploit: string;
  /** 0–100, Tight → Loose. */
  looseness: number;
  /** 0–100, Passive → Aggressive. */
  aggression: number;
}

export const ARCHETYPE_META: Record<string, ArchetypeMeta> = {
  TAG: {
    name: "TAG",
    tagline: "Tight-Aggressive",
    animal: "Lion",
    style:
      "Plays only strong hands, but bets and raises hard when they enter a pot. Opens with raises rather than limps, c-bets often, and folds when they sense real strength.",
    exploit: "Respect their raises, attack their blinds, and give up when they fire back.",
    looseness: 28,
    aggression: 72,
  },
  LAG: {
    name: "LAG",
    tagline: "Loose-Aggressive",
    animal: null,
    style:
      "Enters a huge range of pots and applies relentless pressure — wide opens, light 3-bet bluffs, and barrels across multiple streets. Very hard to put on a hand.",
    exploit: "Tighten up and let them bluff into your strong hands — trap, don't bluff back.",
    looseness: 58,
    aggression: 90,
  },
  Nit: {
    name: "Nit",
    tagline: "The rock",
    animal: "Mouse",
    style:
      "Folds almost everything and only commits chips with the near-nuts. When a Nit finally bets big, believe it.",
    exploit: "Steal relentlessly and fold the instant they wake up with a raise.",
    looseness: 12,
    aggression: 32,
  },
  CallingStation: {
    name: "CallingStation",
    tagline: "Can't be bluffed",
    animal: "Elephant",
    style:
      "Calls bets with any piece of the board and almost never folds or raises. They chase draws and pay off value to the river.",
    exploit: "Never bluff them — value-bet thin and size your good hands up.",
    looseness: 78,
    aggression: 12,
  },
  Maniac: {
    name: "Maniac",
    tagline: "Chaos engine",
    animal: "Jackal",
    style:
      "Raises and re-raises with little regard for their cards — constant, near-random aggression. High-variance chaos that piles pressure on everyone.",
    exploit: "Wait for a real hand and let them barrel chips at you; don't try to out-bluff them.",
    looseness: 88,
    aggression: 98,
  },
  SetMiner: {
    name: "SetMiner",
    tagline: "Hunting sets",
    animal: "Mouse",
    style:
      "Limps or calls cheaply with small and medium pairs hoping to flop a set, then plays passively whenever they miss.",
    exploit: "Bet enough that drawing to a set is unprofitable; fold to their rare big aggression.",
    looseness: 24,
    aggression: 28,
  },
  ABC: {
    name: "ABC",
    tagline: "Textbook, no tricks",
    animal: "Lion",
    style:
      "Straightforward, by-the-book poker — value-bets strong hands, checks or folds weak ones, and almost never bluffs or gets creative.",
    exploit: "Bluff their obvious weak lines and fold when they finally bet big.",
    looseness: 26,
    aggression: 58,
  },
  TAGFish: {
    name: "TAGFish",
    tagline: "Solid preflop, leaks after",
    animal: null,
    style:
      "Looks like a disciplined TAG before the flop, but leaks afterward — over-calls, auto-pilots c-bets, and pays off too often postflop.",
    exploit: "Value-bet relentlessly after the flop; they call far too wide once cards hit the board.",
    looseness: 40,
    aggression: 52,
  },
  Whale: {
    name: "Whale",
    tagline: "Calls everything, reloads",
    animal: "Elephant",
    style:
      "A calling station with a deep wallet — plays nearly every hand and calls big bets without concern, happily reloading after a bust.",
    exploit: "Pure value: bet big with strong hands and never try to bluff them off a pot.",
    looseness: 92,
    aggression: 10,
  },
  Trapper: {
    name: "Trapper",
    tagline: "Slow-plays monsters",
    animal: null,
    style:
      "Disguises monster hands by flat-calling and checking, luring you in before the line suddenly explodes with a big raise.",
    exploit: "Beware the passive line that explodes — pot-control medium hands and don't pay off the check-raise.",
    looseness: 30,
    aggression: 34,
  },
  Shark: {
    name: "Shark",
    tagline: "Balanced, unexploitable",
    animal: "Eagle",
    style:
      "Balanced and tough to read — mixes value bets and bluffs at the right frequencies so no single tell gives them away.",
    exploit: "Play fundamentally sound and avoid marginal spots; there's no easy leak to attack.",
    looseness: 46,
    aggression: 74,
  },
};

/**
 * Look up display metadata for an archetype name. Returns null for unknown or
 * missing names so callers can degrade gracefully (e.g. render just the badge
 * with no tooltip).
 */
export function getArchetypeMeta(archetypeName: string | null): ArchetypeMeta | null {
  if (!archetypeName) return null;
  return ARCHETYPE_META[archetypeName] ?? null;
}
