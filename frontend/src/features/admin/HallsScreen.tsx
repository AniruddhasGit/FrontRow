// SCR-ADM-05 - the hall list, hall configuration and the seat editor (P-ADM-13 to P-ADM-16).
// What the server refuses, the server says: the freeze, duplicates and service toggles answer with
// their own sentences and this screen shows them as they arrive.
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";

interface Hall {
  id: number;
  cinema_id: number;
  name: string;
  is_active: boolean;
  seat_count_total: number;
  seat_count_in_service: number;
  has_showtimes: boolean;
  version: number;
}
interface Seat {
  id: number;
  row_label: string;
  seat_number: number;
  grid_row: number;
  grid_col: number;
  seat_category_id: number;
  is_active: boolean;
}
interface Category {
  id: number;
  name: string;
}
interface Cinema {
  id: number;
  name: string;
  timezone: string;
}

export const HALL_WITHDRAWAL_CONFIRMATION =
  "This hall will accept no new showtimes. Showtimes that already exist are not changed, bookings are not cancelled, and nothing is refunded. The hall is not deleted and you can bring it back into service.";

export function HallsScreen() {
  const [halls, setHalls] = useState<Hall[]>([]);
  const [cinemas, setCinemas] = useState<Cinema[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const load = () => api<{ items: Hall[] }>("GET", "/api/admin/screens").then((r) => setHalls(r.items), (e) => setMessage(errorText(e)));
  useEffect(() => {
    void load();
    void api<{ items: Cinema[] }>("GET", "/api/admin/cinemas").then((r) => setCinemas(r.items), (e) => setMessage(errorText(e)));
  }, []);

  return (
    <section className="admin">
      <h1>Halls</h1>
      {message ? <p role="alert">{message}</p> : null}
      {halls.length === 0 ? <p>No halls yet. Create the first one.</p> : null}
      <ul className="admin-list">
        {halls.map((h) => (
          <li key={h.id}>
            <button type="button" className="admin-link" onClick={() => setOpen(open === h.id ? null : h.id)}>
              {h.name}
            </button>{" "}
            {h.seat_count_in_service === h.seat_count_total
              ? `${h.seat_count_total} seats`
              : `${h.seat_count_in_service} of ${h.seat_count_total} seats in service`}
            {" · "}
            {h.has_showtimes ? "Layout fixed — this hall has showtimes" : "Layout can still be changed"}
            {h.is_active ? null : " · Out of service"}
            {open === h.id ? <HallEditor key={h.version} hall={h} onChanged={load} onError={setMessage} /> : null}
          </li>
        ))}
      </ul>
      <NewHall cinemas={cinemas} onCreated={load} onError={setMessage} />
    </section>
  );
}

function NewHall({ cinemas, onCreated, onError }: { cinemas: Cinema[]; onCreated: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState("");
  const [cinemaId, setCinemaId] = useState("");
  if (cinemas.length === 0) return <p>There is no venue yet. A hall cannot be created until one exists.</p>;
  const chosen = cinemas.find((c) => String(c.id) === cinemaId);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("POST", "/api/admin/screens", { cinema_id: Number(cinemaId), name });
      setName("");
      onError("");
      onCreated();
    } catch (err) {
      onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      <h2>New hall</h2>
      <label>
        Venue
        {/* Rendered even with one option: choosing the venue is a decision (P-ADM-25). */}
        <select value={cinemaId} onChange={(e) => setCinemaId(e.target.value)} required>
          <option value="">Choose a venue</option>
          {cinemas.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <p className="admin-help">Every hall belongs to a venue. Times for shows in this hall are shown in the venue's time zone.</p>
      {chosen ? <p className="admin-help">Times shown in {chosen.timezone}</p> : null}
      <label>
        Hall name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
      </label>
      <button type="submit">Create hall</button>
    </form>
  );
}

function HallEditor({ hall, onChanged, onError }: { hall: Hall; onChanged: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState(hall.name);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [draft, setDraft] = useState({ row_label: "", seat_number: "", grid_row: "", grid_col: "", seat_category_id: "" });
  const loadSeats = () =>
    api<{ items: Seat[] }>("GET", `/api/admin/screens/${hall.id}/seats`).then((r) => setSeats(r.items), (e) => onError(errorText(e)));
  useEffect(() => {
    void loadSeats();
    void api<{ items: Category[] }>("GET", "/api/admin/seat-categories").then((r) => setCategories(r.items), (e) => onError(errorText(e)));
  }, [hall.id]);

  const run = async (call: Promise<unknown>, after: () => unknown) => {
    try {
      await call;
      onError("");
      after();
    } catch (err) {
      onError(errorText(err));
    }
  };
  const patchHall = (body: Record<string, unknown>) => run(api("PATCH", `/api/admin/screens/${hall.id}`, { version: hall.version, ...body }), onChanged);
  const rename = (e: FormEvent) => {
    e.preventDefault();
    void patchHall({ name });
  };
  const withdraw = () => {
    if (window.confirm(HALL_WITHDRAWAL_CONFIRMATION)) void patchHall({ is_active: false });
  };
  const addSeat = (e: FormEvent) => {
    e.preventDefault();
    const seat = {
      row_label: draft.row_label,
      seat_number: Number(draft.seat_number),
      grid_row: Number(draft.grid_row),
      grid_col: Number(draft.grid_col),
      seat_category_id: Number(draft.seat_category_id),
    };
    void run(api("POST", `/api/admin/screens/${hall.id}/seats`, { seats: [seat] }), () => {
      void loadSeats();
      onChanged();
    });
  };
  const toggle = (s: Seat) => void run(api("PATCH", `/api/admin/seats/${s.id}`, { is_active: !s.is_active }), loadSeats);
  const remove = (s: Seat) => {
    if (window.confirm("Remove this seat? It has never been part of a showtime, so nothing is lost. Once this hall has a showtime you will not be able to remove a seat at all."))
      void run(api("DELETE", `/api/admin/seats/${s.id}`), loadSeats);
  };
  const field = (key: keyof typeof draft) => ({ value: draft[key], onChange: (e: { target: { value: string } }) => setDraft({ ...draft, [key]: e.target.value }) });

  return (
    <div className="admin-editor">
      <p className="admin-banner">
        {hall.has_showtimes
          ? "This hall has showtimes. You can add seats, move where a seat is drawn, and take a seat in or out of service. You cannot renumber a seat, move it to another category, or remove it."
          : "This hall has no showtimes yet, so its layout can be changed freely. Once you create the first showtime, seat numbers and categories are fixed permanently. Check every seat number now."}
      </p>
      <form className="admin-form" onSubmit={rename}>
        <label>
          Hall name
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
        </label>
        <button type="submit">Save hall</button>
      </form>
      {hall.is_active ? (
        <p>
          <button type="button" onClick={withdraw}>
            Take hall out of service
          </button>{" "}
          <span className="admin-note">Halls are never deleted. Take this hall out of service instead.</span>
        </p>
      ) : (
        <p>
          <span className="admin-note">This hall is out of service. It accepts no new showtimes until you bring it back.</span>{" "}
          <button type="button" onClick={() => void patchHall({ is_active: true })}>
            Bring hall back into service
          </button>
        </p>
      )}
      {seats.length === 0 ? <p>No seats yet. Add the first row.</p> : null}
      <ul className="admin-list">
        {seats.map((s) => (
          <li key={s.id}>
            {s.row_label}
            {s.seat_number} · position {s.grid_row}, {s.grid_col} · {categories.find((c) => c.id === s.seat_category_id)?.name ?? ""}
            {" "}
            <button type="button" onClick={() => toggle(s)}>
              {s.is_active ? "Take out of service" : "Return to service"}
            </button>
            {hall.has_showtimes ? null : (
              <button type="button" onClick={() => remove(s)}>
                Remove seat
              </button>
            )}
          </li>
        ))}
      </ul>
      <p className="admin-help">
        A seat out of service is not offered on showtimes created after now. Showtimes that already exist are not changed, and a seat
        already booked stays booked.
      </p>
      {hall.has_showtimes ? <p className="admin-note">Seats are never deleted once this hall has a showtime. Take a seat out of service instead.</p> : null}
      <form className="admin-form" onSubmit={addSeat}>
        <label>
          Row <input {...field("row_label")} maxLength={4} required />
        </label>
        <label>
          Seat number <input {...field("seat_number")} inputMode="numeric" required />
        </label>
        <label>
          Row position in the map <input {...field("grid_row")} inputMode="numeric" required />
        </label>
        <label>
          Column position in the map <input {...field("grid_col")} inputMode="numeric" required />
        </label>
        <label>
          Seat category
          <select {...field("seat_category_id")} required>
            <option value="">Choose a category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">{seats.length === 0 ? "Add the first seat" : "Add seat"}</button>
      </form>
    </div>
  );
}
