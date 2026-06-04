/**
 * motion/tokens.ts — the shared motion vocabulary.
 *
 * One place that defines the spring/timing feel so every surface (blackjack,
 * poker, hold'em, pai gow, site UI) animates identically. Mirrors the legacy
 * CSS timings (380ms card-deal, 420ms card-3d flip, 110ms deal-stagger).
 */
import type { Transition } from "framer-motion";

/** Card deal / general element entrance — rubber-hose bounce. */
export const DEAL_SPRING: Transition = { type: "spring", stiffness: 520, damping: 34, mass: 0.9 };

/** 3D flip on reveal (dealer hole card, community streets, showdown). */
export const FLIP_TRANSITION: Transition = { duration: 0.42, ease: "easeInOut" };

/** Small pop-in for badges / values. */
export const POP_IN: Transition = { type: "spring", stiffness: 600, damping: 26 };

/** Chips arcing from a seat to the pot. */
export const CHIP_FLY: Transition = { duration: 0.6, ease: "easeInOut" };

/** Transient action badge pop. */
export const BADGE_POP: Transition = { duration: 0.22, ease: "easeOut" };

/** Per-item stagger step (seconds) — matches the legacy 110ms deal-stagger. */
export const STAGGER_STEP = 0.11;

// ── Site-wide presence (P7): modals, route changes, lists, banners ──────────

/** Route crossfade — fast so navigation feels instant, not sluggish. */
export const ROUTE_FADE: Transition = { duration: 0.18, ease: "easeOut" };

/** Modal backdrop fade. */
export const BACKDROP_FADE: Transition = { duration: 0.16, ease: "easeOut" };

/** Modal panel pop (scale + slide). */
export const MODAL_POP: Transition = { type: "spring", stiffness: 460, damping: 32, mass: 0.8 };

/** Generic enter for banners / chat messages / outcome reveals. */
export const FADE_SLIDE: Transition = { duration: 0.24, ease: "easeOut" };
