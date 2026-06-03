/**
 * tableName.ts — friendly table name generator.
 *
 * AC P0-2c: returns a non-empty string that does NOT match /^Table \d+$/.
 *
 * Generates a two-word name from a curated adjective + noun list.
 * All strings flow through t() for future i18n compatibility.
 */

import { t } from "../i18n";

const ADJECTIVES: readonly string[] = [
  "Golden", "Silver", "Lucky", "Wild", "Royal",
  "Bold", "Crimson", "Jade", "Velvet", "Copper",
  "Rusty", "Dusty", "Sunny", "Misty", "Starry",
  "Amber", "Ivory", "Scarlet", "Azure", "Onyx",
];

const NOUNS: readonly string[] = [
  "Ace", "Crown", "Deal", "Felt", "Joker",
  "Chip", "Spade", "Heart", "Diamond", "Club",
  "Bluff", "Raise", "River", "Flop", "Stack",
  "Ante", "Pot", "Flush", "Straight", "Pair",
];

/**
 * Returns a friendly two-word table name, e.g. "Golden Ace" or "Velvet Flush".
 * Each word is passed through t() for future i18n hooks.
 */
export function generateTableName(): string {
  const adj = ADJECTIVES[Math.floor(Math.random() * ADJECTIVES.length)];
  const noun = NOUNS[Math.floor(Math.random() * NOUNS.length)];
  return `${t(adj)} ${t(noun)}`;
}

export default generateTableName;
