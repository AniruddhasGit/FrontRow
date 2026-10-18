// SCR-SEA-02 · the hold countdown (COMPONENTS.md §7, P-HLD-09). It takes the current instant as a REQUIRED prop and
// never reads a clock: the screen that renders it owns the ticking. The digits sit outside every live region; only
// the warning or zero line is announced, once, through the polite region below them.
import { TIME_LEFT, countdown, countdownLine } from "./hold";

export function HoldCountdown({ expiresAt, now, confirmInFlight, totalMs }: {
  expiresAt: string; now: number; confirmInFlight: boolean; totalMs: number;
}) {
  const c = countdown(expiresAt, now); // throws without `now`: there is no default instant to fall back on
  const line = countdownLine(c, confirmInFlight);
  const share = totalMs > 0 ? Math.min(1, c.remainingMs / totalMs) : 0;
  return (
    <div className="fr-countdown" data-urgent={c.urgent || c.ended ? "" : undefined}>
      <span className="fr-countdown-label">{TIME_LEFT}</span>
      <span className="fr-countdown-digits">{c.text}</span>
      <span className="fr-countdown-track" aria-hidden="true">
        <span className="fr-countdown-bar" style={{ width: `${share * 100}%` }} />
      </span>
      <p className="fr-countdown-line" aria-live="polite">{line ?? ""}</p>
    </div>
  );
}
