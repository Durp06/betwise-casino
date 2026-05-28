/**
 * Chipy.tsx — the BetWise Casino mascot, driven by a hand-painted sprite sheet.
 *
 * The art lives at `frontend/src/assets/chipy/chipy-spritesheet.png` — a
 * 4×4 grid of 16 expressions/poses generated as one PNG. We pick one cell
 * per `ChipyExpression` via the classic CSS sprite technique: scale the
 * background to 400% × 400% so the full sheet is 4× the display size in
 * both dimensions, then offset the position to land on the desired cell.
 *
 * Framer Motion wraps the sprite container with a subtle idle bob +
 * rotational sway, respecting `prefers-reduced-motion`. Blink animation
 * is omitted because that would require additional blink-frame sprites;
 * the idle bob carries the liveliness for now.
 *
 * Same props shape as previous Chipy revs so every caller still works.
 *
 * Pose prop note: the spritesheet bakes arm positions into each cell, so
 * `pose` is currently a no-op. Kept on the props for API stability and
 * future sprite expansions (we could add `chipy-wave.png` etc. later).
 */
import { type CSSProperties } from "react";
import { motion, useReducedMotion } from "framer-motion";
import spritesheetUrl from "../assets/chipy/chipy-spritesheet.png";

export type ChipyExpression = "idle" | "thinking" | "happy" | "surprised";
export type ChipyAnimation  = "idle" | "bounce" | "shake" | "spin" | "think" | "none";
export type ChipyPose       = "rest" | "wave" | "thumbsup" | "point";

interface ChipyProps {
  size?: number;
  expression?: ChipyExpression;
  animation?: ChipyAnimation;
  /** Currently a no-op — arm positions are baked into each sprite. Kept for
   *  API stability; future pose-specific sprites can be wired in here. */
  pose?: ChipyPose;
  className?: string;
  style?: CSSProperties;
}

// ─── Spritesheet layout ──────────────────────────────────────────────────────

const COLS = 4;
const ROWS = 4;

/**
 * Which cell of the 4×4 sheet each expression maps to. Cells are indexed
 * top-left = (0, 0), with col growing right and row growing down.
 *
 * The picks below are the curated "best fit" per emotion from the 16
 * available cells — easy to swap if a different cell reads better in app.
 */
const SPRITE_CELLS: Record<ChipyExpression, { row: number; col: number; label: string }> = {
  idle:      { row: 0, col: 2, label: "confident smirk, crossed arms" },
  happy:     { row: 0, col: 3, label: "big grin, arms raised" },
  thinking:  { row: 1, col: 1, label: "winking smirk" },
  surprised: { row: 2, col: 0, label: "wide eyes, hands at face, O mouth" },
};

// Convert (col, row) → background-position percentages. With background-size
// set to (COLS * 100%, ROWS * 100%), a position of 100% / (COLS - 1) per
// column step lands exactly on the next cell.
function spritePosition(col: number, row: number): string {
  const x = (col / (COLS - 1)) * 100;
  const y = (row / (ROWS - 1)) * 100;
  return `${x}% ${y}%`;
}

// ─── Chipy root ──────────────────────────────────────────────────────────────

export default function Chipy({
  size = 96,
  expression = "idle",
  animation = "idle",
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  pose: _pose = "rest",
  className = "",
  style,
}: ChipyProps) {
  const reduceMotion = useReducedMotion();
  const cell = SPRITE_CELLS[expression];

  const idleAnim = reduceMotion || animation === "none"
    ? {}
    : { y: [0, -3, 0], rotate: [0, -1, 1, 0] };

  const idleTransition = reduceMotion || animation === "none"
    ? { duration: 0 }
    : { duration: 3.4, repeat: Infinity, ease: "easeInOut" as const };

  return (
    <motion.div
      className={className}
      style={{
        width: size,
        height: size,
        display: "inline-block",
        backgroundImage: `url(${spritesheetUrl})`,
        backgroundSize: `${COLS * 100}% ${ROWS * 100}%`,
        backgroundPosition: spritePosition(cell.col, cell.row),
        backgroundRepeat: "no-repeat",
        // image-rendering: high-quality interpolation when scaling down a
        // raster PNG to small sizes (80–96px). Without this, browsers can
        // pick a "smart" downscale that softens line art.
        imageRendering: "auto",
        ...style,
      }}
      role="img"
      aria-label={`Chipy mascot, ${expression} (${cell.label})`}
      animate={idleAnim}
      transition={idleTransition}
    />
  );
}
