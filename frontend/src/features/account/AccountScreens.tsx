// CR-008 T3, T4, T6, T7: the account pages the sidebar links to - Rewards, Wishlist, Notifications, Profile & settings.
// Each page reads once on arrival (no polling); every read and write is one status union with a retry (account.ts).
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "../../router";
import { formatPaise } from "../admin/money";
import { get, send } from "../browse/api";
import { Poster } from "../browse/Poster";
import { dayLabel } from "../browse/logic";
import {
  UNAVAILABLE, loaded, points, profileBody, profileErrors, type Load, type ProfileForm, type Send,
} from "./account";
import "./account.css";

const WAIT = () => AbortSignal.timeout(15000); // web-app-pitfalls rule 2: a read that never answers ends in "error"

/** One read with its retry. `seed` is the first state, for the render harness (no effect runs there). */
export function useLoad<T>(path: string, seed?: Load<T>): [Load<T>, () => void, (data: T) => void] {
  const [state, setState] = useState<Load<T>>(seed ?? { kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (seed) return;
    let live = true;
    setState({ kind: "loading" });
    get<T>(path, WAIT()).then((r) => live && setState(loaded(r)));
    return () => {
      live = false;
    };
  }, [path, attempt, seed]);
  return [state, useCallback(() => setAttempt((n) => n + 1), []), useCallback((data: T) => setState({ kind: "ready", data }), [])];
}

/** The page frame: heading, then the read's four states, each with a way forward. */
function Page<T>({ title, here, state, retry, children }: {
  title: string; here: string; state: Load<T>; retry: () => void; children: (data: T) => ReactNode;
}) {
  return (
    <section className="fr-account-page" aria-labelledby="fr-account-h">
      <h1 id="fr-account-h">{title}</h1>
      {state.kind === "loading" ? <p className="fr-state" aria-busy="true">Loading…</p> : null}
      {state.kind === "guest" ? (
        <p className="fr-state">Sign in to see this page. <Link to={`/sign-in?next=${encodeURIComponent(here)}`} className="fr-signin">Sign in</Link></p>
      ) : null}
      {state.kind === "error" ? (
        <div className="fr-state" role="alert"><p>{state.message}</p>
          <button type="button" className="fr-clear" onClick={retry}>Try again</button></div>
      ) : null}
      {state.kind === "ready" ? children(state.data) : null}
    </section>
  );
}

// ---- T3: Rewards ----------------------------------------------------------------------------------------------------

type Rewards = {
  points_balance: number;
  rules: { earn_points_per_unit: number; redeem_points_per_unit: number; redeem_cap_percent: number };
  history: { kind: "earned" | "redeemed"; points: number; discount_paise: number | null; created_at: string; booking_reference: string }[];
};

