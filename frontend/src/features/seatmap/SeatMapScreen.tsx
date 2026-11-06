// SCR-BRW-03 + SCR-SEA-01 · the seat map at `/showtimes/{showtime_id}` - ONE screen, the read path and the
// selection layer. Anyone may open it; a guest sees the identical map and the action `Sign in to hold these seats`.
//
// Phase 4 (EP-HLD-01..04): a signed-in customer's press takes the hold, tapping a held seat gives it back, and
// `Give up these seats` releases the whole hold. Choosing seats still sends nothing: the selection lives in
// sessionStorage `fr.selection`, the hold in `fr.hold` (sessionStorage, which dies with the tab - P-HLD-09). Closing the
// tab sends nothing either: there is no unload handler, and the hold's TTL is what releases it.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { formatPaise } from "../admin/money";
import { forgetBooking } from "../booking/checkout";
import { get } from "../browse/api";
import { timeLabel } from "../browse/logic";
import { Hall3D } from "../hall3d/Hall3D";
import { HoldCountdown } from "./Countdown";
import { GIVE_UP, adding, closedBanner, failureOf, markTaken, primaryLabel, send, withoutLabels, type Hold } from "./hold";
import {
  HOLD_KEY, LEGEND, MAX_SEATS_PER_BOOKING, SELECTION_KEY, TREATMENT, bands, capNote, changedSeats, goneBanner, mapBanner,
  parseSeatMap, recheck, seatLabel, seatName, selectable, toggle, total, visualOf, type Seat, type SeatMap, type Visual,
} from "./model";
import { createPoller } from "./poller";
import "./seatmap.css";

type Header = { id: number; movie: { title: string }; screen: { name: string }; starts_at: string };
type LoadError = { message: string; requestId: string | null };

function readJson<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function readSelection(showtimeId: number): number[] {
  const stored = readJson<{ showtime_id: number; seat_ids: number[] }>(SELECTION_KEY);
  return stored && stored.showtime_id === showtimeId && Array.isArray(stored.seat_ids) ? stored.seat_ids.filter(Number.isInteger) : [];
}

function writeSelection(showtimeId: number, ids: number[]): void {
  try {
    if (ids.length === 0) window.sessionStorage.removeItem(SELECTION_KEY);
    else window.sessionStorage.setItem(SELECTION_KEY, JSON.stringify({ showtime_id: showtimeId, seat_ids: ids }));
  } catch {
    // storage refused (a private window): the selection still works for this page
  }
}

function readHold(showtimeId: number): Hold | null {
  const hold = readJson<Hold>(HOLD_KEY);
  return hold && hold.showtime_id === showtimeId && typeof hold.hold_token === "string" ? hold : null;
}

function writeHold(hold: Hold | null): void {
  try {
    if (!hold || hold.seats.length === 0) window.sessionStorage.removeItem(HOLD_KEY);
    else window.sessionStorage.setItem(HOLD_KEY, JSON.stringify(hold));
  } catch {
    // storage refused: the hold still works for this page
  }
}

// --fr-motion-change, read from the token so the duration has one definition (COMPONENTS.md §0.5).
function motionChangeMs(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--fr-motion-change").trim();
  return raw.endsWith("ms") ? Number.parseFloat(raw) : Number.parseFloat(raw) * 1000 || 0;
}

// A refusal's banner. SEAT_UNAVAILABLE is not dismissible: it clears when the selection changes (COMPONENTS.md §6).
type Notice = { code: string; message: string };

// The first state, for the render harness (react-dom/server runs no effect, so nothing is fetched or polled there).
// A seeded `map` must already have passed parseSeatMap. Production passes no seed.
type Seed = {
  header?: Header; map?: SeatMap; loadError?: LoadError; pollStrip?: string; selection?: number[]; gone?: string;
  signedIn?: boolean; hold?: Hold; notice?: Notice; now?: number;
};

