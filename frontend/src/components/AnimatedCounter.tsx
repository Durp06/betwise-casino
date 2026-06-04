/**
 * AnimatedCounter — a number that tweens to its new value (pot, stacks) and
 * flashes gold on an increase, instead of snapping. Respects reduced motion.
 */
import { useEffect, useRef, useState } from "react";
import { animate } from "framer-motion";
import { useMotionPrefs } from "../motion/useMotionPrefs";

interface AnimatedCounterProps {
  value: number;
  /** format the displayed (rounded) number, e.g. formatMoney. */
  format?: (n: number) => string;
  className?: string;
}

export default function AnimatedCounter({ value, format, className = "" }: AnimatedCounterProps) {
  const [display, setDisplay] = useState(value);
  const [flash, setFlash] = useState(false);
  const prev = useRef(value);
  const reduced = useMotionPrefs();

  useEffect(() => {
    if (prev.current === value) return;
    const increased = value > prev.current;
    if (reduced) {
      setDisplay(value);
    } else {
      const controls = animate(prev.current, value, {
        duration: 0.45,
        ease: "easeOut",
        onUpdate: (v) => setDisplay(Math.round(v)),
      });
      prev.current = value;
      if (increased) setFlash(true);
      const tid = window.setTimeout(() => setFlash(false), 450);
      return () => {
        controls.stop();
        window.clearTimeout(tid);
      };
    }
    prev.current = value;
  }, [value, reduced]);

  return (
    <span className={`${className} ${flash ? "text-gold-bright" : ""}`} style={{ transition: "color 0.3s ease" }}>
      {format ? format(display) : display}
    </span>
  );
}
