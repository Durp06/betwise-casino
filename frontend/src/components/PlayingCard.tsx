/**
 * PlayingCard.tsx — rubber-hose-cartoon playing card.
 *
 * White-cream face, 3 px black outline, chunky suit SVG in the center,
 * Lilita One values in two corners. Back of card uses the diamond
 * pattern in deep red. Deal-in animation via `.card-deal`.
 */
import type { Card } from "../types";
import { t } from "../i18n";

interface PlayingCardProps {
  card: Card | null;
  className?: string;
  index?: number;
  noAnimate?: boolean;
}

const RED_SUITS = new Set(["hearts", "diamonds"]);

function jitterDeg(index: number): number {
  const pattern = [-2, 1.2, -0.8, 1.6, -1.4, 1.0];
  return pattern[index % pattern.length];
}

// ─── Suit symbols as chunky SVG paths (with their own ink outlines) ──────

function SuitGlyph({ suit }: { suit: string }) {
  const fill = RED_SUITS.has(suit) ? "#C0392B" : "#1A0A00";
  const stroke = "#1A0A00";

  if (suit === "hearts") {
    return (
      <svg viewBox="0 0 32 32" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        <path
          d="M16 28 C 8 22 2 18 2 12 C 2 7 6 4 10 4 C 13 4 15 6 16 8 C 17 6 19 4 22 4 C 26 4 30 7 30 12 C 30 18 24 22 16 28 Z"
          fill={fill} stroke={stroke} strokeWidth={2.5} strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (suit === "diamonds") {
    return (
      <svg viewBox="0 0 32 32" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        <path
          d="M16 3 L 28 16 L 16 29 L 4 16 Z"
          fill={fill} stroke={stroke} strokeWidth={2.5} strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (suit === "spades") {
    return (
      <svg viewBox="0 0 32 32" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        <path
          d="M16 3 C 22 9 28 14 28 19 C 28 23 25 25 22 25 C 20 25 18 24 17 22 L 19 30 L 13 30 L 15 22 C 14 24 12 25 10 25 C 7 25 4 23 4 19 C 4 14 10 9 16 3 Z"
          fill={fill} stroke={stroke} strokeWidth={2.5} strokeLinejoin="round"
        />
      </svg>
    );
  }
  // clubs
  return (
    <svg viewBox="0 0 32 32" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
      <circle cx={16} cy={10} r={5.5} fill={fill} stroke={stroke} strokeWidth={2.5} />
      <circle cx={9}  cy={18} r={5.5} fill={fill} stroke={stroke} strokeWidth={2.5} />
      <circle cx={23} cy={18} r={5.5} fill={fill} stroke={stroke} strokeWidth={2.5} />
      <path
        d="M14 22 L 13 30 L 19 30 L 18 22 Z"
        fill={fill} stroke={stroke} strokeWidth={2.5} strokeLinejoin="round"
      />
    </svg>
  );
}

export default function PlayingCard({
  card,
  className = "",
  index = 0,
  noAnimate = false,
}: PlayingCardProps) {
  const tilt = jitterDeg(index);
  const animClass = noAnimate ? "" : "card-deal";

  // Face-down
  if (!card) {
    return (
      <div
        className={`card-back-pattern ink-outline-thick w-16 h-24 sm:w-20 sm:h-28 rounded-md
          relative flex items-center justify-center ${animClass} ${className}`}
        aria-label={t("Face-down card")}
        style={{
          ["--card-tilt" as string]: `${tilt}deg`,
          transform: noAnimate ? `rotate(${tilt}deg)` : undefined,
          boxShadow: "3px 3px 0 0 #1A0A00",
        }}
      >
        {/* Inner cream border — accent ring */}
        <div className="absolute inset-1 rounded-sm border-2 border-cream/70" />
      </div>
    );
  }

  const isRed = RED_SUITS.has(card.suit);
  const cornerColor = isRed ? "#C0392B" : "#1A0A00";

  return (
    <div
      className={`paper-grain ink-outline-thick w-16 h-24 sm:w-20 sm:h-28 rounded-md
        relative flex flex-col justify-between p-1.5 ${animClass} ${className}`}
      aria-label={`${card.value} of ${card.suit}`}
      style={{
        backgroundColor: "#F5F0E8",
        ["--card-tilt" as string]: `${tilt}deg`,
        transform: noAnimate ? `rotate(${tilt}deg)` : undefined,
        boxShadow: "4px 4px 0 0 #1A0A00",
      }}
    >
      {/* Top-left value */}
      <span
        className="text-xl leading-none font-ui"
        style={{ color: cornerColor }}
      >
        {card.value}
      </span>

      {/* Center suit */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div style={{ width: "55%", height: "55%" }}>
          <SuitGlyph suit={card.suit} />
        </div>
      </div>

      {/* Bottom-right value (rotated) */}
      <span
        className="text-xl leading-none font-ui self-end rotate-180"
        style={{ color: cornerColor }}
      >
        {card.value}
      </span>
    </div>
  );
}
