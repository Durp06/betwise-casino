/**
 * ModalShell — the shared modal chrome: a fading backdrop + a popping panel.
 * Replaces each modal's hand-rolled `fixed inset-0 bg-black/70` backdrop so they
 * all enter/exit with one motion vocabulary. Clicking the backdrop calls onClose;
 * clicks inside the panel don't. The panel root animates on mount (enter) on its
 * own; to also animate EXIT, render the modal inside an <AnimatePresence> in the
 * parent (so it stays mounted through the exit).
 */
import { motion } from "framer-motion";
import { BACKDROP_FADE, MODAL_POP } from "../tokens";

interface ModalShellProps {
  onClose: () => void;
  children: React.ReactNode;
  /** Tailwind classes for the panel (size, colors, padding). */
  panelClassName?: string;
  ariaLabel?: string;
}

export default function ModalShell({ onClose, children, panelClassName = "", ariaLabel }: ModalShellProps) {
  return (
    <motion.div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={BACKDROP_FADE}
      onClick={onClose}
    >
      <motion.div
        className={panelClassName}
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, scale: 0.92, y: 14 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={MODAL_POP}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}
