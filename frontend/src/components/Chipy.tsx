/**
 * Chipy.tsx — the BetWise Casino mascot.
 *
 * A poker chip viewed at a slight 3/4 angle, with cartoon eyes, a wide
 * grin, and white Mickey-Mouse-style gloves on stub arms. Built as an
 * inline SVG so every stroke can be themed; no external assets.
 *
 * All animations are CSS keyframes (see index.css), wrapped behind
 * `prefers-reduced-motion`.
 */
import type { CSSProperties } from "react";

export type ChipyExpression = "idle" | "thinking" | "happy" | "surprised";
export type ChipyAnimation  = "idle" | "bounce"   | "shake" | "spin" | "think" | "none";
export type ChipyPose       = "rest" | "wave"     | "thumbsup" | "point";

interface ChipyProps {
  size?: number;
  expression?: ChipyExpression;
  animation?: ChipyAnimation;
  pose?: ChipyPose;
  className?: string;
  style?: CSSProperties;
}

// ─── Palette (locked at component scope so Chipy reads the same anywhere) ───
const FACE_RED       = "#C0392B";
const RIM_RED        = "#922B21";
const CREAM          = "#F5F0E8";
const INK            = "#1A0A00";
const GLOVE_WHITE    = "#FFFFFF";
const TONGUE_PINK    = "#E67373";

// Notch ring — 16 small rectangles arranged at radius around the chip face
function NotchRing() {
  const count = 16;
  const radius = 38;
  const notches = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
    const cx = 50 + Math.cos(angle) * radius;
    const cy = 50 + Math.sin(angle) * radius;
    const rotateDeg = (angle * 180) / Math.PI + 90;
    notches.push(
      <rect
        key={i}
        x={cx - 1.8}
        y={cy - 3}
        width={3.6}
        height={6}
        fill={CREAM}
        stroke={INK}
        strokeWidth={0.8}
        transform={`rotate(${rotateDeg} ${cx} ${cy})`}
      />,
    );
  }
  return <g>{notches}</g>;
}

// Iris position based on expression
function irisOffsetFor(expression: ChipyExpression): { x: number; y: number } {
  switch (expression) {
    case "thinking":  return { x: -1.5, y: -1.5 };  // up-left, "pondering"
    case "happy":     return { x: 0, y: 0 };         // n/a (squint path)
    case "surprised": return { x: 0, y: 0 };
    default:          return { x: 0, y: 0 };
  }
}

function Eyes({ expression }: { expression: ChipyExpression }) {
  const irisOffset = irisOffsetFor(expression);

  // Happy squint — both eyes are upward-curving arcs (no irises)
  if (expression === "happy") {
    return (
      <g>
        <path
          d="M 32 38 Q 38 31 44 38"
          stroke={INK} strokeWidth={2.5} fill="none" strokeLinecap="round"
        />
        <path
          d="M 56 38 Q 62 31 68 38"
          stroke={INK} strokeWidth={2.5} fill="none" strokeLinecap="round"
        />
      </g>
    );
  }

  // Surprised — small irises, wide eye whites
  if (expression === "surprised") {
    return (
      <g>
        <circle cx={38} cy={38} r={7.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2.2} />
        <circle cx={62} cy={38} r={7.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2.2} />
        <circle cx={38} cy={38} r={1.5} fill={INK} />
        <circle cx={62} cy={38} r={1.5} fill={INK} />
      </g>
    );
  }

  // Idle / thinking — normal eyes, with offset irises
  return (
    <g>
      <circle cx={38} cy={38} r={7} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2.2} />
      <circle cx={62} cy={38} r={7} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2.2} />
      <circle cx={38 + irisOffset.x} cy={38 + irisOffset.y} r={3} fill={INK} />
      <circle cx={62 + irisOffset.x} cy={38 + irisOffset.y} r={3} fill={INK} />
      {/* Glint highlights */}
      <circle cx={39.5 + irisOffset.x} cy={36.5 + irisOffset.y} r={1.1} fill={CREAM} />
      <circle cx={63.5 + irisOffset.x} cy={36.5 + irisOffset.y} r={1.1} fill={CREAM} />
    </g>
  );
}

function Mouth({ expression }: { expression: ChipyExpression }) {
  // Open excited (happy) — wide grin with teeth visible
  if (expression === "happy") {
    return (
      <g>
        {/* Outer mouth */}
        <path
          d="M 30 56 Q 50 76 70 56 Q 50 70 30 56 Z"
          fill={INK} stroke={INK} strokeWidth={2.4} strokeLinejoin="round"
        />
        {/* Teeth row */}
        <rect x={36} y={58} width={5} height={6} fill={CREAM} stroke={INK} strokeWidth={1} />
        <rect x={42} y={59} width={5} height={7} fill={CREAM} stroke={INK} strokeWidth={1} />
        <rect x={48} y={60} width={5} height={7} fill={CREAM} stroke={INK} strokeWidth={1} />
        <rect x={54} y={59} width={5} height={7} fill={CREAM} stroke={INK} strokeWidth={1} />
        {/* Tongue peek */}
        <ellipse cx={50} cy={67} rx={6} ry={2.5} fill={TONGUE_PINK} stroke={INK} strokeWidth={1} />
      </g>
    );
  }

  // Surprised — small round O mouth
  if (expression === "surprised") {
    return (
      <ellipse cx={50} cy={62} rx={4.5} ry={5.5} fill={INK} stroke={INK} strokeWidth={2} />
    );
  }

  // Thinking — flat neutral line with slight curve
  if (expression === "thinking") {
    return (
      <path
        d="M 38 62 Q 50 60 62 62"
        stroke={INK} strokeWidth={2.5} fill="none" strokeLinecap="round"
      />
    );
  }

  // Idle — wide rubber-hose grin with three teeth
  return (
    <g>
      <path
        d="M 34 56 Q 50 70 66 56"
        stroke={INK} strokeWidth={2.8} fill="none" strokeLinecap="round"
      />
      {/* Teeth peeking under the smile line — small rectangles */}
      <g transform="translate(0, 1)">
        <rect x={42} y={58.5} width={4} height={4} fill={CREAM} stroke={INK} strokeWidth={0.8} />
        <rect x={46} y={59.5} width={4} height={4.5} fill={CREAM} stroke={INK} strokeWidth={0.8} />
        <rect x={50} y={59.5} width={4} height={4.5} fill={CREAM} stroke={INK} strokeWidth={0.8} />
        <rect x={54} y={58.5} width={4} height={4} fill={CREAM} stroke={INK} strokeWidth={0.8} />
      </g>
    </g>
  );
}

