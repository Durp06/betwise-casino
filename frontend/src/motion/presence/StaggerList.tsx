/**
 * StaggerList / StaggerItem — a container whose children rise+fade in one after
 * another instead of all popping at once. Use for lobby table lists, the game
 * picker, leaderboard rows, hand-history rows, etc.:
 *
 *   <StaggerList className="flex flex-col gap-3">
 *     {items.map((it) => <StaggerItem key={it.id}>…</StaggerItem>)}
 *   </StaggerList>
 *
 * Reduced motion drops the slide (transform) and keeps the fade.
 */
import { motion } from "framer-motion";
import type { Variants } from "framer-motion";
import { STAGGER_STEP } from "../tokens";

const containerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: STAGGER_STEP } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.26, ease: "easeOut" } },
};

interface StaggerListProps {
  children: React.ReactNode;
  className?: string;
}

export function StaggerList({ children, className = "" }: StaggerListProps) {
  return (
    <motion.div className={className} variants={containerVariants} initial="hidden" animate="show">
      {children}
    </motion.div>
  );
}

interface StaggerItemProps {
  children: React.ReactNode;
  className?: string;
}

export function StaggerItem({ children, className = "" }: StaggerItemProps) {
  return (
    <motion.div className={className} variants={itemVariants}>
      {children}
    </motion.div>
  );
}
