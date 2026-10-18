// A row of single-choice buttons - the date strips (SCR-BRW-01, SCR-BRW-02) and the listing's reference-backed
// filters. ONE tab stop: arrow keys move between the choices (roving tabindex), Enter or Space chooses.
// Each button carries its own words; a day reads `Sat 15 Aug`, never `Today` (S7.19 rule 7).
import { useRef, type KeyboardEvent } from "react";
import { dayLabel } from "./logic";

export interface Choice {
  value: string | null;
  label: string;
}

export function ChoiceGroup({ label, choices, selected, onSelect, className = "fr-strip" }: {
  label: string; choices: Choice[]; selected: string | null; onSelect: (value: string | null) => void; className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = Math.max(0, choices.findIndex((c) => c.value === selected));
  const onKey = (e: KeyboardEvent, i: number) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    refs.current[(i + step + choices.length) % choices.length]?.focus();
  };
  return (
    <div role="group" aria-label={label} className={className}>
      {choices.map((c, i) => (
        <button
          key={c.value ?? ""}
          ref={(el) => { refs.current[i] = el; }}
          type="button"
          className="fr-choice"
          aria-pressed={c.value === selected}
          tabIndex={i === current ? 0 : -1}
          onKeyDown={(e) => onKey(e, i)}
          onClick={() => onSelect(c.value)}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

export function DayStrip({ label, days, selected, anyDate, onSelect }: {
  label: string; days: string[]; selected: string | null; anyDate?: boolean; onSelect: (day: string | null) => void;
}) {
  const choices: Choice[] = [...(anyDate ? [{ value: null, label: "Any date" }] : []), ...days.map((d) => ({ value: d, label: dayLabel(d) }))];
  return <ChoiceGroup label={label} choices={choices} selected={selected} onSelect={onSelect} />;
}
