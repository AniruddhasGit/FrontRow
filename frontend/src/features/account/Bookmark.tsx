// CR-008 T4: the bookmark toggle on film cards, the landing and the film page, and the one saved-set read per page.
// A guest's press remembers the film (fr.pending_bookmark) and goes to sign-in; Shell applies it once signed in.
import { useCallback, useEffect, useReducer } from "react";
import { navigate } from "../../router";
import { get, send } from "../browse/api";
import { rememberBookmark, savedReducer, type Saved } from "./account";

const WAIT = () => AbortSignal.timeout(15000); // a read that never answers ends as "error" (web-app-pitfalls rule 2)

/** The page's saved set: read once on mount (no polling), then changed only by this page's own presses. */
export function useSaved(): [Saved, (movieId: number, saved: boolean) => void] {
  const [state, dispatch] = useReducer(savedReducer, { kind: "loading" } as Saved);
  useEffect(() => {
    let live = true;
    const read = () => get<{ items: { movie_id: number }[] }>("/api/me/bookmarks", WAIT()).then((r) => {
      if (!live) return;
      if (r.ok) dispatch({ type: "loaded", ids: r.body.items.map((i) => i.movie_id) });
      else dispatch(r.status === 401 ? { type: "guest" } : { type: "error" });
    });
    void read();
    // Shell applies a guest's remembered Save after sign-in and says so once; read again then (an event, not a timer).
    const again = () => void read();
    window.addEventListener("fr:bookmarks-changed", again);
    return () => {
      live = false;
      window.removeEventListener("fr:bookmarks-changed", again);
    };
  }, []);
  const toggle = useCallback((movieId: number, saved: boolean) => {
    dispatch({ type: "press", id: movieId });
    void send<{ saved: boolean }>("PUT", `/api/me/bookmarks/${movieId}`, { saved }).then((r) =>
      dispatch(r.ok ? { type: "answered", id: movieId, saved: r.body.saved } : { type: "refused", id: movieId }));
  }, []);
  return [state, toggle];
}

export function signInToSave(movieId: number): void {
  try {
    rememberBookmark(window.sessionStorage, movieId);
  } catch {
    // no storage: they press Save again after signing in
  }
  navigate(`/sign-in?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
}

/** One film's toggle. While the saved set is loading or failed to load the control is shown but inert. */
export function BookmarkToggle({ movieId, title, state, toggle }: {
  movieId: number; title: string; state: Saved; toggle: (movieId: number, saved: boolean) => void;
}) {
  const saved = state.kind === "ready" && state.ids.includes(movieId);
  const busy = state.kind === "loading" || (state.kind === "ready" && state.pending.includes(movieId));
  const failed = state.kind === "ready" && state.failed === movieId;
  const onClick = () => {
    if (state.kind === "guest") return signInToSave(movieId);
    if (state.kind === "ready" && !busy) toggle(movieId, !saved);
  };
  // The name stays "Save <title>" in both states; aria-pressed carries saved / not saved (a toggle button's pattern).
  return (
    <span className="fr-bookmark-wrap">
      <button type="button" className="fr-bookmark" aria-pressed={saved} aria-busy={busy || undefined}
              disabled={state.kind === "error"} title={state.kind === "error" ? "Saved films cannot be loaded right now" : undefined}
              aria-label={`Save ${title}`} onClick={onClick}>
        <span aria-hidden="true">{saved ? "★" : "☆"}</span> <span className="fr-bookmark-text">Save</span>
      </button>
      <span role="status" className="fr-bookmark-note">{failed ? "Not saved. Try again." : ""}</span>
    </span>
  );
}
