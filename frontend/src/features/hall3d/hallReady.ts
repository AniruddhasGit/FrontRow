// CR-005: one flow from the landing into the seat page. The router holds the old page's last frame on screen (a View
// Transition) until the new page's hall has drawn its first frame, so the room never flashes empty between them.
let release: (() => void) | null = null;

/** A promise that settles when the next hall draws, or after `ms`, whichever is first. */
export function nextHallDrawn(ms = 3000): Promise<void> {
  return new Promise((done) => {
    release = done;
    setTimeout(done, ms);
  });
}

export function hallDrawn(): void {
  release?.();
  release = null;
}
