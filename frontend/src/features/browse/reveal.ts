// Owner, 2026-11-23: nothing spawns in mid-animation. An image shows only once it is decoded, whole, in a box whose size
// was reserved before it arrived (the poster's 2:3, the hall view's width/height); it never paints in line by line.

/** A ref for an <img className="fr-reveal">: it fades in (app.css) once decoded. An image the browser already holds
 *  (a poster seen on the page before) shows at once, so a View Transition's snapshot already has it. */
export function reveal(img: HTMLImageElement | null): void {
  if (!img || img.dataset.shown !== undefined) return;
  const show = () => void (img.dataset.shown = "");
  if (img.complete && img.naturalWidth) return show();
  img.addEventListener("load", () => void img.decode().then(show, show), { once: true });
}

/** Settles when every image is decoded (or failed), or after `ms`, whichever is first: a wait with an exit
 *  (web-app-pitfalls 2). Decoded images stay in the browser's memory cache, so the page that shows them next has them. */
export function decoded(srcs: string[], ms: number): Promise<void> {
  const all = Promise.all(srcs.map((src) => {
    const img = new Image();
    img.src = src;
    return img.decode().catch(() => null);
  }));
  return Promise.race([all.then(() => undefined), new Promise<void>((done) => setTimeout(done, ms))]);
}
