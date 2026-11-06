// SCR-ADM-03 - one hall's day, and the form that creates or edits a showtime (P-ADM-07 to P-ADM-10).
// Times are naive local in the venue's zone, both ways; nothing here converts a time (E6 S4).
// The base price is typed in dollars and sent as integer cents (money.ts).
// The film is chosen by id until the admin film list exists (EP-ADM-01, Phase 6).
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";
import { formatPaise, paiseToRupeesText, showtimeBody } from "./money";
import { plural } from "./text";

interface Hall {
  id: number;
  name: string;
}
interface Showtime {
  id: number;
  movie_id: number;
  movie_title: string;
  starts_at: string;
  ends_at: string;
  base_price_paise: number;
  seat_count_at_creation: number;
  booked_seat_count: number;
  version: number;
}

export const NEVER_DELETED =
  "Showtimes are never deleted, and v1 has no way to cancel one. Check the film, the hall and the times before you create it.";

const clock = (iso: string) => {
  const [h, m] = iso.slice(11, 16).split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { halls: Hall[]; hallId: string; date: string; day: Showtime[]; editing?: Showtime };

export function ShowtimesScreen({ seed }: { seed?: Seed }) {
  const [halls, setHalls] = useState<Hall[]>(seed?.halls ?? []);
  const [hallId, setHallId] = useState(seed?.hallId ?? "");
  const [date, setDate] = useState(seed?.date ?? "");
  const [hideStarted, setHideStarted] = useState(false);
  const [day, setDay] = useState<Showtime[]>(seed?.day ?? []);
  const [editing, setEditing] = useState<Showtime | null>(seed?.editing ?? null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void api<{ items: Hall[] }>("GET", "/api/admin/screens").then((r) => setHalls(r.items), (e) => setMessage(errorText(e)));
  }, []);
  const load = () => {
    if (!hallId || !date) return;
    const query = new URLSearchParams({ screen_id: hallId, date, include_past: hideStarted ? "false" : "true" });
    void api<{ items: Showtime[] }>("GET", `/api/admin/showtimes?${query}`).then((r) => setDay(r.items), (e) => setMessage(errorText(e)));
  };
  useEffect(load, [hallId, date, hideStarted]);
  const hall = halls.find((h) => String(h.id) === hallId);

  return (
    <section className="admin">
      <h1>Showtimes</h1>
      {message ? <p role="alert">{message}</p> : null}
      <div className="admin-form">
        <label>
          Hall
          <select value={hallId} onChange={(e) => setHallId(e.target.value)}>
            <option value="">Choose a hall</option>
            {halls.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          <input type="checkbox" checked={hideStarted} onChange={(e) => setHideStarted(e.target.checked)} /> Hide showtimes that have already
          started
        </label>
        <p className="admin-help">A showtime counts as started at its advertised start time. Sales for it may still be open.</p>
      </div>
      {hallId && date ? (
        <>
          <p aria-live="polite">{day.length === 0 ? "No showtimes on this hall for this date" : `${plural(day.length, "showtime", "showtimes")} on this hall for this date`}</p>
          <ol className="admin-list" aria-label={`Showtimes on ${hall?.name ?? ""} on ${date}`}>
            {day.map((s) => (
              <li key={s.id}>
                <button type="button" className="admin-link" onClick={() => setEditing(s)}>
                  {clock(s.starts_at)} to {clock(s.ends_at)} · {s.movie_title} · {formatPaise(s.base_price_paise)} base
                </button>{" "}
                {s.booked_seat_count === 0 ? "No seats booked yet" : `${s.booked_seat_count} of ${s.seat_count_at_creation} seats booked`}
              </li>
            ))}
          </ol>
        </>
      ) : null}
      <p className="admin-note">{NEVER_DELETED}</p>
      <ShowtimeForm key={editing ? `${editing.id}-${editing.version}` : "new"} hallId={hallId} editing={editing}
        onDone={() => { setEditing(null); setMessage(""); load(); }} onError={setMessage} />
      <p className="admin-help">Sales for this showtime close 15 minutes after the advertised start. A customer already holding seats can finish paying after that.</p>
    </section>
  );
}

function ShowtimeForm({ hallId, editing, onDone, onError }: { hallId: string; editing: Showtime | null; onDone: () => void; onError: (m: string) => void }) {
  const [form, setForm] = useState({
    movie_id: editing ? String(editing.movie_id) : "",
    screen_id: hallId,
    starts_at: editing?.starts_at.slice(0, 16) ?? "",
    ends_at: editing?.ends_at.slice(0, 16) ?? "",
    rupees: editing ? paiseToRupeesText(editing.base_price_paise) : "",
  });
  const set = (key: keyof typeof form) => ({ value: form[key], onChange: (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value }) });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = showtimeBody({ ...form, screen_id: form.screen_id || hallId });
    try {
      if (editing) {
        const { movie_id, starts_at, ends_at, base_price_paise } = body;
        await api("PATCH", `/api/admin/showtimes/${editing.id}`, { version: editing.version, movie_id, starts_at, ends_at, base_price_paise });
      } else {
        await api("POST", "/api/admin/showtimes", body);
      }
      onDone();
    } catch (err) {
      onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      <h2>{editing ? "Edit showtime" : "New showtime"}</h2>
      <label>
        Film <input {...set("movie_id")} inputMode="numeric" required />
      </label>
      <label>
        Starts (India time) <input type="datetime-local" {...set("starts_at")} required />
      </label>
      <label>
        Ends (India time) <input type="datetime-local" {...set("ends_at")} required />
      </label>
      <label>
        Base price <input {...set("rupees")} inputMode="decimal" required />
      </label>
      <button type="submit">{editing ? "Save changes" : "Create showtime"}</button>{" "}
      {editing ? (
        <button type="button" onClick={onDone}>
          Discard this form
        </button>
      ) : null}
    </form>
  );
}
