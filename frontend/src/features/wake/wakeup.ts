// SRC-008 WAIT-1: the cold-start screen. Pure: no React, no three.js, no runtime import, so node --test loads it.
import type { SeatMap } from "../seatmap/model";
import type { BakedMeta } from "../hall3d/hall";

export const WAKE_HALL = 6; // "Hall 6 Grand" (WAIT-1). Its /halls/hall6.* bake is not shipped yet: the plain screen shows.
export const WAKE_SECONDS = 90;
export const SHOW_AFTER_MS = 1500; // an awake API answers well inside this, so the screen never flashes
export const GIVE_UP_MS = 180_000; // web-app-pitfalls 2: a ceiling, after which the app loads and shows its own errors

/** The pause before the next readiness check: 1.5 s, growing by half each time, never over 8 s. */
export function retryDelay(attempt: number): number {
  return Math.min(1500 * 1.5 ** attempt, 8000);
}

/** What the screen says, `elapsedMs` after the page opened. At zero it says so, rather than counting a lie. */
export function screenLines(elapsedMs: number): { clock: string; title: string; body: string; done: number } {
  const left = Math.max(0, WAKE_SECONDS - Math.floor(elapsedMs / 1000));
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  return left > 0
    ? { clock, done: 1 - left / WAKE_SECONDS, title: "Waking up the box office",
        body: "Our free server sleeps when nobody is visiting. It takes about a minute to start." }
    : { clock, done: 1, title: "Still starting — almost there",
        body: "The server is taking a little longer than usual. The site opens by itself the moment it answers." };
}

const CATEGORY: Record<string, string> = { S: "Standard", P: "Premium", R: "Recliner" };

/** A seat map for the baked hall alone: every seat free, named by its baked category. No prices: the client does no
 *  money arithmetic (FR-ADR-038) and the server that knows them is the one asleep. Nothing here can be booked. */
export function bakedSeatMap(meta: BakedMeta): SeatMap {
  const codes = [...new Set(meta.seats.map((s) => s.cat))];
  const rows = [...new Set(meta.seats.map((s) => s.row))];
  return {
    showtime: { id: 0, starts_at: "", sales_close_at: "", sales_closed: false },
    screen: { id: 0, name: `SCREEN ${meta.hall}`, rows: rows.length, cols: Math.max(...meta.seats.map((s) => s.num)) },
    categories: codes.map((c, i) => ({ id: i + 1, name: CATEGORY[c] ?? "Standard", price_paise: 0 })),
    seats: meta.seats.map((s, i) => ({
      id: i + 1, row: s.row, num: s.num, gr: rows.indexOf(s.row), gc: s.num, cat: codes.indexOf(s.cat) + 1,
      price_paise: 0, state: "available", is_active: true,
    })),
    generated_at: "", poll_interval_seconds: 60,
  };
}

export interface Ink { ground: string; glow: string; strong: string; muted: string; cyan: string; fill: string; rule: string }

function wrap(g: CanvasRenderingContext2D, text: string, max: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(" ")) {
    const next = line ? `${line} ${word}` : word;
    if (line && g.measureText(next).width > max) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  return [...lines, line];
}

/** The picture on the cinema screen: the reason, the clock and a thin progress line, in the half-light palette. */
export function paintScreen(g: CanvasRenderingContext2D, w: number, h: number, elapsedMs: number, ink: Ink): void {
  const { clock, title, body, done } = screenLines(elapsedMs);
  const bg = g.createRadialGradient(w / 2, h * 0.42, h * 0.05, w / 2, h / 2, w * 0.62);
  bg.addColorStop(0, ink.glow);
  bg.addColorStop(1, ink.ground);
  g.fillStyle = bg;
  g.fillRect(0, 0, w, h);
  g.textAlign = "center";
  g.textBaseline = "middle";
  const u = Math.min(h, w / 2.39); // the type scales with the picture's short side
  g.font = `400 ${u * 0.04}px "JetBrains Mono", monospace`;
  g.fillStyle = ink.cyan;
  g.fillText("F R O N T R O W   ·   B O X   O F F I C E", w / 2, h * 0.16);
  let size = u * 0.1;
  do g.font = `700 ${size}px "Inter Tight", system-ui, sans-serif`;
  while (g.measureText(title).width > w * 0.86 && (size *= 0.92) > u * 0.04);
  g.fillStyle = ink.strong;
  g.fillText(title, w / 2, h * 0.3);
  g.font = `800 ${u * 0.3}px "Inter Tight", system-ui, sans-serif`;
  g.shadowColor = ink.cyan;
  g.shadowBlur = u * 0.06;
  g.fillText(clock, w / 2, h * 0.53);
  g.shadowBlur = 0;
  const barW = w * 0.36;
  const barY = h * 0.7;
  g.fillStyle = ink.rule;
  g.fillRect((w - barW) / 2, barY, barW, Math.max(2, u * 0.006));
  g.fillStyle = ink.fill;
  g.fillRect((w - barW) / 2, barY, barW * done, Math.max(2, u * 0.006));
  g.font = `400 ${u * 0.045}px "Inter Tight", system-ui, sans-serif`;
  g.fillStyle = ink.muted;
  wrap(g, body, w * 0.62).forEach((line, i) => g.fillText(line, w / 2, h * 0.79 + i * u * 0.065));
}
