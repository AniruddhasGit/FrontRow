// SCR-ADM-04 - seat categories and pricing (P-ADM-11). The confirmation states the server's own
// affected_future_showtimes figure, never one this screen counted itself.
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";
import { formatPaise } from "./money";
import { plural } from "./text";

interface Category {
  id: number;
  name: string;
  uplift_basis_points: number;
  seat_count: number;
  version: number;
}
interface Listing {
  items: Category[];
  affected_future_showtimes: number;
  evaluated_at_utc: string;
}

const percent = (bp: number) => `${bp / 100} percent`;

export function CategoriesScreen() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [message, setMessage] = useState("");
  const load = () => api<Listing>("GET", "/api/admin/seat-categories").then(setListing, (e) => setMessage(errorText(e)));
  useEffect(() => void load(), []);
  const n = listing?.affected_future_showtimes ?? 0;

  return (
    <section className="admin">
      <h1>Seat categories and pricing</h1>
      {message ? <p role="alert">{message}</p> : null}
      <p className="admin-banner">
        {n === 0
          ? "This uplift applies to every hall and every show. There are no showtimes still selling, so changing it changes no price today."
          : `This uplift applies to every hall and every show. Changing it changes the price of ${plural(n, "future showtime", "future showtimes")}.`}
      </p>
      <p className="admin-help">
        A showtime counts here while it can still take a booking. Sales close 15 minutes after the advertised start, so a show that has
        just begun is counted.
      </p>
      <p className="admin-help">There is no per-hall and no per-film category pricing. One uplift per category, everywhere.</p>
      {listing?.items.map((c) => (
        <CategoryForm key={`${c.id}-${c.version}`} category={c} affected={n} onSaved={load} onError={setMessage} />
      ))}
      <NewCategory onCreated={load} onError={setMessage} />
      <p className="admin-note">
        The category names Standard, Premium and Recliner were chosen by the build session, not specified by you. Rename them freely.
      </p>
    </section>
  );
}

function CategoryForm({ category, affected, onSaved, onError }: { category: Category; affected: number; onSaved: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState(category.name);
  const [uplift, setUplift] = useState(String(category.uplift_basis_points));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next = Number(uplift);
    if (
      next !== category.uplift_basis_points &&
      !window.confirm(
        `Change ${category.name} from ${percent(category.uplift_basis_points)} to ${percent(next)}? This affects ` +
          `${plural(affected, "future showtime", "future showtimes")} in every hall. Customers already holding seats keep the price they were shown.`,
      )
    )
      return;
    try {
      await api("PATCH", `/api/admin/seat-categories/${category.id}`, { version: category.version, name, uplift_basis_points: next });
      onError("");
      onSaved();
    } catch (err) {
      onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      <label>
        Category name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required />
      </label>
      <label>
        Uplift, in basis points
        <input value={uplift} onChange={(e) => setUplift(e.target.value)} inputMode="numeric" required />
      </label>
      <p className="admin-help">
        {Number(uplift)} basis points is {Number(uplift) / 100} percent · {category.seat_count} seats
      </p>
      <button type="submit">Save pricing</button>
    </form>
  );
}

function NewCategory({ onCreated, onError }: { onCreated: () => void; onError: (m: string) => void }) {
  const [name, setName] = useState("");
  const [uplift, setUplift] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("POST", "/api/admin/seat-categories", { name, uplift_basis_points: Number(uplift) });
      setName("");
      setUplift("");
      onError("");
      onCreated();
    } catch (err) {
      onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      <h2>New seat category</h2>
      <label>
        Category name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required />
      </label>
      <label>
        Uplift, in basis points
        <input value={uplift} onChange={(e) => setUplift(e.target.value)} inputMode="numeric" required />
      </label>
      <p className="admin-help">
        100 basis points is 1 percent. A base price of {formatPaise(25000)} with an uplift of 1250 gives a seat price of {formatPaise(28125)}.
      </p>
      <button type="submit">Create category</button>
    </form>
  );
}
