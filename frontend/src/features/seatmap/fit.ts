// CR-008 T16 (owner, 2026-11-22: "no horizontal scroll through out the entire app"): the 2D seat map fits its panel.
// The cells are sized from the box's width (a ResizeObserver, no timer). When even that would make a seat too small to
// tap, the map shows the whole hall as an overview and the viewer taps a block (the seats between two aisles, split
// further if still too wide) to zoom into it at a tappable size - instead of scrolling sideways. Pure: tested alone.

export const GUTTER = 28; // --fr-seat-gutter: the row label column
export const MAX_CELL = 32;
/** The smallest seat a pointer may aim at: 24 px is WCAG 2.2 2.5.8's target for touch; a mouse can aim at less. */
export const MIN_TOUCH = 22;
export const MIN_POINTER = 10; // desktop: the panel beside the 3D hall (where seats can be chosen too) is ~360 px wide

/** The cell and gap that make `cols` seat columns plus the gutter fit `width`. */
export function cellFor(width: number, cols: number): { cell: number; gap: number } {
  const at = (gap: number) => Math.floor((width - GUTTER - gap * cols) / Math.max(1, cols));
  const wide = at(4);
  if (wide >= 20) return { cell: Math.min(MAX_CELL, wide), gap: 4 };
  return { cell: Math.max(4, at(2)), gap: 2 };
}

export type Part = { from: number; to: number }; // grid columns, inclusive

/** The hall's blocks: runs of used columns split where two or more columns are empty (an aisle); a block wider than
 *  `maxCols` is cut into equal pieces that each fit. */
export function parts(columns: number[], maxCols: number): Part[] {
  const used = [...new Set(columns)].sort((a, b) => a - b);
  const runs: Part[] = [];
  for (const c of used) {
    const last = runs[runs.length - 1];
    if (last && c - last.to <= 2) last.to = c;
    else runs.push({ from: c, to: c });
  }
  return runs.flatMap((r) => {
    const span = r.to - r.from + 1;
    const n = Math.ceil(span / Math.max(1, maxCols));
    const size = Math.ceil(span / n);
    return Array.from({ length: n }, (_, i) => ({ from: r.from + i * size, to: Math.min(r.to, r.from + (i + 1) * size - 1) }));
  });
}

/** How many columns fit at a tappable size. */
export function fitsCols(width: number, min: number): number {
  return Math.max(1, Math.floor((width - GUTTER) / (min + 4)));
}

export type Fit =
  | { kind: "full"; cell: number | null; gap: number | null } // null: not measured yet (the CSS defaults apply)
  | { kind: "overview"; cell: number; gap: number; parts: Part[] }
  | { kind: "zoomed"; cell: number; gap: number; parts: Part[]; part: number };

/** The map's one layout status, from the box width, the grid's columns, the pointer and the chosen block. */
export function layout(width: number, columns: number[], cols: number, coarse: boolean, zoom: number | null): Fit {
  if (width <= 0) return { kind: "full", cell: null, gap: null };
  const min = coarse ? MIN_TOUCH : MIN_POINTER;
  const all = cellFor(width, cols);
  if (all.cell >= min) return { kind: "full", ...all };
  const list = parts(columns, fitsCols(width, min));
  if (zoom === null || zoom >= list.length) return { kind: "overview", ...all, parts: list };
  const p = list[zoom];
  return { kind: "zoomed", ...cellFor(width, p.to - p.from + 1), parts: list, part: zoom };
}

/** The block's everyday name: Left / Centre / Right for three, else "Block 2 of 4". */
export function partName(i: number, n: number): string {
  if (n === 2) return ["Left block", "Right block"][i];
  if (n === 3) return ["Left block", "Centre block", "Right block"][i];
  return `Block ${i + 1} of ${n}`;
}