export function SeatMapScreen({ showtimeId, seed }: { showtimeId: string; seed?: Seed }) {
  const id = Number(showtimeId);
  const [header, setHeader] = useState<Header | null>(seed?.header ?? null);
  const [map, setMap] = useState<SeatMap | null>(seed?.map ?? null);
  const [loadError, setLoadError] = useState<LoadError | null>(seed?.loadError ?? null);
  const [pollStrip, setPollStrip] = useState<string | null>(seed?.pollStrip ?? null);
  const [selection, setSelection] = useState<number[]>(() => seed?.selection ?? readSelection(id));
  const [gone, setGone] = useState<string | null>(seed?.gone ?? null);
  const [changed, setChanged] = useState<Set<number>>(new Set());
  const [signedIn, setSignedIn] = useState(seed?.signedIn ?? false);
  const [attempt, setAttempt] = useState(0);
  const [hold, setHoldState] = useState<Hold | null>(() => seed?.hold ?? readHold(id));
  const [holdSpan, setHoldSpan] = useState(0); // the bar's full length: what was left when this page first saw the hold
  const [notice, setNotice] = useState<Notice | null>(seed?.notice ?? null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => seed?.now ?? Date.now());
  const last = useRef<SeatMap | null>(null);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;

  const setHold = useCallback((next: Hold | null) => {
    setHoldState(next);
    writeHold(next);
    if (next) setHoldSpan((span) => span || Math.max(0, Date.parse(next.expires_at) - Date.now()));
    else setHoldSpan(0);
  }, []);

  useEffect(() => {
    get<Header>(`/api/showtimes/${id}`).then((r) => r.ok && setHeader(r.body));
    get("/api/auth/me").then((r) => setSignedIn(r.ok));
    // A reload re-reads the hold from the server, which answers from Redis alone (EP-HLD-02).
    const stored = readHold(id);
    if (stored) {
      send<Hold>("GET", `/api/holds/${stored.hold_token}`).then((r) => {
        if (r.ok && r.body) setHold(r.body);
        else if (!r.ok && failureOf(r.code, r.details).kind === "ended") setHold(null);
      });
    }
  }, [id, setHold]);

  // The screen owns the ticking; the countdown component only renders the instant it is handed.
  useEffect(() => {
    if (!hold) return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [hold]);

  const receive = useCallback((next: SeatMap) => {
    const moved = changedSeats(last.current, next);
    last.current = next;
    setMap(next);
    setPollStrip(null);
    // Re-check the selection against the fresh map; a seat that has gone leaves it and is named once (P-SEA-03).
    const { kept, gone: lost } = recheck(selectionRef.current, next);
    if (lost.length > 0) {
      setSelection(kept);
      writeSelection(next.showtime.id, kept);
      setGone(goneBanner(lost));
    }
    if (moved.size > 0) {
      setChanged(moved);
      window.setTimeout(() => setChanged(new Set()), motionChangeMs());
    }
  }, []);

  useEffect(() => {
    setLoadError(null);
    const poller = createPoller<SeatMap>({
      timer: { setTimeout: (fn, ms) => window.setTimeout(fn, ms), clearTimeout: (h) => window.clearTimeout(h as number) },
      visibility: {
        hidden: () => document.hidden,
        onChange: (fn) => {
          document.addEventListener("visibilitychange", fn);
          return () => document.removeEventListener("visibilitychange", fn);
        },
      },
      fetchOnce: async () => {
        const r = await get<unknown>(`/api/showtimes/${id}/seatmap`);
        if (!r.ok) {
          if (last.current === null) setLoadError(firstLoadError(r));
          setPollStrip(r.status === 429 ? "Too many requests. The seat map will update again shortly."
                                         : "The seat map is not updating. The seats shown may be out of date.");
          return { ok: false, retryAfter: r.retryAfter ?? undefined };
        }
        const parsed = parseSeatMap(r.body);
        if (!parsed) {
          if (last.current === null) setLoadError({ message: "The seat map could not be loaded.", requestId: null });
          return { ok: false };
        }
        return { ok: true, value: parsed, interval: parsed.poll_interval_seconds };
      },
      onValue: receive,
      onError: () => undefined,
    });
    poller.start();
    return () => poller.stop();
  }, [id, attempt, receive]);

  const heldIds = useMemo(() => new Set((hold?.seats ?? []).map((s) => s.seat_id)), [hold]);
  const mine = useMemo(() => new Set([...heldIds, ...selection]), [heldIds, selection]);
  const seatsById = useMemo(() => new Map((map?.seats ?? []).map((s) => [s.id, s])), [map]);
  const categoryName = useMemo(() => new Map((map?.categories ?? []).map((c) => [c.id, c.name])), [map]);

  const failed = (r: { code: string; message: string; details: unknown }) => {
    const f = failureOf(r.code, r.details);
    if (f.kind === "taken" && map) {
      setMap(markTaken(map, f.labels));
      const kept = withoutLabels(selectionRef.current, map, f.labels);
      selectionRef.current = kept;
      setSelection(kept);
      writeSelection(map.showtime.id, kept);
    }
    if (f.kind === "ended") setHold(null);
    if (f.kind === "sign_in") setSignedIn(false);
    setNotice(r.message ? { code: r.code, message: r.message } : null);
  };

  const takeHold = async () => {
    const want = adding(selectionRef.current, hold);
    if (!map || busy || want.length === 0) return;
    setBusy(true);
    const r = await send<Hold>("POST", `/api/showtimes/${id}/holds`, { seat_ids: want });
    setBusy(false);
    if (r.ok && r.body) {
      // A new hold forgets the last booking, so a second booking of this showtime in this tab reaches checkout (P-PAY-14).
      try {
        forgetBooking(window.sessionStorage);
      } catch {
        // storage refused: there is no stored booking to forget
      }
      setHold(r.body);
      selectionRef.current = [];
      setSelection([]);
      writeSelection(id, []);
      setNotice(null);
    } else if (!r.ok) failed(r);
  };

  const giveBack = async (seatId: number | null) => {
    if (!hold || busy) return;
    setBusy(true);
    const path = seatId === null ? `/api/holds/${hold.hold_token}` : `/api/holds/${hold.hold_token}/seats/${seatId}`;
    const r = await send<Hold>("DELETE", path);
    setBusy(false);
    if (r.ok) setHold(seatId === null || !r.body || r.body.seats.length === 0 ? null : r.body);
    else failed(r);
  };

  const tap = (seat: Seat, visual: Visual) => {
    if (heldIds.has(seat.id)) {
      void giveBack(seat.id); // tapping a held seat gives that seat back (P-HLD-08)
      return;
    }
    if (!map || map.showtime.sales_closed || !seat.is_active) return;
    // From the ref, not the render's closure: two taps inside one frame must both count.
    const current = selectionRef.current;
    const next = toggle(current, seat, visual, MAX_SEATS_PER_BOOKING);
    if (next.selection === current) return;
    selectionRef.current = next.selection;
    setSelection(next.selection);
    writeSelection(map.showtime.id, next.selection);
    setGone(null);
    setNotice((n) => (n?.code === "SEAT_UNAVAILABLE" ? null : n));
  };

  if (loadError && !map) {
    return (
      <section className="fr-seatmap">
        <SeatMapHeading header={header} />
        <div className="fr-map-error">
          <p>{loadError.message}</p>
          {loadError.requestId ? <p className="fr-request-id">If you need help, quote {loadError.requestId}.</p> : null}
          <button type="button" className="fr-action-secondary" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      </section>
    );
  }

  const mapLine = map ? mapBanner(map) : null;
  const banner = map && mapLine && map.showtime.sales_closed ? closedBanner(mapLine, Boolean(hold)) : mapLine;
  const chosen = adding(selection, hold);
  const chosenSum = total(chosen, seatsById);
  // The held seats carry the prices the server fixed at acquisition; the chosen ones the map's. Integers, added.
  const sum = chosenSum === null ? null : chosenSum + (hold?.total_paise ?? 0);
  const lines = chosen.map((sid) => seatsById.get(sid)).filter((s): s is Seat => Boolean(s));
  const holding = Boolean(hold && hold.seats.length > 0);

  return (
    <section className="fr-seatmap">
      <SeatMapHeading header={header} />
      <div className="fr-banners">
        {notice ? (
          <div className="fr-banner" role="alert" aria-live="assertive">
            <p>{notice.message}</p>
            {notice.code === "SEAT_UNAVAILABLE" ? null : (
              <button type="button" className="fr-banner-dismiss" aria-label="Dismiss this message" onClick={() => setNotice(null)}>Dismiss</button>
            )}
          </div>
        ) : null}
        {gone ? (
          <div className="fr-banner" role="alert" aria-live="assertive">
            <p>{gone}</p>
            <button type="button" className="fr-banner-dismiss" aria-label="Dismiss this message" onClick={() => setGone(null)}>Dismiss</button>
          </div>
        ) : null}
        <div aria-live="polite">{banner ? <div className="fr-banner"><p>{banner}</p></div> : null}</div>
      </div>
      <Hall3D map={map} mine={mine} onTap={tap} />
      <div className="fr-seatmap-body">
        <div className="fr-field">
          <p className="fr-poll-strip" aria-live="polite">{pollStrip ?? ""}</p>
          <div className="fr-screen-bar" aria-hidden="true" />
          <p className="fr-screen-label" aria-hidden="true">SCREEN</p>
          {map ? (
            <Grid map={map} mine={mine} changed={changed} categoryName={categoryName} onTap={tap} />
          ) : (
            <div className="fr-grid fr-grid-loading" aria-hidden="true" />
          )}
        </div>
        <Legend map={map} />
        <aside className="fr-summary" aria-label="Your seats">
          {holding && hold ? (
            <HoldCountdown expiresAt={hold.expires_at} now={now} confirmInFlight={false} totalMs={holdSpan} />
          ) : null}
          <p className="fr-summary-heading">
            {holding && hold
              ? (hold.seats.length === 1 ? "1 seat held by you" : `${hold.seats.length} seats held by you`)
              : (selection.length === 1 ? "1 seat chosen" : `${selection.length} seats chosen`)}
          </p>
          <ul className="fr-summary-lines">
            {(hold?.seats ?? []).map((s) => (
              <li key={`h${s.seat_id}`} className="fr-summary-line">
                <span className="fr-mono">{s.label}</span>
                <span className="fr-summary-cat">{s.category}</span>
                <span className="fr-mono">{formatPaise(s.price_paise)}</span>
              </li>
            ))}
            {lines.map((s) => (
              <li key={s.id} className="fr-summary-line">
                <span className="fr-mono">{seatLabel(s)}</span>
                <span className="fr-summary-cat">{categoryName.get(s.cat)}</span>
                <span className="fr-mono">{formatPaise(s.price_paise)}</span>
              </li>
            ))}
            <li className="fr-summary-line fr-summary-total">
              <span className="fr-total-label">TOTAL</span>
              {sum !== null && map ? <span className="fr-total">{formatPaise(sum)}</span> : null}
            </li>
          </ul>
          <p className="fr-cap-note" aria-live="polite">{capNote(MAX_SEATS_PER_BOOKING)}</p>
          {signedIn ? (
            <button type="button" className="fr-action" disabled={!map || busy || chosen.length === 0 || sum === null || map.showtime.sales_closed}
                    onClick={() => void takeHold()}>
              {primaryLabel(true, chosen.length, holding)}
            </button>
          ) : (
            // The sign-in step and the selection's round trip through it are the account lane's (P-ACC-13, S-ACC-14).
            <button type="button" className="fr-action" disabled={!map || sum === null}>{primaryLabel(false, chosen.length, false)}</button>
          )}
          {holding ? (
            <button type="button" className="fr-action-secondary" disabled={busy} onClick={() => void giveBack(null)}>{GIVE_UP}</button>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function firstLoadError(r: { status: number; message: string; requestId: string | null }): LoadError {
  if (r.status === 404) return { message: "That showtime could not be found.", requestId: null };
  if (r.status === 503 && r.message) return { message: r.message, requestId: null };
  // Every other 4xx and 5xx, 429 included: the first-load error. The request id is shown on 5xx only (FR-ADR-052).
  return { message: "The seat map could not be loaded.", requestId: r.status >= 500 ? r.requestId : null };
}

function SeatMapHeading({ header }: { header: Header | null }) {
  return (
    <header className="fr-seatmap-head">
      <h1>{header ? header.movie.title : " "}</h1>
      <p className="fr-meta">{header ? <><span className="fr-mono">{timeLabel(header.starts_at)}</span><span>{header.screen.name}</span></> : " "}</p>
    </header>
  );
}

function Grid({ map, mine, changed, categoryName, onTap }: {
  map: SeatMap; mine: ReadonlySet<number>; changed: ReadonlySet<number>; categoryName: ReadonlyMap<number, string>;
  onTap: (seat: Seat, visual: Visual) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const rows = useMemo(() => {
    const byRow = new Map<number, Seat[]>();
    for (const s of map.seats) {
      if (!byRow.has(s.gr)) byRow.set(s.gr, []);
      byRow.get(s.gr)!.push(s);
    }
    return byRow;
  }, [map]);
  const runs = useMemo(() => bands(map), [map]);
  const bandOf = useMemo(() => {
    const out = new Map<number, number>();
    for (const b of runs) for (let gr = b.from; gr <= b.to; gr++) if (rows.has(gr)) out.set(gr, b.cat);
    return out;
  }, [runs, rows]);
  // A rule sits between two ADJACENT bands only: nothing but void rows between them (P-BRW-16 rule 6).
  const ruleBefore = useMemo(() => {
    const out = new Set<number>();
    for (let i = 1; i < runs.length; i++) {
      let adjacent = true;
      for (let gr = runs[i - 1].to + 1; gr < runs[i].from; gr++) if (rows.has(gr)) adjacent = false;
      if (adjacent) out.add(runs[i].from);
    }
    return out;
  }, [runs, rows]);
  const tabbable = focusId !== null && map.seats.some((s) => s.id === focusId) ? focusId : map.seats[0]?.id;

  const move = (from: Seat, key: string): Seat | null => {
    if (key === "ArrowLeft" || key === "ArrowRight") {
      const same = rows.get(from.gr)!;
      const i = same.indexOf(from) + (key === "ArrowRight" ? 1 : -1);
      return same[i] ?? null;
    }
    const grs = [...rows.keys()].sort((a, b) => a - b);
    const target = grs[grs.indexOf(from.gr) + (key === "ArrowDown" ? 1 : -1)];
    if (target === undefined) return null;
    return rows.get(target)!.reduce((best, s) => (Math.abs(s.gc - from.gc) < Math.abs(best.gc - from.gc) ? s : best));
  };

  const onKey = (e: KeyboardEvent, seat: Seat, visual: Visual) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (selectable(seat, visual, map.showtime.sales_closed)) onTap(seat, visual);
      return;
    }
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const next = move(seat, e.key);
    if (!next) return;
    setFocusId(next.id);
    const el = container.current?.querySelector<HTMLElement>(`[data-seat-id="${next.id}"]`);
    el?.focus({ preventScroll: true });
    // The minimum movement that brings the cell fully into view; scroll-padding keeps it clear of the gutter.
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  };

  const gridRows = [];
  for (let gr = 1; gr <= map.screen.rows; gr++) {
    const seats = rows.get(gr);
    if (ruleBefore.has(gr)) gridRows.push(<div key={`rule-${gr}`} className="fr-band-rule" data-band-rule="" aria-hidden="true" />);
    gridRows.push(
      <div key={gr} role="row" className="fr-grid-row" data-band={bandOf.has(gr) ? String(bandOf.get(gr)) : undefined}>
        <span role="rowheader" className="fr-gutter">{seats ? seats[0].row : ""}</span>
        {(seats ?? []).map((s) => {
          const visual = visualOf(s, mine);
          const t = TREATMENT[visual];
          return (
            <span
              key={s.id}
              role="gridcell"
              data-seat-id={s.id}
              data-visual={s.is_active ? visual : "out_of_service"}
              data-glyph={t.glyph}
              data-changed={changed.has(s.id) ? "" : undefined}
              aria-label={seatName(s, categoryName.get(s.cat) ?? "", visual)}
              aria-selected={visual === "held_by_me"}
              aria-disabled={!selectable(s, visual, map.showtime.sales_closed)}
              tabIndex={s.id === tabbable ? 0 : -1}
              className="fr-seat"
              style={{ gridColumn: s.gc + 1 }}
              onClick={() => { setFocusId(s.id); if (selectable(s, visual, map.showtime.sales_closed)) onTap(s, visual); }}
              onKeyDown={(e) => onKey(e, s, visual)}
            >
              {visual === "held_by_me" && s.is_active ? null : <span className="fr-seat-num">{s.num}</span>}
            </span>
          );
        })}
      </div>,
    );
  }

  return (
    <>
      {runs.length === 0 ? <p className="fr-mixed-note">Seat categories are mixed within rows. Each seat's category is in the legend and in its label.</p> : null}
      <div ref={container} className="fr-grid-scroll">
        <div role="grid" aria-label="Seat map" className="fr-grid" style={{ ["--fr-grid-cols" as string]: String(map.screen.cols) }}>
          {gridRows}
        </div>
      </div>
    </>
  );
}

function Legend({ map }: { map: SeatMap | null }) {
  return (
    <div className="fr-legend">
      <ul className="fr-legend-states">
        {LEGEND.map((l) => (
          <li key={l.visual}>
            <span className="fr-seat fr-swatch" aria-hidden="true" data-visual={l.visual}
                  data-glyph={l.visual === "out_of_service" ? "outline" : TREATMENT[l.visual].glyph} />
            <span>{l.label}</span>
          </li>
        ))}
      </ul>
      <ul className="fr-legend-categories">
        {map
          ? map.categories.map((c) => (
              <li key={c.id}><span>{c.name}</span>{"  "}<span className="fr-mono fr-legend-price">{formatPaise(c.price_paise)}</span></li>
            ))
          : <li><span className="fr-inset-block" /></li>}
      </ul>
    </div>
  );
}