export function RewardsScreen({ seed }: { seed?: Load<Rewards> }) {
  const [state, retry] = useLoad<Rewards>("/api/me/rewards", seed);
  return (
    <Page title="Rewards" here="/account/rewards" state={state} retry={retry}>
      {(r) => (
        <>
          <p className="fr-points-balance"><span className="fr-mono">{points(r.points_balance)}</span> to spend</p>
          <p className="fr-account-note">
            You earn {r.rules.earn_points_per_unit} points for every whole dollar you pay. At checkout, {r.rules.redeem_points_per_unit} points
            take $1.00 off, up to {r.rules.redeem_cap_percent}% of the order. Points are added when a booking is paid, once.
          </p>
          <h2>History</h2>
          {r.history.length === 0 ? <p>No points yet. <Link to="/films">Book a film</Link> to start earning.</p> : (
            <ul className="fr-account-list">
              {r.history.map((h) => (
                <li key={`${h.booking_reference}-${h.kind}`} className="fr-account-row">
                  <span className={h.kind === "earned" ? "fr-points-plus fr-mono" : "fr-points-minus fr-mono"}>
                    {h.kind === "earned" ? "+" : "−"}{points(h.points)}
                  </span>
                  <span>{h.kind === "earned" ? "Earned on" : `Used for ${formatPaise(h.discount_paise ?? 0)} off`}{" "}
                    <Link to={`/bookings/${encodeURIComponent(h.booking_reference)}`} className="fr-mono">{h.booking_reference}</Link></span>
                  <span className="fr-mono fr-account-when">{dayLabel(h.created_at.slice(0, 10))}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Page>
  );
}

// ---- T4: Wishlist ---------------------------------------------------------------------------------------------------

type Wishlist = { items: { movie_id: number; title: string; runtime_minutes: number; poster_url: string }[] };

export function WishlistScreen({ seed }: { seed?: Load<Wishlist> }) {
  const [state, retry, replace] = useLoad<Wishlist>("/api/me/bookmarks", seed);
  const [removing, setRemoving] = useState<Send>({ kind: "idle" });
  const remove = async (id: number, items: Wishlist["items"]) => {
    if (removing.kind === "sending") return;
    setRemoving({ kind: "sending" });
    const r = await send("PUT", `/api/me/bookmarks/${id}`, { saved: false });
    if (!r.ok) return setRemoving({ kind: "failed", message: r.message || UNAVAILABLE });
    setRemoving({ kind: "idle" });
    replace({ items: items.filter((i) => i.movie_id !== id) });
  };
  return (
    <Page title="Wishlist" here="/account/wishlist" state={state} retry={retry}>
      {(w) => (
        <>
          <div aria-live="polite">{removing.kind === "failed" ? <p className="fr-banner">{removing.message}</p> : null}</div>
          {w.items.length === 0 ? <p>Nothing saved yet. Press <strong>Save</strong> on a film to keep it here. <Link to="/films">See what is showing</Link></p> : (
            <ul className="fr-wishlist">
              {w.items.map((m) => (
                <li key={m.movie_id} className="fr-wish">
                  <Link to={`/movies/${m.movie_id}`} className="fr-wish-link">
                    <Poster src={m.poster_url} title={m.title} />
                    <span className="fr-wish-title">{m.title}</span>
                    <span className="fr-mono fr-account-when">{m.runtime_minutes} min</span>
                  </Link>
                  <button type="button" className="fr-action-secondary" disabled={removing.kind === "sending"}
                          onClick={() => void remove(m.movie_id, w.items)} aria-label={`Remove ${m.title} from your wishlist`}>Remove</button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Page>
  );
}

// ---- T7: Notifications ----------------------------------------------------------------------------------------------

type Inbox = { unread: number; items: { id: number; kind: string; title: string; body: string; read: boolean; created_at: string; booking_reference: string }[] };

export function NotificationsScreen({ seed }: { seed?: Load<Inbox> }) {
  const [state, retry, replace] = useLoad<Inbox>("/api/me/notifications", seed);
  const [marking, setMarking] = useState<Send>({ kind: "idle" });
  const mark = async (box: Inbox, ids: number[] | "all") => {
    if (marking.kind === "sending") return;
    setMarking({ kind: "sending" });
    const r = await send<{ unread: number }>("POST", "/api/me/notifications/read", ids === "all" ? { all: true } : { ids });
    if (!r.ok) return setMarking({ kind: "failed", message: r.message || UNAVAILABLE });
    setMarking({ kind: "idle" });
    replace({ unread: r.body.unread, items: box.items.map((n) => (ids === "all" || ids.includes(n.id) ? { ...n, read: true } : n)) });
    window.dispatchEvent(new Event("fr:account-changed")); // the header's badge re-reads its summary once
  };
  return (
    <Page title="Notifications" here="/account/notifications" state={state} retry={retry}>
      {(box) => (
        <>
          <p className="fr-account-note" aria-live="polite">{box.unread === 0 ? "You are all caught up." : `${box.unread} unread.`}</p>
          <div aria-live="polite">{marking.kind === "failed" ? <p className="fr-banner">{marking.message}</p> : null}</div>
          {box.unread > 0 ? (
            <button type="button" className="fr-action-secondary" disabled={marking.kind === "sending"} onClick={() => void mark(box, "all")}>
              Mark all as read
            </button>
          ) : null}
          {box.items.length === 0 ? <p>Nothing yet. Booking confirmations and points show up here.</p> : (
            <ul className="fr-account-list">
              {box.items.map((n) => (
                <li key={n.id} className={n.read ? "fr-account-row fr-note-read" : "fr-account-row fr-note-unread"}>
                  <span className="fr-note-title">{n.read ? null : <span className="fr-visually-hidden">Unread: </span>}{n.title}</span>
                  <span>{n.body} <Link to={`/bookings/${encodeURIComponent(n.booking_reference)}`}>View booking</Link></span>
                  <span className="fr-mono fr-account-when">{dayLabel(n.created_at.slice(0, 10))}</span>
                  {n.read ? null : (
                    <button type="button" className="fr-clear" disabled={marking.kind === "sending"} onClick={() => void mark(box, [n.id])}
                            aria-label={`Mark "${n.title}" as read`}>Mark read</button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Page>
  );
}

// ---- T6: Profile & settings -----------------------------------------------------------------------------------------

type Profile = { email: string; display_name: string | null; phone: string | null; preferred_language_id: number | null; preferred_format_id: number | null };
type Lookup = { id: number; name: string };

export function ProfileScreen({ seed, options }: { seed?: Load<Profile>; options?: { languages: Lookup[]; formats: Lookup[] } }) {
  const [state, retry, replace] = useLoad<Profile>("/api/me/profile", seed);
  const [lists, setLists] = useState(options ?? { languages: [] as Lookup[], formats: [] as Lookup[] });
  useEffect(() => {
    if (options) return;
    get<{ languages: Lookup[]; formats: Lookup[] }>("/api/reference", WAIT()).then((r) => r.ok && setLists(r.body));
  }, [options]);
  return (
    <Page title="Profile & settings" here="/account/profile" state={state} retry={retry}>
      {(p) => <ProfileEditor profile={p} lists={lists} saved={replace} />}
    </Page>
  );
}

function ProfileEditor({ profile, lists, saved }: { profile: Profile; lists: { languages: Lookup[]; formats: Lookup[] }; saved: (p: Profile) => void }) {
  const [form, setForm] = useState<ProfileForm>({
    display_name: profile.display_name ?? "", phone: profile.phone ?? "",
    preferred_language_id: profile.preferred_language_id ? String(profile.preferred_language_id) : "",
    preferred_format_id: profile.preferred_format_id ? String(profile.preferred_format_id) : "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof ProfileForm, string>>>({});
  const [status, setStatus] = useState<Send>({ kind: "idle" });
  const set = (k: keyof ProfileForm) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault();
    if (status.kind === "sending") return;
    const local = profileErrors(form);
    setErrors(local);
    if (Object.keys(local).length) return setStatus({ kind: "idle" });
    setStatus({ kind: "sending" });
    const r = await send<Profile>("PUT", "/api/me/profile", profileBody(form));
    if (r.ok) {
      setStatus({ kind: "done", message: "Saved." });
      window.dispatchEvent(new Event("fr:account-changed"));
      return saved(r.body);
    }
    const fields = (r.details as { fields?: Partial<Record<keyof ProfileForm, string>> } | undefined)?.fields;
    if (fields) setErrors(fields);
    setStatus({ kind: "failed", message: r.message || UNAVAILABLE });
  };
  const field = (k: keyof ProfileForm, label: string, control: ReactNode) => (
    <div className="fr-field">
      <label htmlFor={`fr-p-${k}`}>{label}</label>
      {control}
      {errors[k] ? <p className="fr-field-error" id={`fr-p-${k}-err`}>{errors[k]}</p> : null}
    </div>
  );
  const describe = (k: keyof ProfileForm) => ({ "aria-invalid": errors[k] ? true : undefined, "aria-describedby": errors[k] ? `fr-p-${k}-err` : undefined });
  return (
    <form className="fr-profile" onSubmit={(e) => void submit(e)} noValidate>
      <p className="fr-account-note">Signed in as <span className="fr-mono">{profile.email}</span>. The email cannot be changed.</p>
      {field("display_name", "Display name", <input id="fr-p-display_name" value={form.display_name} onChange={set("display_name")}
                                                    maxLength={80} autoComplete="nickname" {...describe("display_name")} />)}
      {field("phone", "Phone (optional)", <input id="fr-p-phone" value={form.phone} onChange={set("phone")} inputMode="tel"
                                                autoComplete="tel" {...describe("phone")} />)}
      {field("preferred_language_id", "Preferred language", (
        <select id="fr-p-preferred_language_id" value={form.preferred_language_id} onChange={set("preferred_language_id")} {...describe("preferred_language_id")}>
          <option value="">No preference</option>
          {lists.languages.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      ))}
      {field("preferred_format_id", "Preferred format", (
        <select id="fr-p-preferred_format_id" value={form.preferred_format_id} onChange={set("preferred_format_id")} {...describe("preferred_format_id")}>
          <option value="">No preference</option>
          {lists.formats.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      ))}
      <div aria-live="polite" className="fr-profile-status">
        {status.kind === "failed" ? <p className="fr-banner">{status.message}</p> : status.kind === "done" ? <p>{status.message}</p> : null}
      </div>
      <button type="submit" className="fr-action" disabled={status.kind === "sending"} aria-busy={status.kind === "sending" || undefined}>
        {status.kind === "sending" ? "Saving…" : "Save changes"}
      </button>
    </form>
  );
}
