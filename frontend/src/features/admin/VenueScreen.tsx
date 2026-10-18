// SCR-ADM-08 - the venue: its name and its IANA zone. No create and no delete (P-ADM-25).
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";
import { plural } from "./text";

interface Cinema {
  id: number;
  name: string;
  timezone: string;
  screen_count: number;
  showtime_count: number;
  version: number;
}

export function VenueScreen() {
  const [items, setItems] = useState<Cinema[] | null>(null);
  const [message, setMessage] = useState("");
  const load = () =>
    api<{ items: Cinema[] }>("GET", "/api/admin/cinemas").then(
      (r) => setItems(r.items),
      () => setMessage("The venue cannot be loaded right now. Try again shortly."),
    );
  useEffect(() => void load(), []);

  return (
    <section className="admin">
      <h1>Venue</h1>
      <p className="lede">The place this system sells tickets for. Halls belong to it, and every time in the product is shown in its time zone.</p>
      {message ? <p role="alert">{message}</p> : null}
      {items?.length === 0 ? <p>There is no venue yet. It is created when the system is set up.</p> : null}
      {items?.map((c) => <VenueForm key={`${c.id}-${c.version}`} cinema={c} onSaved={load} onError={setMessage} />)}
      <p className="admin-note">Venues are not created here. There is one venue and it is created when the system is set up.</p>
      <p className="admin-note">Venues are never deleted.</p>
    </section>
  );
}

function VenueForm({ cinema, onSaved, onError }: { cinema: Cinema; onSaved: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState(cinema.name);
  const [timezone, setTimezone] = useState(cinema.timezone);
  const n = cinema.showtime_count;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (
      timezone !== cinema.timezone &&
      !window.confirm(
        `Change the time zone from ${cinema.timezone} to ${timezone}? Nothing already recorded is altered. ` +
          `${plural(n, "showtime will", "showtimes will")} be shown at a different time from now on, and the dashboard's days will start and end at a different hour.`,
      )
    )
      return;
    try {
      // The version the GET returned goes back with the write (P-ADM-12).
      await api("PATCH", `/api/admin/cinemas/${cinema.id}`, { version: cinema.version, name, timezone });
      onError("");
      onSaved();
    } catch (err) {
      onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      <p>{cinema.screen_count === 0 ? "No halls yet" : plural(cinema.screen_count, "hall", "halls")}</p>
      <label>
        Venue name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
      </label>
      <label>
        Time zone
        <input value={timezone} onChange={(e) => setTimezone(e.target.value)} maxLength={64} required />
      </label>
      <p className="admin-help">
        An IANA time zone name, such as Asia/Kolkata. Every date and time in the product is shown in this zone. Nothing already
        stored is changed by editing it — the times are stored as instants and only what you see changes.
      </p>
      <p className="admin-help">
        Changing the time zone changes the time shown for {plural(n, "showtime", "showtimes")}, and moves the start and end of every
        day, week and month on the dashboard.
      </p>
      <button type="submit">Save venue</button>
    </form>
  );
}
