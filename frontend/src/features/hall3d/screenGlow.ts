// What the cinema screen casts into the room (owner, 2026-11-22: "if there is something bright on the screen the
// whole theatre colors do change ... I want the light to make sense and feel real"). Pure: no three.js, no DOM, so
// node --test loads it. HallScene samples the screen picture into a small RGBA grid and hands it here.

export interface Glow {
  /** the average colour of the picture's left and right halves, 0..1 (as seen from the seats) */
  left: [number, number, number];
  right: [number, number, number];
  /** how bright the picture is overall, 0..1 (Rec. 709 luma of the average) */
  luma: number;
}

/** The room before any picture: a dim, cool projector white. */
export const NO_GLOW: Glow = { left: [0.22, 0.26, 0.32], right: [0.22, 0.26, 0.32], luma: 0.25 };

/** Averages an RGBA pixel grid (w × h, row-major, 0..255) into the two halves and the overall brightness. */
export function glowOf(rgba: ArrayLike<number>, w: number, h: number): Glow {
  const sum = [[0, 0, 0], [0, 0, 0]];
  const n = [0, 0];
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = 4 * (y * w + x);
      const side = x < w / 2 ? 0 : 1;
      for (let c = 0; c < 3; c++) sum[side][c] += rgba[i + c] / 255;
      n[side]++;
    }
  }
  const left = sum[0].map((v) => v / Math.max(1, n[0])) as Glow["left"];
  const right = sum[1].map((v) => v / Math.max(1, n[1])) as Glow["right"];
  const avg = left.map((v, c) => (v + right[c]) / 2);
  return { left, right, luma: 0.2126 * avg[0] + 0.7152 * avg[1] + 0.0722 * avg[2] };
}
