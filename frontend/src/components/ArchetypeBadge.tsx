/**
 * ArchetypeBadge.tsx — small pill showing a bot's archetype name.
 *
 * Color-coded by archetype family (tight/aggressive/loose-passive/loose-
 * aggressive/balanced). Includes a title attribute with the archetype's
 * description for hover tooltips.
 */
import { t } from "../i18n";

interface ArchetypeBadgeProps {
  archetypeName: string | null;
  isBot: boolean;
}

const TIGHT_AGG = "bg-red-100 text-red-900 border-red-700";
const LOOSE_AGG = "bg-orange-100 text-orange-900 border-orange-700";
const TIGHT_PASS = "bg-blue-100 text-blue-900 border-blue-700";
const LOOSE_PASS = "bg-green-100 text-green-900 border-green-700";
const BALANCED = "bg-purple-100 text-purple-900 border-purple-700";
const HUMAN = "bg-cream text-ink border-ink";

const ARCHETYPE_COLOR: Record<string, string> = {
  TAG: TIGHT_AGG,
  ABC: TIGHT_AGG,
  Nit: TIGHT_PASS,
  SetMiner: TIGHT_PASS,
  Trapper: TIGHT_PASS,
  LAG: LOOSE_AGG,
  Maniac: LOOSE_AGG,
  CallingStation: LOOSE_PASS,
  Whale: LOOSE_PASS,
  TAGFish: LOOSE_PASS,
  Shark: BALANCED,
};

const ARCHETYPE_DESCRIPTION: Record<string, string> = {
  TAG: "Tight-aggressive. Plays strong ranges; raises not limps; folds to real strength.",
  LAG: "Loose-aggressive. Wide opens; 3-bet bluffs; barrels multiple streets.",
  Nit: "Folds almost everything. Big-bets only the near-nuts. Highly bluffable.",
  CallingStation: "Calls down with anything. Impossible to bluff — value-bet thin.",
  Maniac: "Random aggression. Distinguished from a fish by high PFR/AF.",
  SetMiner: "Plays small pairs cheap hoping to flop a set; passive otherwise.",
  ABC: "Straightforward. Value-bets strong, folds weak. No creativity.",
  TAGFish: "Looks TAG by preflop stats; leaks postflop.",
  Whale: "Plays everything; calls big bets without concern.",
  Trapper: "Slow-plays monsters; passive line that explodes.",
  Shark: "Balanced and near-unexploitable. Tells vanish.",
};

export default function ArchetypeBadge({ archetypeName, isBot }: ArchetypeBadgeProps) {
  if (!isBot) {
    return (
      <span
        className={`px-2 py-0.5 text-[10px] uppercase tracking-widest rounded-full border-2 font-ui ${HUMAN}`}
        data-testid="archetype-badge-human"
      >
        {t("You")}
      </span>
    );
  }
  if (!archetypeName) return null;
  const color = ARCHETYPE_COLOR[archetypeName] ?? "bg-gray-100 text-gray-900 border-gray-700";
  const description = ARCHETYPE_DESCRIPTION[archetypeName] ?? "";
  return (
    <span
      className={`px-2 py-0.5 text-[10px] uppercase tracking-widest rounded-full border-2 font-ui ${color}`}
      title={description}
      data-testid={`archetype-badge-${archetypeName}`}
    >
      {t(archetypeName)}
    </span>
  );
}
