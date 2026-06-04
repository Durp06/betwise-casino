/**
 * ChipFly — a small stack of chips that arcs from a seat to the pot when that
 * seat bets/raises/calls. Portal'd to <body> as a fixed-position layer and
 * reads the seat + pot rects at fire time (reflow-safe). Removes itself on
 * completion. Skipped entirely under reduced motion.
 */
import { useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { useDeckContext } from "../motion/DeckProvider";
import { useMotionPrefs } from "../motion/useMotionPrefs";
import { CHIP_FLY } from "../motion/tokens";
import { chipBreakdown, CHIP_COLOR } from "../utils/chipMath";

interface ChipFlyProps {
  seatNumber: number;
  amount: number;
  onDone: () => void;
}

export default function ChipFly({ seatNumber, amount, onDone }: ChipFlyProps) {
  const ctx = useDeckContext();
  const reduced = useMotionPrefs();
  const [pts, setPts] = useState<{ fx: number; fy: number; tx: number; ty: number } | null>(null);

  useLayoutEffect(() => {
    if (reduced) {
      onDone();
      return;
    }
    const seat = ctx?.getSeatRect(seatNumber);
    const pot = ctx?.potRef.current?.getBoundingClientRect();
    if (!seat || !pot) {
      onDone();
      return;
    }
    setPts({
      fx: seat.left + seat.width / 2,
      fy: seat.top + seat.height / 2,
      tx: pot.left + pot.width / 2,
      ty: pot.top + pot.height / 2,
    });
    // mount-only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!pts) return null;
  const chips = chipBreakdown(amount);
  const liftY = Math.min(pts.fy, pts.ty) - 48; // arc apex

  return createPortal(
    <motion.div
      aria-hidden="true"
      initial={{ x: pts.fx, y: pts.fy, opacity: 0, scale: 0.8 }}
      animate={{ x: [pts.fx, pts.tx], y: [pts.fy, liftY, pts.ty], opacity: [0, 1, 1, 0.9], scale: 1 }}
      transition={CHIP_FLY}
      onAnimationComplete={onDone}
      style={{ position: "fixed", top: 0, left: 0, marginLeft: -14, marginTop: -14, zIndex: 60, pointerEvents: "none" }}
    >
      <div className="relative w-7 h-7">
        {chips.map((d, i) => (
          <div
            key={i}
            className="absolute w-7 h-7 rounded-full border-2 border-ink"
            style={{ backgroundColor: CHIP_COLOR[d], top: -i * 3, boxShadow: "1px 1px 0 0 #1A0A00" }}
          />
        ))}
      </div>
    </motion.div>,
    document.body,
  );
}
