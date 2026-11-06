// SCR-ADM-02 - the film editor: the authored fields, the poster panel, the display window and the two gates.
// Every write round-trips the version the last read returned, the poster upload included (P-ADM-12, P-ADM-03).
// The window is typed and shown as NAIVE LOCAL time in the venue's zone and is never converted here (E6 S4).
// The server is the enforcement point for every bound; this form only says them first.
import { useEffect, useState, type FormEvent } from "react";
import { Link, navigate } from "../../router";
import { api, errorText } from "./api";
import { EMPTY_VOCABULARY, windowLine, type Film, type Named } from "./films";

type Vocab = "language" | "certification" | "genre";
type Lookups = Record<Vocab, Named[]>;

const LIMITS = "Posters must be a JPEG, PNG or WebP image, no larger than 2 MB, between 200 by 300 and 4000 by 6000 pixels.";
const PUBLISH_CONFIRM =
  "Publish this film? Customers will see it as soon as the display window starts, and it will keep its showtimes. You can withdraw it again at any time.";
const WITHDRAW_CONFIRM =
  "This film will stop appearing to customers immediately. Showtimes and bookings for it are not changed and nothing is refunded. The film is not deleted and you can publish it again.";

// The venue's local time now, naive, to say whether a closed window is still to come or already over.
function localNow(zone: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(new Date()).map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { film: Film | null; lookups: Lookups; now?: string };

export function FilmEditor({ movieId, seed }: { movieId?: string; seed?: Seed }) {
  const [film, setFilm] = useState<Film | null>(seed?.film ?? null);
  const [lookups, setLookups] = useState<Lookups | null>(seed?.lookups ?? null);
  const [zone, setZone] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(() => fromFilm(seed?.film ?? null));
  useEffect(() => {
    if (seed) return;
    const vocab = (k: Vocab) => api<{ items: Named[] }>("GET", `/api/admin/lookups/${k}`).then((r) => r.items);
    Promise.all([vocab("language"), vocab("certification"), vocab("genre")]).then(
      ([language, certification, genre]) => setLookups({ language, certification, genre }),
      (e) => setMessage(errorText(e)),
    );
    api<{ items: { timezone: string }[] }>("GET", "/api/admin/cinemas").then((r) => setZone(r.items[0]?.timezone ?? ""), () => {});
    if (movieId) api<Film>("GET", `/api/admin/movies/${movieId}`).then(loaded, (e) => setMessage(errorText(e)));
  }, [movieId]);
  const loaded = (next: Film) => {
    setFilm(next);
    setForm(fromFilm(next));
  };
  const set = (key: keyof ReturnType<typeof fromFilm>) => (value: string | string[]) => setForm((f) => ({ ...f, [key]: value }));

  const run = async (write: () => Promise<Film>) => {
    setBusy(true);
    try {
      const next = await write();
      setMessage("");
      if (!film) navigate(`/admin/movies/${next.id}`);
      loaded(next);
    } catch (err) {
      // A version conflict keeps every typed value on screen, so it can be copied before reloading.
      setMessage(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = {
      title: form.title, synopsis: form.synopsis, runtime_minutes: Number(form.runtime),
      certification_id: Number(form.certification), language_id: Number(form.language), genre_ids: form.genres.map(Number),
    };
    if (form.from) body.display_from = form.from;
    if (form.until) body.display_until = form.until;
    void run(() =>
      film
        ? api<Film>("PATCH", `/api/admin/movies/${film.id}`, { version: film.version, ...body })
        : api<Film>("POST", "/api/admin/movies", body), // a new film has no window fields yet (they appear once it is saved)
    );
  };
  const upload = (file: File | undefined) => {
    if (!film || !file) return;
    const data = new FormData();
    data.append("version", String(film.version)); // a form part, never a header or a query parameter
    data.append("file", file);
    void run(() => api<Film>("POST", `/api/admin/movies/${film.id}/poster`, data));
  };
  const gate = (action: "publish" | "unpublish", confirmText: string) => {
    if (film && window.confirm(confirmText)) void run(() => api<Film>("POST", `/api/admin/movies/${film.id}/${action}`, { version: film.version }));
  };

  const select = (kind: Vocab, label: string, multiple = false) =>
    lookups && lookups[kind].length === 0 ? (
      <p className="admin-gate-fail">
        {EMPTY_VOCABULARY[kind]} <Link to="/admin/lookups">Manage lists</Link>
      </p>
    ) : (
      <label>
        {label}
        <select multiple={multiple} value={multiple ? form.genres : form[kind as "language" | "certification"]}
          onChange={(e) => set(multiple ? "genres" : (kind as "language" | "certification"))(
            multiple ? Array.from(e.target.selectedOptions, (o) => o.value) : e.target.value)} required>
          {multiple ? null : <option value="">Choose one</option>}
          {(lookups?.[kind] ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
    );
  const now = seed?.now ?? (zone ? localNow(zone) : "");

  return (
    <section className="admin">
      <h1>{film ? film.title : "New film"}</h1>
      {message ? <p role="alert" className="admin-banner">{message}</p> : null}
      <form className="admin-form" onSubmit={save}>
        <label>
          Title
          <input value={form.title} onChange={(e) => set("title")(e.target.value)} maxLength={200} required />
        </label>
        <label>
          Synopsis
          <textarea value={form.synopsis} onChange={(e) => set("synopsis")(e.target.value)} maxLength={4000} />
        </label>
        <label>
          Runtime, in minutes
          <input className="admin-mono" type="number" min={1} step={1} value={form.runtime} onChange={(e) => set("runtime")(e.target.value)} required />
        </label>
        {select("certification", "Certification")}
        {select("language", "Language")}
        {select("genre", "Genres", true)}
        <p className="admin-help">
          A title of 1 to 200 characters, a synopsis of up to 4000, and a runtime in whole minutes. Choose one language, one certification and at
          least one genre.
        </p>
        {film ? (
          <fieldset>
            <legend>Display window</legend>
            <label>
              Shown from (India time)
              <input className="admin-mono" type="datetime-local" value={form.from} onChange={(e) => set("from")(e.target.value)} />
            </label>
            <label>
              Shown until (India time)
              <input className="admin-mono" type="datetime-local" value={form.until} onChange={(e) => set("until")(e.target.value)} />
            </label>
            <p className="admin-help">
              The film stops being shown at the moment the end date and time is reached. A film shown until 2 Oct 2026, 12:00 am is visible for the
              whole of 1 Oct 2026 and not on 2 Oct 2026.
            </p>
          </fieldset>
        ) : null}
        <button type="submit" disabled={busy}>Save</button>
      </form>
      <section className="admin-form" aria-labelledby="poster-heading">
        <h2 id="poster-heading">Poster</h2>
        <p id="poster-limits" className="admin-help">{LIMITS}</p>
        {film ? (
          <label>
            {busy ? "Uploading…" : film.poster_present ? "Replace poster" : "Upload poster"}
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-describedby="poster-limits" disabled={busy}
              onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        ) : (
          <p>Save this film first, then upload its poster.</p>
        )}
      </section>
      {film ? (
        <section className="admin-form">
          <div role="status" aria-live="polite">
            <p>{film.published ? "Published." : "Not published. Customers cannot see this film."}</p>
            <p>{windowLine(film, now)}</p>
          </div>
          {film.published ? (
            <>
              <button type="button" disabled={busy} onClick={() => gate("unpublish", WITHDRAW_CONFIRM)}>Withdraw from customers</button>
              <p className="admin-note">Films are never deleted. Withdraw a film instead, so that past bookings still make sense.</p>
            </>
          ) : (
            <>
              <button type="button" className="admin-primary" disabled={busy || !film.poster_present || film.display_from === null}
                onClick={() => gate("publish", PUBLISH_CONFIRM)}>Publish</button>
              {!film.poster_present ? <p className="admin-help">This film has no poster. Upload a poster before publishing it.</p> : null}
              {film.display_from === null ? (
                <p className="admin-help">This film has no display window. Set the dates it is shown between before publishing it.</p>
              ) : null}
            </>
          )}
        </section>
      ) : null}
    </section>
  );
}

function fromFilm(film: Film | null) {
  return {
    title: film?.title ?? "", synopsis: film?.synopsis ?? "", runtime: film ? String(film.runtime_minutes) : "",
    certification: film ? String(film.certification_id) : "", language: film ? String(film.language_id) : "",
    genres: (film?.genre_ids ?? []).map(String),
    from: film?.display_from?.slice(0, 16) ?? "", until: film?.display_until?.slice(0, 16) ?? "",
  };
}