function Glove({ side, pose }: { side: "left" | "right"; pose: ChipyPose }) {
  // Left glove always at rest; only the right glove changes pose
  if (side === "left") {
    return (
      <g>
        {/* Stub arm */}
        <line x1={18} y1={54} x2={9} y2={62} stroke={INK} strokeWidth={4} strokeLinecap="round" />
        {/* Glove — circular hand with three finger bumps on top */}
        <g transform="translate(2, 60)">
          <circle cx={6} cy={3} r={5.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2} />
          {/* Three finger bumps */}
          <circle cx={2.5} cy={-1} r={1.6} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
          <circle cx={6}   cy={-2} r={1.8} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
          <circle cx={9.5} cy={-1} r={1.6} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
        </g>
      </g>
    );
  }

  // Right glove — varies by pose
  if (pose === "wave") {
    return (
      <g>
        <line x1={82} y1={50} x2={92} y2={32} stroke={INK} strokeWidth={4} strokeLinecap="round" />
        <g transform="translate(88, 22) rotate(15)">
          <circle cx={4} cy={4} r={5.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2} />
          <circle cx={0}  cy={2} r={1.8} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
          <circle cx={4}  cy={0} r={2}   fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
          <circle cx={8}  cy={2} r={1.8} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
        </g>
      </g>
    );
  }

  if (pose === "thumbsup") {
    return (
      <g>
        <line x1={82} y1={50} x2={92} y2={36} stroke={INK} strokeWidth={4} strokeLinecap="round" />
        <g transform="translate(89, 26)">
          {/* Fist */}
          <circle cx={4} cy={6} r={5.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2} />
          {/* Thumb pointing up */}
          <rect x={2.5} y={-2} width={3.5} height={6} rx={1.7} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.6} />
        </g>
      </g>
    );
  }

  if (pose === "point") {
    return (
      <g>
        <line x1={82} y1={50} x2={94} y2={42} stroke={INK} strokeWidth={4} strokeLinecap="round" />
        <g transform="translate(90, 36)">
          <circle cx={4} cy={6} r={5.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2} />
          {/* Pointing finger */}
          <rect x={8} y={4.5} width={6} height={3} rx={1.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.6} />
        </g>
      </g>
    );
  }

  // Rest — glove hanging at side
  return (
    <g>
      <line x1={82} y1={54} x2={91} y2={62} stroke={INK} strokeWidth={4} strokeLinecap="round" />
      <g transform="translate(88, 60)">
        <circle cx={6} cy={3} r={5.5} fill={GLOVE_WHITE} stroke={INK} strokeWidth={2} />
        <circle cx={2.5} cy={-1} r={1.6} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
        <circle cx={6}   cy={-2} r={1.8} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
        <circle cx={9.5} cy={-1} r={1.6} fill={GLOVE_WHITE} stroke={INK} strokeWidth={1.4} />
      </g>
    </g>
  );
}

export default function Chipy({
  size = 96,
  expression = "idle",
  animation = "idle",
  pose = "rest",
  className = "",
  style,
}: ChipyProps) {
  const animClass =
    animation === "none" ? "" : `chipy-animate-${animation}`;

  return (
    <div
      className={`${animClass} ${className}`}
      style={{ width: size, height: size, display: "inline-block", ...style }}
      role="img"
      aria-label={`Chipy mascot, ${expression}`}
    >
      <svg viewBox="0 0 100 100" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        {/* Chip rim — slight 3/4 angle suggested via offset darker ellipse */}
        <ellipse cx={51.5} cy={53} rx={40} ry={40} fill={RIM_RED} stroke={INK} strokeWidth={3} />

        {/* Chip face — sits on top, slightly up-left so the rim peeks bottom-right */}
        <circle cx={50} cy={50} r={38} fill={FACE_RED} stroke={INK} strokeWidth={3} />

        {/* Notch ring around the inner edge */}
        <NotchRing />

        {/* Inner face circle (lighter cream-edge ring for definition) */}
        <circle cx={50} cy={50} r={28} fill={FACE_RED} stroke={INK} strokeWidth={2} />

        {/* Eyes */}
        <Eyes expression={expression} />

        {/* Mouth */}
        <Mouth expression={expression} />

        {/* Gloves */}
        <Glove side="left" pose="rest" />
        <Glove side="right" pose={pose} />
      </svg>
    </div>
  );
}
