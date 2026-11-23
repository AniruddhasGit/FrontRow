// CR-011 F4: the film page's reviews, newest or most helpful first, each with a Helpful vote (once per customer, never on
// your own: the server enforces both; the button only mirrors it). One status for the list (ReviewList) and one for a
// vote; no timer, no poll: the list is read on arrival, on a sort or band change, and once after the viewer posts a review.
// CR-013 (owner, 2026-11-23): the viewer's own rating sits on top (`children`), the reviews are one scrolling list with
// each score beside its comment, a star-band filter narrows it on the server, and the "Saw it at FrontRow" badge shows
// only where the server says it is true (`verified`).
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "../../router";
import { signInHref } from "../auth/session";
import { get, send } from "../browse/api";
import { ChoiceGroup } from "../browse/DayStrip";
import { dayLabel } from "../browse/logic";
import { REVIEW_BANDS, bandLabel, bandRange, initials, type BandCounts, type Review, type ReviewBand, type ReviewList,
         type ReviewSort } from "./discover";

type Vote = { kind: "idle" } | { kind: "voting"; id: number } | { kind: "failed"; message: string };

export function Reviews({ filmId, version, me, signedIn, children }: {
  filmId: number; version: number; me: { review_id: number | null; voted: number[] } | null; signedIn: boolean;
  children: ReactNode;
}) {
  const [sort, setSort] = useState<ReviewSort>("newest");
  const [band, setBand] = useState<ReviewBand | null>(null);
  const [bands, setBands] = useState<BandCounts | null>(null); // every band's count, kept while a new band loads
  const [list, setList] = useState<ReviewList>({ kind: "loading" });
  const [vote, setVote] = useState<Vote>({ kind: "idle" });
  const [voted, setVoted] = useState<Set<number>>(new Set());
  useEffect(() => setVoted(new Set(me?.voted ?? [])), [me?.voted]);
  useEffect(() => {
    const ctl = new AbortController();
    setList({ kind: "loading" });
    const q = `sort=${sort}${band ? `&band=${band}` : ""}`;
    void get<{ count: number; bands: BandCounts; items: Review[] }>(`/api/movies/${filmId}/reviews?${q}`,
      AbortSignal.any([ctl.signal, AbortSignal.timeout(15000)])).then((r) => {
      if (ctl.signal.aborted) return;
      if (r.ok) setBands(r.body.bands);
      setList(r.ok ? { kind: "ready", count: r.body.count, items: r.body.items } : { kind: "error" });
    });
    return () => ctl.abort();
  }, [filmId, sort, band, version]);

  const helpful = async (id: number) => {
    if (vote.kind === "voting" || list.kind !== "ready") return;
    setVote({ kind: "voting", id });
    const r = await send<{ helpful: number }>("POST", `/api/me/reviews/${id}/helpful`, {});
    if (!r.ok) return setVote({ kind: "failed", message: r.message || "Your vote was not counted. Try again." });
    setVote({ kind: "idle" });
    setVoted((v) => new Set([...v, id]));
    setList((l) => l.kind === "ready" ? { ...l, items: l.items.map((x) => x.id === id ? { ...x, helpful: r.body.helpful } : x) } : l);
  };

  const total = bands ? REVIEW_BANDS.reduce((n, b) => n + bands[b], 0) : null;
  return (
    <section className="fr-reviews" aria-labelledby="film-reviews">
      <h2 id="film-reviews">Reviews</h2>
      {children}
      <div className="fr-row-head">
        <h3>What people thought</h3>
        <p>{total === null ? "" : `${total} ${total === 1 ? "review" : "reviews"}`}</p>
      </div>
      <div className="fr-review-tools">
        <ChoiceGroup label="Show reviews by stars" className="fr-pick" selected={band}
                     onSelect={(v) => setBand(v as ReviewBand | null)}
                     choices={[{ value: null, label: `All${total === null ? "" : ` (${total})`}` },
                               ...REVIEW_BANDS.map((b) => ({ value: b, label: bandLabel(b, bands) }))]} />
        <ChoiceGroup label="Sort reviews" className="fr-pick" selected={sort} onSelect={(v) => setSort((v ?? "newest") as ReviewSort)}
                     choices={[{ value: "newest", label: "Newest" }, { value: "helpful", label: "Most helpful" }]} />
      </div>
      {list.kind === "loading" ? <p className="fr-state">Loading reviews…</p>
        : list.kind === "error" ? <p className="fr-state">Reviews cannot be loaded right now.</p>
        : list.items.length === 0 ? (
          <p className="fr-state">{band ? `No reviews scored ${bandRange(band)} yet.` : "No reviews yet. Be the first to write one."}</p>
        ) : (
          <div className="fr-review-scroll" role="region" aria-label="Reviews list, scrollable" tabIndex={0}>
            <ul className="fr-review-list">
              {list.items.map((x) => {
                const own = me?.review_id === x.id;
                const done = voted.has(x.id);
                return (
                  <li key={x.id} className="fr-review-row">
                    <span className="fr-avatar" aria-hidden="true">{initials(x.author)}</span>
                    <p className="fr-review-who">
                      <strong>{x.author}{own ? " (you)" : ""}</strong>
                      {x.verified ? <span className="fr-review-badge">Saw it at FrontRow</span> : null}
                    </p>
                    <span className="fr-review-score" aria-label={`${x.score} out of 10`}><span aria-hidden="true">★ {x.score}/10</span></span>
                    <p className="fr-review-text">{x.text}</p>
                    <div className="fr-review-foot">
                      <span>{dayLabel(x.written_at.slice(0, 10))}</span>
                      <span>{x.helpful} found this helpful</span>
                      {signedIn && !own ? (
                        <button type="button" className="fr-action-secondary fr-helpful" aria-pressed={done}
                                disabled={done || (vote.kind === "voting" && vote.id === x.id)} onClick={() => void helpful(x.id)}>
                          <span aria-hidden="true">👍</span> {done ? "Helpful (you)" : "Helpful"}
                        </button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      {!signedIn && list.kind === "ready" && list.items.length ? (
        <p className="fr-reviews-signin"><Link to={signInHref(`/movies/${filmId}`)}>Sign in</Link> to mark a review helpful.</p>
      ) : null}
      <p role="status" className="fr-share-note">{vote.kind === "failed" ? vote.message : ""}</p>
    </section>
  );
}
