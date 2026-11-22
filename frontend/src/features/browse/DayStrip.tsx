// A row of single-choice buttons - the date strips (SCR-BRW-01, SCR-BRW-02) and the listing's reference-backed
// filters. ONE tab stop: arrow keys move between the choices (roving tabindex), Enter or Space chooses.
// Each button carries its own words; a day reads `Sat 15 Aug`, never `Today` (S7.19 rule 7).
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { weekRows } from "../discover/discover";
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

/** CR-008 T16 (owner: no horizontal scroll anywhere): the dates as a wrapping week grid, 7 to a row - weekday over the
 *  day's number, the month's name where it starts or changes - and "Any date" as a chip above. Still ONE tab stop:
 *  left/right step a day, up/down a week. Each button's name stays `Sat 15 Aug` (S7.19). */
export function DayStrip({ label, days, selected, anyDate, onSelect }: {
  label: string; days: string[]; selected: string | null; anyDate?: boolean; onSelect: (day: string | null) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const choices: (string | null)[] = [...(anyDate ? [null] : []), ...days];
  const current = Math.max(0, choices.indexOf(selected));
  const offset = anyDate ? 1 : 0;
  const onKey = (e: KeyboardEvent, i: number) => {
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 7, ArrowUp: -7 }[e.key] ?? 0;
    if (!step) return;
    e.preventDefault();
    // from "Any date", down goes to the first day; a week's step past either end stops at the end
    const next = i < offset ? (step > 0 ? offset : choices.length - 1) : Math.min(choices.length - 1, Math.max(0, i + step));
    refs.current[next]?.focus();
  };
  const button = (value: string | null, i: number, body: ReactNode, name?: string) => (
    <button key={value ?? ""} ref={(el) => { refs.current[i] = el; }} type="button"
            className={value === null ? "fr-choice fr-day-any" : "fr-choice fr-day"} aria-pressed={value === selected}
            aria-label={name} tabIndex={i === current ? 0 : -1} onKeyDown={(e) => onKey(e, i)} onClick={() => onSelect(value)}>
      {body}
    </button>
  );
  return (
    <div role="group" aria-label={label} className="fr-days">
      {anyDate ? button(null, 0, "Any date") : null}
      {weekRows(days).map((week, w) => (
        <div key={week[0].day} className="fr-week">
          {week.map(({ day, month }, d) => {
            const [weekday, date] = dayLabel(day).split(" ");
            return button(day, offset + w * 7 + d, (
              <>
                <span className="fr-day-month" aria-hidden="true">{month ?? ""}</span>
                <span className="fr-day-weekday" aria-hidden="true">{weekday}</span>
                <span className="fr-day-date fr-mono" aria-hidden="true">{date}</span>
              </>
            ), dayLabel(day));
          })}
        </div>
      ))}
    </div>
  );
}
