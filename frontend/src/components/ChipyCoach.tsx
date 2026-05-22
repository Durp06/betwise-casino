/**
 * ChipyCoach.tsx — always-visible coaching side panel.
 *
 * Unlike the older ChipyPanel (a button-driven quiz modal), this panel is
 * always rendered next to the felt and just reflects whatever the gameStore
 * is currently streaming. The proactive triggers live in:
 *
 *   - Table.tsx (pre-play: fires streamPreAdvice when myHand becomes active,
 *               or sets the drill-mode quiz prompt)
 *   - ActionBar.tsx (post-play: fires streamAdvice with the action taken)
 *
 * Markdown stripping: the system prompt tells Chipy to write plain prose, but
 * LLMs sometimes ignore that. stripMarkdown() defensively removes ## / ** /
 * * / ` / leading list markers from the rendered text so users never see
 * literal asterisks on the page.
 *
 * Quick/Drill toggle: pill buttons in the header let the player pick their
 * coaching style. "Quick" = current behavior (Chipy reveals before you act).
 * "Drill" = Chipy holds back the recommendation and surfaces a static quiz
 * prompt instead; post-play stream still fires with the answer.
 */
import { useGameStore } from "../store/gameStore";
import Chipy from "./Chipy";
import type { ChipyExpression, ChipyAnimation, ChipyPose } from "./Chipy";
import { t } from "../i18n";

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__([^_]+?)__/g, "$1")
    .replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "$1")
    .replace(/`([^`]+?)`/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "");
}

export default function ChipyCoach() {
  const {
    chipyText,
    chipyStreaming,
    chipyPhase,
    coachMode,
    setCoachMode,
    chipyDrillPrompt,
  } = useGameStore();
  const text = stripMarkdown(chipyText);

  let expression: ChipyExpression = "idle";
  let animation: ChipyAnimation = "idle";
  let pose: ChipyPose = "rest";
  let banner = t("Watchin' the table");

  if (chipyStreaming) {
    expression = "thinking";
    animation = "think";
    pose = "rest";
    banner = chipyPhase === "pre" ? t("Sizin' it up…") : t("Callin' the play…");
  } else if (chipyPhase === "pre") {
    expression = "idle";
    animation = "idle";
    pose = "point";
    banner = t("Your move");
  } else if (chipyPhase === "post") {
    expression = "happy";
    animation = "bounce";
    pose = "thumbsup";
    banner = t("Last hand");
  }

  // In drill mode, when nothing is streaming, show the static quiz prompt
  // instead of (empty) narration text. Falls back to chipyText if Chipy is
  // (or just was) talking — so the post-play reveal still renders normally.
  const isDrill = coachMode === "drill";
  const bodyText =
    isDrill && !text && chipyDrillPrompt ? chipyDrillPrompt : text;

  const toggleBase =
    "px-3 py-1 rounded-full font-ui text-[10px] uppercase tracking-widest " +
    "border-[2px] border-ink transition-colors disabled:opacity-40 " +
    "disabled:cursor-not-allowed";
  const toggleActive = "bg-ink text-cream";
  const toggleInactive = "bg-cream text-ink hover:bg-gold-bright";

  return (
    <aside
      className="ink-outline-thick rounded-xl flex flex-col w-full lg:w-72 xl:w-80 self-start"
      style={{ backgroundColor: "#1A0A00", boxShadow: "6px 6px 0 0 #1A0A00" }}
      aria-live="polite"
      aria-busy={chipyStreaming}
    >
      <header
        className="flex items-center gap-3 px-3 py-2 border-b-[3px] border-ink"
        style={{ backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={56} expression={expression} animation={animation} pose={pose} />
        <div className="flex flex-col leading-tight flex-1 min-w-0">
          <h2 className="font-display text-ink text-xl tracking-wider leading-none">
            CHIPY
          </h2>
          <span className="font-flavor text-ink/80 text-xs italic truncate">
            {banner}
          </span>
        </div>
        <div
          role="group"
          aria-label={t("Coach mode")}
          className="flex gap-1"
        >
          <button
            type="button"
            onClick={() => setCoachMode("quick")}
            disabled={chipyStreaming}
            aria-pressed={coachMode === "quick"}
            className={`${toggleBase} ${coachMode === "quick" ? toggleActive : toggleInactive}`}
          >
            {t("Quick")}
          </button>
          <button
            type="button"
            onClick={() => setCoachMode("drill")}
            disabled={chipyStreaming}
            aria-pressed={coachMode === "drill"}
            className={`${toggleBase} ${coachMode === "drill" ? toggleActive : toggleInactive}`}
          >
            {t("Drill")}
          </button>
        </div>
      </header>
      <div
        className="paper-grain p-3 min-h-[120px] flex items-start"
        style={{ backgroundColor: "#F5F0E8" }}
      >
        {bodyText ? (
          <p className="font-body text-ink text-sm leading-relaxed whitespace-pre-line">
            {bodyText}
          </p>
        ) : (
          <p className="font-flavor text-ink/60 text-sm italic">
            {t("Howdy. I'll chime in when there's a play to make.")}
          </p>
        )}
      </div>
    </aside>
  );
}
