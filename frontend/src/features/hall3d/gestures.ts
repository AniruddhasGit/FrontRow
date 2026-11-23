// The 3D hall's seat gestures (owner, 2026-11-23): one click takes you to the seat's view and chooses nothing; a double
// click chooses the seat (it turns blue) and the camera stays where it is; a right click takes a chosen seat back out.
// Pure, so node --test loads it. A click waits DOUBLE_MS before it acts, so a double click never also flies the camera.

export type SeatGesture = "click" | "double" | "right";
export type SeatAction = "look" | "choose" | "unchoose" | "none";
export const DOUBLE_MS = 260;

/** `visual` is the seat as you see it (seatmap/model.ts visualOf); `open` is the 2D map's selectable() for it. */
export function seatAction(g: SeatGesture, visual: string, open: boolean): SeatAction {
  if (g === "click") return "look"; // any seat, choosable or not, can be looked from
  if (g === "double") return open && visual === "available" ? "choose" : "none"; // choosing twice never un-chooses
  return visual === "held_by_me" ? "unchoose" : "none";
}
