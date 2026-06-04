/**
 * SeatMotion — wraps a seat so multiplayer presence is legible:
 * folded players dim + shrink, and the seat on the clock gets a pulsing ring.
 * Presentational; receives booleans from the table's action feed.
 */
import { motion } from "framer-motion";
import { type ReactNode } from "react";
import { useMotionPrefs } from "../motion/useMotionPrefs";

interface SeatMotionProps {
  isFolded?: boolean;
  isCurrentToAct?: boolean;
  children: ReactNode;
  className?: string;
}

export default function SeatMotion({
  isFolded = false,
  isCurrentToAct = false,
  children,
  className = "",
}: SeatMotionProps) {
  const reduced = useMotionPrefs();
  return (
    <motion.div
      animate={
        reduced
          ? { opacity: isFolded ? 0.45 : 1 }
          : { opacity: isFolded ? 0.45 : 1, scale: isFolded ? 0.96 : 1 }
      }
      transition={{ duration: 0.3 }}
      className={`relative ${className}`}
    >
      {isCurrentToAct && !isFolded && (
        <motion.div
          aria-hidden="true"
          className="absolute -inset-1 rounded-xl pointer-events-none z-10"
          animate={
            reduced
              ? {}
              : {
                  boxShadow: [
                    "0 0 0 0 rgba(244,208,63,0)",
                    "0 0 0 4px rgba(244,208,63,0.85)",
                    "0 0 0 0 rgba(244,208,63,0)",
                  ],
                }
          }
          transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
      {children}
    </motion.div>
  );
}
