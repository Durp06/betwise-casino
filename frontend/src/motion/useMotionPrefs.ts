/**
 * useMotionPrefs — single boolean for "should we reduce motion?".
 *
 * Components read this to collapse fly/flip/transform variants to plain opacity.
 * MotionConfig reducedMotion="user" handles pure variant animations globally;
 * this gates the hand-authored sequences (deck fly, chip fly) that aren't variants.
 */
import { useReducedMotion } from "framer-motion";

export function useMotionPrefs(): boolean {
  return useReducedMotion() ?? false;
}
