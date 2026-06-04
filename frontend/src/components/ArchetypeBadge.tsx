/**
 * ArchetypeBadge.tsx — small pill showing a bot's archetype name, with a
 * play-style tooltip on hover/focus.
 *
 * In the solo poker trainer each opponent is a named archetype. Hovering (or
 * keyboard-focusing) the badge reveals an accessible tooltip describing how
 * that player plays, how to exploit them, and where they sit on the two
 * classic poker axes — Tight↔Loose and Passive↔Aggressive. Copy + axis data
 * live in frontend/src/data/archetypes.ts (single source of truth).
 *
 * Implemented as a real React tooltip rather than the native `title` attribute
 * so it appears instantly, matches the BetWise ink aesthetic, and is reachable
 * by keyboard (WAI-ARIA tooltip pattern: focusable trigger + aria-describedby).
 *
 * The tooltip is rendered in a portal on document.body with fixed positioning
 * that flips above/below the badge and clamps to the viewport. That keeps it
 * from being clipped by a top-row seat or by SeatMotion's framer-motion
 * transform (a transformed ancestor would otherwise capture `position: fixed`).
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getArchetypeMeta } from "../data/archetypes";
import { t } from "../i18n";

interface ArchetypeBadgeProps {
  archetypeName: string | null;
  isBot: boolean;
}

const TIGHT_AGG = "bg-red-100 text-red-900 border-red-700";
const LOOSE_AGG = "bg-orange-100 text-orange-900 border-orange-700";
const TIGHT_PASS = "bg-blue-100 text-blue-900 border-blue-700";
const LOOSE_PASS = "bg-green-100 text-green-900 border-green-700";
const BALANCED = "bg-purple-100 text-purple-900 border-purple-700";
const HUMAN = "bg-cream text-ink border-ink";

const ARCHETYPE_COLOR: Record<string, string> = {
  TAG: TIGHT_AGG,
  ABC: TIGHT_AGG,
  Nit: TIGHT_PASS,
  SetMiner: TIGHT_PASS,
  Trapper: TIGHT_PASS,
  LAG: LOOSE_AGG,
  Maniac: LOOSE_AGG,
  CallingStation: LOOSE_PASS,
  Whale: LOOSE_PASS,
  TAGFish: LOOSE_PASS,
  Shark: BALANCED,
};

const PILL_BASE =
  "px-2 py-0.5 text-[10px] uppercase tracking-widest rounded-full border-2 font-ui";

const TOOLTIP_WIDTH = 240; // matches w-60
const TOOLTIP_EST_HEIGHT = 190; // worst-case height used only for the flip decision
const GAP = 8;

interface TipPos {
  top: number;
  left: number;
  placement: "top" | "bottom";
  /** Height budget for the chosen side, so the tooltip never paints off-screen. */
  maxHeight: number;
}

/** One labelled meter, e.g. Tight ▱▰▰ Loose. Fill width is a dynamic value. */
function AxisMeter({
  leftLabel,
  rightLabel,
  value,
}: {
  leftLabel: string;
  rightLabel: string;
  value: number;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-ui uppercase text-[8px] tracking-wider text-ink/60 w-14 text-right shrink-0">
        {t(leftLabel)}
      </span>
      <div
        className="relative h-1.5 flex-1 rounded-full bg-ink/15"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={`${t(leftLabel)} to ${t(rightLabel)}`}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-ink/70"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-ui uppercase text-[8px] tracking-wider text-ink/60 w-14 shrink-0">
        {t(rightLabel)}
      </span>
    </div>
  );
}

