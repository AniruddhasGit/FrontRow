// SCR-PAY-01 · the checkout screen at /showtimes/{showtime_id}/checkout - the only screen with a pay action.
// The panel and every rule are in checkout.ts; this file owns the ticking, the storage and the navigation.
import { useCallback, useEffect, useState } from "react";
import { navigate } from "../../router";
import { MINOR_UNIT_RATIO, formatPaise } from "../admin/money";
import { get } from "../browse/api";
import { dayLabel, timeLabel } from "../browse/logic";
import { HoldCountdown } from "../seatmap/Countdown";
import { countdown } from "../seatmap/hold";
import { HOLD_KEY, SELECTION_KEY } from "../seatmap/model";
import { handOver } from "../ticket/arrival";
import { CHECKOUT_EXPIRY_RETURN_DELAY_MS, CheckoutView, arrival, bannerText, pay, type Arrival, type HeldHold } from "./checkout";
import { payExtras, points as pointsText, type Quote } from "../account/account";
import "./booking.css";

type Header = { movie: { title: string }; screen: { name: string }; starts_at: string };
// CR-008 (the lead's confirmed finding): one server hold per customer and showtime can grow from another tab, so the
// screen shows the SERVER's seats and total, read on arrival, and Pay carries that total (expected_total_paise).
type ServerHold = { kind: "checking" } | { kind: "ready"; hold: HeldHold & { total_paise: number } } | { kind: "failed"; message: string };
// CR-008 T3: the points offer for this order, from the server's own formula (GET /api/me/rewards?quote_paise=).
type Offer = { kind: "loading" } | { kind: "none" } | { kind: "ready"; balance: number; quote: Quote };
const WAIT = () => AbortSignal.timeout(15000); // a read that never answers ends (web-app-pitfalls rule 2)

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function where(showtimeId: number): Arrival {
  const s = storage();
  return s ? arrival(s, showtimeId, HOLD_KEY) : { kind: "seatmap" };
}

