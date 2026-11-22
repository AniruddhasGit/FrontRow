// CR-011 F4: the film page's reviews - every one by a customer who booked and saw the film here (the server's gate),
// newest or most helpful first, each with a Helpful vote (once per customer, never on your own: the server enforces
// both; the button only mirrors it). One status for the list (ReviewList) and one for a vote; no timer, no poll: the list
// is read on arrival, on a sort change, and once after the viewer posts a review.
import { useEffect, useState } from "react";
import { Link } from "../../router";
import { signInHref } from "../auth/session";
import { get, send } from "../browse/api";
import { ChoiceGroup } from "../browse/DayStrip";
import { dayLabel } from "../browse/logic";
import { initials, type Review, type ReviewList, type ReviewSort } from "./discover";

type Vote = { kind: "idle" } | { kind: "voting"; id: number } | { kind: "failed"; message: string };

export function Reviews({ filmId, version, me, signedIn }: {
  filmId: number; version: number; me: { review_id: number | null; voted: number[] } | null; signedIn: boolean;
}) {
  const [sort, setSort] = useState<ReviewSort>("newest");
  const [list, setList] = useState<ReviewList>({ kind: "loading" });
  const [vote, setVote] = useState<Vote>({ kind: "idle" });
  const [voted, setVoted] = useState<Set<number>>(new Set());
  useEffect(() => setVoted(new Set(me?.voted ?? [])), [me?.voted]);
  useEffect(() => {
    const ctl = new AbortController();
    setList({ kind: "loading" });
    void get<{ count: number; items: Review[] }>(`/api/movies/${filmId}/reviews?sort=${sort}`, AbortSignal.any([ctl.signal, AbortSignal.timeout(15000)])).then((r) => {
      if (ctl.signal.aborted) return;
      setList(r.ok ? { kind: "ready", count: r.body.count, items: r.body.items } : { kind: "error" });
    });
    return () => ctl.abort();
  }, [filmId, sort, version]);

  const helpful = async (id: number) => {
    if (vote.kind === "voting" || list.kind !== "ready") return;
    setVote({ kind: "voting", id });
    const r = await send<{ helpful: number }>("POST", `/api/me/reviews/${id}/helpful`, {});
    if (!r.ok) return setVote({ kind: "failed", message: r.message || "Your vote was not counted. Try again." });
    setVote({ kind: "idle" });
    setVoted((v) => new Set([...v, id]));
    setList((l) => l.kind === "ready" ? { ...l, items: l.items.map((x) => x.id === id ? { ...x, helpful: r.body.helpful } : x) } : l);
  };

  return (
    <section className="fr-reviews" aria-labelledby="film-reviews">
      <div className="fr-row-head">
        <h2 id="film-reviews">Top reviews</h2>
        <p>{list.kind === "ready" ? `${list.count} ${list.count === 1 ? "review" : "reviews"} from people who saw it here` : ""}</p>
      </div>
      <ChoiceGroup label="Sort reviews" className="fr-pick" selected={sort} onSelect={(v) => setSort((v ?? "newest") as ReviewSort)}
                   choices={[{ value: "newest", label: "Newest" }, { value: "helpful", label: "Most helpful" }]} />
      {list.kind === "loading" ? <p className="fr-state">Loading reviews…</p>
        : list.kind === "error" ? <p className="fr-state">Reviews cannot be loaded right now.</p>
        : list.items.length === 0 ? <p className="fr-state">No reviews yet. People who book and see it here can write the first.</p>
        : (
          <ul className="fr-review-cards">
            {list.items.map((x) => {
              const own = me?.review_id === x.id;
              const done = voted.has(x.id);
              return (
                <li key={x.id} className="fr-review-card">
                  <div className="fr-review-who">
                    <span className="fr-avatar" aria-hidden="true">{initials(x.author)}</span>
                    <span>
                      <strong>{x.author}{own ? " (you)" : ""}</strong>
                      <span className="fr-review-badge">Saw it at FrontRow</span>
                    </span>
                    <span className="fr-review-score" aria-label={`${x.score} out of 10`}><span aria-hidden="true">★ {x.score}/10</span></span>
                  </div>
                  <p className="fr-review-text">{x.text}</p>
                  <div className="fr-review-foot">
                    <span className="fr-review-date">{dayLabel(x.written_at.slice(0, 10))}</span>
                    <span className="fr-review-helpful">{x.helpful} found this helpful</span>
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
        )}
      {!signedIn && list.kind === "ready" && list.items.length ? (
        <p className="fr-reviews-signin"><Link to={signInHref(`/movies/${filmId}`)}>Sign in</Link> to mark a review helpful.</p>
      ) : null}
      <p role="status" className="fr-share-note">{vote.kind === "failed" ? vote.message : ""}</p>
    </section>
  );
}
