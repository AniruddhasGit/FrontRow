// The showcase hall's film change (owner, 2026-11-23: "the movies can just change by flicker changing the projector
// animation and the movies screen lights up"): the screen goes dark, the projector lamp stutters on, then the picture
// rises to full. Seconds since the change -> brightness 0..1 for the screen and the beam. Pure, so node --test loads it.

export const FLICKER_S = 1.0;
// [from second, level]: dark, three stutters, then a rise from 0.8 to full by FLICKER_S
const STEPS: [number, number][] = [[0, 0.04], [0.2, 0.85], [0.26, 0.15], [0.34, 0.7], [0.4, 0.2], [0.48, 0.8]];

export function flickerLevel(t: number): number {
  if (!(t >= 0) || t >= FLICKER_S) return 1;
  const last = STEPS[STEPS.length - 1];
  if (t >= last[0]) return last[1] + (1 - last[1]) * ((t - last[0]) / (FLICKER_S - last[0]));
  let level = STEPS[0][1];
  for (const [from, v] of STEPS) if (t >= from) level = v;
  return level;
}
