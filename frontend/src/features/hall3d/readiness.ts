// Owner, 2026-11-23: "if the hall is not loaded yet properly we should not start the animation ... make sure that each
// component of the hall is loaded before we show the page". One status for a hall's load (web-app-pitfalls 3), from
// the state of each of its parts (the room .glb, the seat models, the reflection panorama, the screen's still) and the
// time since the hall started loading. Pure: node --test loads it.
//
// Every wait has an exit (web-app-pitfalls 2): past HALL_CAP_MS the hall stops waiting. An optional part still out (the
// panorama, the still) is dropped and the hall shows with its defaults ("capped"); a required part still out (the room)
// sends the page to its fallback ("failed"), as a required part that errors does at once.
// Why 9 s: the largest room file is 11 MB (hall6.glb), about 9 s at 10 Mbit/s; the still's lookup gives up after its
// third try at ~4.5 s of waiting (still.ts); and a box still empty after ~9 s reads as broken. The seat page's 2D map is
// usable the whole time, and the router never holds a page change longer than 3 s (hallReady.ts).

export type PartState = "loading" | "loaded" | "failed";
export type Parts = Record<string, PartState>;
export type HallStatus = "loading" | "ready" | "capped" | "failed";

export const HALL_CAP_MS = 9000;

export function readiness(parts: Parts, elapsedMs: number, required: readonly string[] = [], capMs = HALL_CAP_MS): HallStatus {
  if (required.some((k) => parts[k] === "failed")) return "failed";
  if (Object.values(parts).every((s) => s !== "loading")) return "ready";
  if (elapsedMs < capMs) return "loading";
  return required.every((k) => parts[k] === "loaded") ? "capped" : "failed";
}

/** The status says the hall may be drawn: everything is in, or the cap dropped what is not. */
export const settled = (s: HallStatus) => s === "ready" || s === "capped";