export default function ArchetypeBadge({ archetypeName, isBot }: ArchetypeBadgeProps) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<TipPos>({ top: 0, left: 0, placement: "top", maxHeight: 0 });
  const tooltipId = useId();

  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const spaceAbove = r.top - GAP;
    const spaceBelow = vh - r.bottom - GAP;
    // Default to above; flip below only when there isn't room above and below
    // genuinely has more room. Then cap the height to the space on the chosen
    // side so the tooltip can never paint off the top OR bottom of the viewport
    // (the bug a short / mobile viewport would otherwise hit).
    const placeBelow = spaceAbove < TOOLTIP_EST_HEIGHT && spaceBelow > spaceAbove;
    const maxHeight = Math.max(0, placeBelow ? spaceBelow : spaceAbove);
    const top = placeBelow ? r.bottom + GAP : r.top - GAP;
    const half = TOOLTIP_WIDTH / 2;
    const centerX = r.left + r.width / 2;
    const left = Math.max(half + GAP, Math.min(centerX, vw - half - GAP));
    setPos({ top, left, placement: placeBelow ? "bottom" : "top", maxHeight });
  }, []);

  const show = useCallback(() => {
    updatePosition();
    setOpen(true);
  }, [updatePosition]);
  const hide = useCallback(() => setOpen(false), []);

  // Keep the tooltip glued to the badge if the table scrolls or resizes.
  useEffect(() => {
    if (!open) return;
    const onChange = () => updatePosition();
    window.addEventListener("scroll", onChange, true);
    window.addEventListener("resize", onChange);
    return () => {
      window.removeEventListener("scroll", onChange, true);
      window.removeEventListener("resize", onChange);
    };
  }, [open, updatePosition]);

  if (!isBot) {
    return (
      <span className={`${PILL_BASE} ${HUMAN}`} data-testid="archetype-badge-human">
        {t("You")}
      </span>
    );
  }
  if (!archetypeName) return null;

  const color = ARCHETYPE_COLOR[archetypeName] ?? "bg-gray-100 text-gray-900 border-gray-700";
  const meta = getArchetypeMeta(archetypeName);

  // Unknown archetype (not in the registry): render the bare pill, no tooltip.
  if (!meta) {
    return (
      <span className={`${PILL_BASE} ${color}`} data-testid={`archetype-badge-${archetypeName}`}>
        {t(archetypeName)}
      </span>
    );
  }

  return (
    <>
      <span
        ref={triggerRef}
        className={`${PILL_BASE} ${color} cursor-help outline-none focus-visible:ring-2 focus-visible:ring-ink/50`}
        data-testid={`archetype-badge-${archetypeName}`}
        tabIndex={0}
        aria-describedby={open ? tooltipId : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={(e) => {
          if (e.key === "Escape") hide();
        }}
      >
        {t(archetypeName)}
      </span>

      {open &&
        createPortal(
          <div
            role="tooltip"
            id={tooltipId}
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              maxHeight: pos.maxHeight,
              transform:
                pos.placement === "bottom" ? "translateX(-50%)" : "translate(-50%, -100%)",
            }}
            className="z-50 w-60 max-w-[min(15rem,92vw)] overflow-y-auto rounded-lg border-2 border-ink bg-cream text-ink p-3 text-left normal-case tracking-normal pointer-events-none shadow-[3px_3px_0_0_#1A0A00]"
          >
            {/* Header: name · animal */}
            <div className="flex items-baseline gap-1.5">
              <span className="font-ui font-bold text-sm leading-none">{t(meta.name)}</span>
              {meta.animal && (
                <span className="text-[9px] uppercase tracking-wider text-ink/50 leading-none">
                  {t(meta.animal)}
                </span>
              )}
            </div>
            <div className="text-[11px] italic text-ink/70 mt-0.5">{t(meta.tagline)}</div>

            {/* How they play */}
            <p className="mt-2 text-[11px] leading-snug">{t(meta.style)}</p>

            {/* Teaching axes: Tight↔Loose × Passive↔Aggressive */}
            <div data-testid="archetype-axes" className="mt-2 flex flex-col gap-1">
              <AxisMeter leftLabel="Tight" rightLabel="Loose" value={meta.looseness} />
              <AxisMeter leftLabel="Passive" rightLabel="Aggressive" value={meta.aggression} />
            </div>

            {/* How to exploit */}
            <p className="mt-2 text-[11px] leading-snug">
              <span className="font-ui font-bold uppercase text-[9px] tracking-wider text-action-hit">
                {t("Exploit")}
              </span>{" "}
              <span>{t(meta.exploit)}</span>
            </p>
          </div>,
          document.body,
        )}
    </>
  );
}
