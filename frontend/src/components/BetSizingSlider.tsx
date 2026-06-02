/**
 * BetSizingSlider.tsx — slider + preset fractions for bet sizing.
 *
 * Presets: ¼ pot, ½ pot, ¾ pot, pot, all-in.
 * Bounds: [minRaise, stack].
 */
import { useState } from "react";
import { t } from "../i18n";

interface BetSizingSliderProps {
  minRaise: number;
  maxRaise: number; // typically your stack
  potSize: number;
  initialValue: number;
  onChange: (amount: number) => void;
}

export default function BetSizingSlider({
  minRaise,
  maxRaise,
  potSize,
  initialValue,
  onChange,
}: BetSizingSliderProps) {
  const [value, setValue] = useState(initialValue);

  function setAndNotify(next: number): void {
    const clamped = Math.max(minRaise, Math.min(maxRaise, next));
    setValue(clamped);
    onChange(clamped);
  }

  const presets = [
    { label: "¼ pot", value: Math.round(potSize * 0.25) },
    { label: "½ pot", value: Math.round(potSize * 0.5) },
    { label: "¾ pot", value: Math.round(potSize * 0.75) },
    { label: t("pot"), value: potSize },
    { label: t("all-in"), value: maxRaise },
  ];

  return (
    <div className="flex flex-col gap-2" data-testid="bet-sizing-slider">
      <input
        type="range"
        min={minRaise}
        max={maxRaise}
        value={value}
        onChange={(e) => setAndNotify(Number(e.target.value))}
        className="w-full"
        aria-label={t("Bet size")}
      />
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono">{value}</span>
        <span className="text-ink/60">
          {t("min")} {minRaise} · {t("max")} {maxRaise}
        </span>
      </div>
      <div className="flex gap-1 flex-wrap">
        {presets.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => setAndNotify(p.value)}
            className="px-2 py-1 text-xs font-ui rounded border-2 border-ink bg-cream text-ink hover:bg-gold-bright"
            data-testid={`bet-preset-${p.label}`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
