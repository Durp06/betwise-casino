/**
 * DealtCard — the single animated card.
 *
 * Flies in from the shared deck origin (DeckProvider) with a rubber-hose bounce,
 * and 3D-flips when revealed (drives the dormant .card-3d CSS via framer). Used
 * everywhere cards appear in play; PlayingCard keeps a static path for thumbnails.
 *
 * Reduced motion: skips the fly + flip; cards fade in (opacity), order preserved.
 */
import { useLayoutEffect, useRef } from "react";
import { motion, useAnimationControls } from "framer-motion";
import PlayingCard from "./PlayingCard";
import type { Card } from "../types";
import { useDeckOrigin } from "../motion/useDeckOrigin";
import { useMotionPrefs } from "../motion/useMotionPrefs";
import { DEAL_SPRING, FLIP_TRANSITION, STAGGER_STEP } from "../motion/tokens";

interface DealtCardProps {
  card: Card | null;
  /** false renders the card back (opponent hole cards / pre-reveal). */
  faceUp?: boolean;
  /** slot index → deal stagger. */
  index?: number;
  /** fly in from the deck on mount (default true). */
  dealFromDeck?: boolean;
  className?: string;
}

export default function DealtCard({
  card,
  faceUp = true,
  index = 0,
  dealFromDeck = true,
  className = "",
}: DealtCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const getFlyFrom = useDeckOrigin();
  const reduced = useMotionPrefs();
  const fly = useAnimationControls();

  useLayoutEffect(() => {
    const delay = index * STAGGER_STEP;
    if (reduced || !dealFromDeck) {
      fly.set({ opacity: 0 });
      void fly.start({ opacity: 1, transition: { duration: 0.22, delay } });
      return;
    }
    const from = getFlyFrom(ref.current);
    fly.set({ x: from.x, y: from.y, opacity: 0, rotate: -22, scale: 0.86 });
    void fly.start({
      x: 0,
      y: 0,
      opacity: 1,
      rotate: 0,
      scale: 1,
      transition: { ...DEAL_SPRING, delay },
    });
    // mount-only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <motion.div
      ref={ref}
      animate={fly}
      exit={reduced ? { opacity: 0 } : { opacity: 0, x: -50, y: 36, rotate: 14, transition: { duration: 0.2 } }}
      className={`w-16 h-24 sm:w-20 sm:h-28 ${className}`}
      style={{ willChange: "transform" }}
    >
      <div className="card-3d w-full h-full">
        <motion.div
          className="card-inner"
          initial={{ rotateY: faceUp ? 0 : 180 }}
          animate={{ rotateY: faceUp ? 0 : 180 }}
          transition={reduced ? { duration: 0 } : FLIP_TRANSITION}
          style={{ transformStyle: "preserve-3d", width: "100%", height: "100%" }}
        >
          <div className="card-face">
            <PlayingCard card={card} index={index} noAnimate />
          </div>
          <div className="card-face card-face-back">
            <PlayingCard card={null} index={index} noAnimate />
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
