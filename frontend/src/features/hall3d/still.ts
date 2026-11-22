// CR-006: a demo film's poster redirects to /art/films/<slug>.webp, and its screen still sits beside it as
// <slug>-still.webp. Found with a GET (the poster route has no HEAD: it answered 405, and the title card stayed) and
// retried, because one dropped request - an API waking on Render - used to leave the film off the screen for good.
// Pure: no three.js, no DOM, so node --test loads it.

type Fetcher = (url: string, init?: { method?: string }) => Promise<{ ok: boolean; url: string }>;

export async function stillPath(
  movieId: number, fetchFn: Fetcher,
  { tries = 3, wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms)) } = {},
): Promise<string | null> {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetchFn(`/api/movies/${movieId}/poster`, { method: "GET" }); // the poster is already cached by the cards
      if (r.ok) {
        const path = new URL(r.url, "http://x").pathname;
        return /^\/art\/films\/[a-z0-9-]+\.webp$/.test(path) ? path.replace(/\.webp$/, "-still.webp") : null;
      }
    } catch {
      // dropped: try again
    }
    if (i < tries - 1) await wait(1500 * (i + 1));
  }
  return null; // the title card stays: every wait has an exit
}
