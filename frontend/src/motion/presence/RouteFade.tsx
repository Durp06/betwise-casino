/**
 * RouteFade — crossfades page content on route changes so navigation doesn't
 * hard-cut. The consumer passes the current pathname (used as the AnimatePresence
 * key) and the route output as children; `mode="wait"` sequences the outgoing
 * page's fade-out before the incoming page's fade-in, so no absolute positioning
 * is needed. Reduced motion keeps the opacity fade but drops the slide.
 */
import { AnimatePresence, motion } from "framer-motion";
import { ROUTE_FADE } from "../tokens";

interface RouteFadeProps {
  pathname: string;
  children: React.ReactNode;
}

export default function RouteFade({ pathname, children }: RouteFadeProps) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={ROUTE_FADE}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
