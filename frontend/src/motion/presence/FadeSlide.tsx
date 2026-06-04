/**
 * FadeSlide — a single element that fades + slides in on mount (and out, when
 * rendered inside an <AnimatePresence>). Use for banners, outcome reveals, and
 * chat messages so they don't pop. Reduced motion keeps the fade, drops the slide.
 */
import { motion } from "framer-motion";
import { FADE_SLIDE } from "../tokens";

interface FadeSlideProps {
  children: React.ReactNode;
  className?: string;
  /** Initial vertical offset in px (positive = slides up into place). */
  y?: number;
}

export default function FadeSlide({ children, className = "", y = 10 }: FadeSlideProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -y }}
      transition={FADE_SLIDE}
    >
      {children}
    </motion.div>
  );
}