export function CheckoutScreen({ showtimeId }: { showtimeId: string }) {
  const id = Number(showtimeId);
  const [route] = useState(() => where(id));
  const hold = route.kind === "checkout" ? route.hold : null;
  const [header, setHeader] = useState<Header | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [inFlight, setInFlight] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [span] = useState(() => (hold ? Math.max(0, Date.parse(hold.expires_at) - Date.now()) : 0));
  const [server, setServer] = useState<ServerHold>({ kind: "checking" });
  const [reread, setReread] = useState(0);
  const [offer, setOffer] = useState<Offer>({ kind: "loading" });
  const [usePoints, setUsePoints] = useState(false);

  useEffect(() => {
    if (!hold) return;
    let live = true;
    setServer({ kind: "checking" });
    get<HeldHold & { total_paise: number }>(`/api/holds/${encodeURIComponent(hold.hold_token)}`, WAIT()).then((r) => {
      if (!live) return;
      if (!r.ok) return setServer({ kind: "failed", message: r.message || "Your seats could not be checked. Try again, or go back to the seat map." });
      setServer({ kind: "ready", hold: r.body });
      try {
        window.sessionStorage.setItem(HOLD_KEY, JSON.stringify(r.body)); // this tab's copy now matches the server's
      } catch {
        // storage refused: the screen still shows the server's seats
      }
    });
    return () => {
      live = false;
    };
  }, [hold, reread]);

  const serverTotal = server.kind === "ready" ? server.hold.total_paise : null;
  useEffect(() => {
    if (serverTotal === null) return;
    let live = true;
    setOffer({ kind: "loading" });
    get<{ points_balance: number; quote: Quote }>(`/api/me/rewards?quote_paise=${serverTotal}`, WAIT()).then((r) => {
      if (!live) return;
      // No points, or the offer cannot be read: checkout goes on at the full price - the offer is never a gate.
      setOffer(r.ok && r.body.quote.points > 0 ? { kind: "ready", balance: r.body.points_balance, quote: r.body.quote } : { kind: "none" });
    });
    return () => {
      live = false;
    };
  }, [serverTotal]);

  useEffect(() => {
    // Decided from stored values alone, with no request (SCR-PAY-01).
    if (route.kind === "confirmed") navigate(`/bookings/${encodeURIComponent(route.reference)}`);
    else if (route.kind === "seatmap") navigate(`/showtimes/${id}`);
    else get<Header>(`/api/showtimes/${id}`).then((r) => r.ok && setHeader(r.body));
  }, [route, id]);

  // The screen owns the ticking; the panel only renders the instant it is handed.
  useEffect(() => {
    if (!hold) return;
    let timer = 0;
    const tick = () => {
      setNow(Date.now());
      timer = window.setTimeout(tick, 250);
    };
    timer = window.setTimeout(tick, 250);
    return () => window.clearTimeout(timer);
  }, [hold]);

  const expired = hold ? countdown(hold.expires_at, now).ended : false;

  // 0:00 with no confirm in flight: stay for CHECKOUT_EXPIRY_RETURN_DELAY_MS, then back to the map with the selection.
  useEffect(() => {
    if (!hold || !expired || inFlight) return;
    const t = window.setTimeout(() => {
      try {
        window.sessionStorage.setItem(SELECTION_KEY, JSON.stringify({ showtime_id: id, seat_ids: hold.seats.map((s) => s.seat_id) }));
      } catch {
        // storage refused: the map opens with no selection
      }
      navigate(`/showtimes/${id}`);
    }, CHECKOUT_EXPIRY_RETURN_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [hold, expired, inFlight, id]);

  const quote = offer.kind === "ready" ? offer.quote : null;
  const onPay = useCallback(async () => {
    const s = storage();
    if (!hold || !s || inFlight || serverTotal === null) return;
    setInFlight(true);
    const out = await pay({
      fetch: (url, init) => window.fetch(url, init), store: s, hold, extras: payExtras(serverTotal, quote, usePoints),
      wait: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
      onInFlight: () => setBanner(bannerText("IDEMPOTENCY_IN_FLIGHT", "", null)),
    });
    setInFlight(false);
    if (out.ok) {
      handOver(out.body.booking_reference);
      navigate(`/bookings/${encodeURIComponent(out.body.booking_reference)}`);
      return;
    }
    if (out.code === "TOTAL_CHANGED") setReread((n) => n + 1); // read the server's hold again and show what Pay would book
    setBanner(bannerText(out.code, out.message, out.requestId));
  }, [hold, inFlight, serverTotal, quote, usePoints]);

  if (!hold) return null;
  const starts = header?.starts_at ?? "";
  return (
    <CheckoutView
      banner={banner}
      title={header?.movie.title ?? ""}
      hall={header?.screen.name ?? ""}
      startsLabel={starts ? `${dayLabel(starts.slice(0, 10))} · ${timeLabel(starts)}` : ""}
      seats={server.kind === "ready" ? server.hold.seats : hold.seats}
      discountPaise={usePoints && quote ? quote.discount_paise : undefined}
      points={server.kind === "failed" ? (
        <div className="fr-state" role="alert"><p>{server.message}</p>
          <button type="button" className="fr-clear" onClick={() => setReread((n) => n + 1)}>Try again</button></div>
      ) : offer.kind === "ready" ? (
        <label className="fr-checkout-points">
          <input type="checkbox" checked={usePoints} disabled={inFlight} onChange={(e) => setUsePoints(e.target.checked)} />
          <span>Use {pointsText(offer.quote.points)} for {formatPaise(offer.quote.discount_paise)} off
            {offer.balance > offer.quote.points ? ` (you have ${pointsText(offer.balance)}; up to half an order can be paid with points)` : ""}</span>
        </label>
      ) : undefined}
      money={formatPaise}
      ratio={MINOR_UNIT_RATIO}
      countdown={<HoldCountdown expiresAt={hold.expires_at} now={now} confirmInFlight={inFlight} totalMs={span} />}
      live={!expired && server.kind === "ready"}
      expired={expired}
      inFlight={inFlight}
      onPay={() => void onPay()}
      onBack={() => navigate(`/showtimes/${id}`)} // navigation only: there is no client-side release
    />
  );
}
