/**
 * Chipy.tsx — the BetWise Casino mascot ("V4 Modern").
 *
 * Clean chip identity that reads as a modern UI mascot, not a 1930s
 * rubber-hose cartoon. Eight thin notches around the rim, a single inner
 * ring for chip definition, big white eyes with one shine dot each, thin
 * minimal eyebrows, and a single-curve smile (no teeth). Framer Motion
 * drives idle "breathing" + occasional blinks; respects
 * `prefers-reduced-motion`.
 *
 * Props shape kept identical to the previous Cuphead-style Chipy so every
 * caller still works. The `animation` prop's "bounce" / "shake" / "spin" /
 * "think" branches map onto the idle motion config — they're kept for
 * back-compat but no longer drive separate CSS keyframes.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { motion, useReducedMotion } from "framer-motion";

export type ChipyExpression = "idle" | "thinking" | "happy" | "surprised";
export type ChipyAnimation  = "idle" | "bounce" | "shake" | "spin" | "think" | "none";
export type ChipyPose       = "rest" | "wave" | "thumbsup" | "point";

interface ChipyProps {
  size?: number;
  expression?: ChipyExpression;
  animation?: ChipyAnimation;
  pose?: ChipyPose;
  className?: string;
  style?: CSSProperties;
}

// ─── Palette ──────────────────────────────────────────────────────────────────
const FACE_RED = "#C0392B";
const RIM_RED  = "#922B21";
const CREAM    = "#F5F0E8";
const INK      = "#1A0A00";
const WHITE    = "#FFFFFF";

// ─── Notch ring (8 thin notches around the chip edge) ─────────────────────────
function NotchRing() {
  const count = 8;
  const radius = 39;
  const notches = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
    const cx = 50 + Math.cos(angle) * radius;
    const cy = 50 + Math.sin(angle) * radius;
    const rotateDeg = (angle * 180) / Math.PI + 90;
    notches.push(
      <rect
        key={i}
        x={cx - 1} y={cy - 2.5}
        width={2} height={5}
        rx={1}
        fill={CREAM} stroke={INK} strokeWidth={0.7}
        transform={`rotate(${rotateDeg} ${cx} ${cy})`}
      />,
    );
  }
  return <g>{notches}</g>;
}

// ─── Eyebrows ─────────────────────────────────────────────────────────────────
function Eyebrows({ expression }: { expression: ChipyExpression }) {
  const stroke = { stroke: INK, strokeWidth: 1.8, strokeLinecap: "round" as const, fill: "none" };
  switch (expression) {
    case "happy":
      return (
        <g {...stroke}>
          <path d="M 32 30 Q 38 27 44 29" />
          <path d="M 56 29 Q 62 27 68 30" />
        </g>
      );
    case "surprised":
      return (
        <g {...stroke}>
          <path d="M 32 27 Q 38 24 44 27" />
          <path d="M 56 27 Q 62 24 68 27" />
        </g>
      );
    case "thinking":
      return (
        <g {...stroke}>
          <path d="M 32 30 L 44 28" />
          <path d="M 56 28 Q 62 25 68 29" />
        </g>
      );
    default:
      return (
        <g {...stroke}>
          <path d="M 32 30 Q 38 28.5 44 30" />
          <path d="M 56 30 Q 62 28.5 68 30" />
        </g>
      );
  }
}

// ─── Eyes ─────────────────────────────────────────────────────────────────────
function Eyes({ expression, blink }: { expression: ChipyExpression; blink: boolean }) {
  if (blink) {
    return (
      <g stroke={INK} strokeWidth={2.4} strokeLinecap="round" fill="none">
        <path d="M 33 40 Q 39 43 45 40" />
        <path d="M 55 40 Q 61 43 67 40" />
      </g>
    );
  }
  if (expression === "happy") {
    return (
      <g stroke={INK} strokeWidth={2.6} strokeLinecap="round" fill="none">
        <path d="M 33 40 Q 39 33 45 40" />
        <path d="M 55 40 Q 61 33 67 40" />
      </g>
    );
  }
  const offsetX = expression === "thinking" ? -1 : 0;
  const offsetY = expression === "thinking" ? -1 : 0;
  const radius = expression === "surprised" ? 8 : 6.8;
  return (
    <g>
      <circle cx={39} cy={40} r={radius} fill={WHITE} stroke={INK} strokeWidth={2} />
      <circle cx={61} cy={40} r={radius} fill={WHITE} stroke={INK} strokeWidth={2} />
      <circle cx={39 + offsetX} cy={40 + offsetY} r={2.8} fill={INK} />
      <circle cx={61 + offsetX} cy={40 + offsetY} r={2.8} fill={INK} />
      <circle cx={40.5 + offsetX} cy={38 + offsetY} r={1.1} fill={WHITE} />
      <circle cx={62.5 + offsetX} cy={38 + offsetY} r={1.1} fill={WHITE} />
    </g>
  );
}

// ─── Mouth ────────────────────────────────────────────────────────────────────
function Mouth({ expression }: { expression: ChipyExpression }) {
  if (expression === "happy") {
    return (
      <g>
        <path
          d="M 35 56 Q 50 70 65 56"
          stroke={INK} strokeWidth={2.6} fill="none" strokeLinecap="round"
        />
        <path
          d="M 38 58 Q 50 67 62 58 Q 50 62 38 58 Z"
          fill={INK} opacity={0.8}
        />
      </g>
    );
  }
  if (expression === "surprised") {
    return <ellipse cx={50} cy={60} rx={3.5} ry={5} fill={INK} />;
  }
  if (expression === "thinking") {
    return (
      <path
        d="M 41 62 Q 50 60 58 63"
        stroke={INK} strokeWidth={2.4} fill="none" strokeLinecap="round"
      />
    );
  }
  return (
    <path
      d="M 37 57 Q 50 65 63 57"
      stroke={INK} strokeWidth={2.6} fill="none" strokeLinecap="round"
    />
  );
}

// ─── Gloves ───────────────────────────────────────────────────────────────────
function Glove({ side, pose }: { side: "left" | "right"; pose: ChipyPose }) {
  if (side === "left") {
    return (
      <g>
        <path d="M 18 56 Q 14 62 10 66" stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />
        <ellipse cx={9} cy={68} rx={7} ry={6} fill={WHITE} stroke={INK} strokeWidth={2} />
      </g>
    );
  }
  if (pose === "wave") {
    return (
      <g>
        <path d="M 82 50 Q 88 40 92 32" stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />
        <g transform="translate(91, 28) rotate(15)">
          <ellipse cx={0} cy={0} rx={7} ry={6} fill={WHITE} stroke={INK} strokeWidth={2} />
        </g>
      </g>
    );
  }
  if (pose === "thumbsup") {
    return (
      <g>
        <path d="M 82 50 Q 88 44 92 36" stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />
        <g transform="translate(92, 36)">
          <ellipse cx={0} cy={4} rx={7} ry={6} fill={WHITE} stroke={INK} strokeWidth={2} />
          <rect x={-2.5} y={-5} width={5} height={8} rx={2.4} fill={WHITE} stroke={INK} strokeWidth={1.8} />
        </g>
      </g>
    );
  }
  if (pose === "point") {
    return (
      <g>
        <path d="M 82 50 Q 88 46 94 42" stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />
        <g transform="translate(94, 42)">
          <ellipse cx={0} cy={4} rx={7} ry={6} fill={WHITE} stroke={INK} strokeWidth={2} />
          <rect x={6} y={2} width={8} height={4} rx={2} fill={WHITE} stroke={INK} strokeWidth={1.8} />
        </g>
      </g>
    );
  }
  return (
    <g>
      <path d="M 82 56 Q 86 62 90 66" stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />
      <ellipse cx={91} cy={68} rx={7} ry={6} fill={WHITE} stroke={INK} strokeWidth={2} />
    </g>
  );
}

// ─── Chipy root ───────────────────────────────────────────────────────────────
export default function Chipy({
  size = 96,
  expression = "idle",
  animation = "idle",
  pose = "rest",
  className = "",
  style,
}: ChipyProps) {
  const reduceMotion = useReducedMotion();
  const [blink, setBlink] = useState(false);

  // Periodic blinks (~ every 4-6 s). Skipped under prefers-reduced-motion.
  useEffect(() => {
    if (reduceMotion) return;
    let cancelled = false;
    const schedule = () => {
      const delay = 4200 + Math.random() * 2500;
      const id = window.setTimeout(() => {
        if (cancelled) return;
        setBlink(true);
        window.setTimeout(() => {
          if (cancelled) return;
          setBlink(false);
          schedule();
        }, 130);
      }, delay);
      return id;
    };
    const id = schedule();
    return () => {
      cancelled = true;
      if (id !== undefined) window.clearTimeout(id);
    };
  }, [reduceMotion]);

  // Idle "breathing" loop — subtle scale + a tiny rotational sway.
  // animation === "none" disables motion entirely.
  const idleAnim = reduceMotion || animation === "none"
    ? {}
    : { scale: [1, 1.025, 1], rotate: [0, -1, 1, 0] };

  const idleTransition = reduceMotion || animation === "none"
    ? { duration: 0 }
    : { duration: 3.4, repeat: Infinity, ease: "easeInOut" as const };

  return (
    <motion.div
      className={className}
      style={{ width: size, height: size, display: "inline-block", ...style }}
      role="img"
      aria-label={`Chipy mascot, ${expression}`}
      animate={idleAnim}
      transition={idleTransition}
    >
      <svg viewBox="0 0 100 100" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="chipy-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2.5" stdDeviation="1.4" floodColor={INK} floodOpacity={0.4} />
          </filter>
        </defs>

        {/* Rim peek */}
        <circle cx={50} cy={51.5} r={41} fill={RIM_RED} stroke={INK} strokeWidth={2.5} filter="url(#chipy-shadow)" />
        {/* Face */}
        <circle cx={50} cy={50} r={39} fill={FACE_RED} stroke={INK} strokeWidth={2.5} />
        <NotchRing />
        {/* Inner ring — chip-identity reinforcement */}
        <circle cx={50} cy={50} r={30} fill="none" stroke={INK} strokeWidth={1.5} opacity={0.5} />

        <Eyebrows expression={expression} />
        <Eyes expression={expression} blink={blink} />
        <Mouth expression={expression} />

        <Glove side="left"  pose="rest" />
        <Glove side="right" pose={pose} />
      </svg>
    </motion.div>
  );
}
