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
import { CHECKOUT_EXPIRY_RETURN_DELAY_MS, CheckoutView, arrival, bannerText, pay, type Arrival } from "./checkout";
import "./booking.css";

type Header = { movie: { title: string }; screen: { name: string }; starts_at: string };

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

  const onPay = useCallback(async () => {
    const s = storage();
    if (!hold || !s || inFlight) return;
    setInFlight(true);
    const out = await pay({
      fetch: (url, init) => window.fetch(url, init), store: s, hold,
      wait: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
      onInFlight: () => setBanner(bannerText("IDEMPOTENCY_IN_FLIGHT", "", null)),
    });
    setInFlight(false);
    if (out.ok) {
      handOver(out.body.booking_reference);
      navigate(`/bookings/${encodeURIComponent(out.body.booking_reference)}`);
      return;
    }
    setBanner(bannerText(out.code, out.message, out.requestId));
  }, [hold, inFlight]);

  if (!hold) return null;
  const starts = header?.starts_at ?? "";
  return (
    <CheckoutView
      banner={banner}
      title={header?.movie.title ?? ""}
      hall={header?.screen.name ?? ""}
      startsLabel={starts ? `${dayLabel(starts.slice(0, 10))} · ${timeLabel(starts)}` : ""}
      seats={hold.seats}
      money={formatPaise}
      ratio={MINOR_UNIT_RATIO}
      countdown={<HoldCountdown expiresAt={hold.expires_at} now={now} confirmInFlight={inFlight} totalMs={span} />}
      live={!expired}
      expired={expired}
      inFlight={inFlight}
      onPay={() => void onPay()}
      onBack={() => navigate(`/showtimes/${id}`)} // navigation only: there is no client-side release
    />
  );
}
