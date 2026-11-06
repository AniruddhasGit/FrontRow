// SCR-ADM-07 - the four lists a film is built from (P-ADM-23, P-ADM-24). Opens on Languages; the tab is in the URL.
// Withdrawn rows are always listed (include_withdrawn=true): a row the admin cannot see is one they cannot restore.
// No delete control and no edit control: an entry is withdrawn, never removed and never renamed.
import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { api, errorText, ApiError } from "./api";
import { KINDS, usage, type Entry, type Kind } from "./films";

const WITHDRAW_CONFIRM =
  "Withdraw this entry from the list? It stops being offered when a film or showtime is created or edited. Everything already using it is unchanged and still shows it, and you can put it back at any time.";

function kindFromUrl(): Kind {
  const k = new URLSearchParams(window.location.search).get("kind");
  return KINDS.some((x) => x.kind === k) ? (k as Kind) : "language";
}

// The first state, for the render harness (react-dom/server runs no effect). Production passes no seed.
type Seed = { kind: Kind; items: Entry[] };

export function ListsScreen({ seed }: { seed?: Seed }) {
  const [kind, setKind] = useState<Kind>(seed?.kind ?? kindFromUrl());
  const [items, setItems] = useState<Entry[] | null>(seed?.items ?? null);
  const [message, setMessage] = useState("");
  const [name, setName] = useState("");
  const [fieldError, setFieldError] = useState("");
  const load = () =>
    api<{ items: Entry[] }>("GET", `/api/admin/lookups/${kind}?include_withdrawn=true`).then(
      (r) => setItems(r.items),
      () => setMessage("This list cannot be loaded right now. Try again shortly."),
    );
  useEffect(() => {
    if (!seed) void load();
  }, [kind]);
  const choose = (next: Kind) => {
    window.history.replaceState(null, "", `/admin/lookups?kind=${next}`); // reflected in the URL without a navigation
    setKind(next);
    setItems(null);
    setFieldError("");
  };
  const arrows = (e: KeyboardEvent, i: number) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (step) choose(KINDS[(i + step + KINDS.length) % KINDS.length].kind);
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("POST", `/api/admin/lookups/${kind}`, { name });
      setName("");
      setFieldError("");
      void load();
    } catch (err) {
      // The field keeps its value; a name failure is shown on the field (duplicate, withdrawn duplicate, length).
      if (err instanceof ApiError && err.code === "VALIDATION_FAILED") {
        setFieldError(err.message);
        // A withdrawn duplicate: bring the row whose Restore is the remedy into view.
        const hit = items?.find((x) => !x.is_active && x.name.trim().toLowerCase() === name.trim().toLowerCase());
        if (hit) document.getElementById(`entry-${hit.id}`)?.scrollIntoView({ block: "center" });
      } else setMessage(errorText(err));
    }
  };
  const flip = async (entry: Entry) => {
    if (entry.is_active && !window.confirm(WITHDRAW_CONFIRM)) return; // restoring is the undo: not confirmed
    try {
      await api("PATCH", `/api/admin/lookups/${kind}/${entry.id}`, { is_active: !entry.is_active });
      void load();
    } catch (err) {
      setMessage(errorText(err));
    }
  };
  const tab = KINDS.find((k) => k.kind === kind)!;

  return (
    <section className="admin">
      <h1>Lists</h1>
      <p className="lede">The lists a film is built from. A film cannot be saved until it has a language, a certification and at least one genre from these lists.</p>
      <div role="tablist" aria-label="Lists">
        {KINDS.map((k, i) => (
          <button key={k.kind} type="button" role="tab" id={`tab-${k.kind}`} aria-selected={k.kind === kind}
            tabIndex={k.kind === kind ? 0 : -1} onClick={() => choose(k.kind)} onKeyDown={(e) => arrows(e, i)}>
            {k.tab}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-labelledby={`tab-${kind}`}>
        {message ? <p role="alert">{message}</p> : null}
        {items === null && !message ? <ul className="admin-list" aria-busy="true">{[0, 1, 2].map((i) => <li key={i} className="admin-row-loading" />)}</ul> : null}
        {items?.length === 0 ? <p>Nothing on this list yet. Add the first entry.</p> : null}
        {items && items.length > 0 ? (
          <ul className="admin-list" aria-label={tab.tab}>
            {items.map((entry) => (
              <li key={entry.id} id={`entry-${entry.id}`} className={entry.is_active ? "admin-entry" : "admin-entry admin-withdrawn"}
                aria-label={[entry.name, entry.is_active ? null : "withdrawn", usage(kind, entry.reference_count)].filter(Boolean).join(", ")}>
                <span>{entry.name}</span> <span className="admin-mono admin-help">{usage(kind, entry.reference_count)}</span>
                {entry.is_active ? null : (
                  <p className="admin-help">Withdrawn. Not offered on new films or showtimes. Everything already using it still shows it.</p>
                )}
                <button type="button" aria-label={`${entry.is_active ? "Withdraw" : "Restore"} ${entry.name}`} onClick={() => void flip(entry)}>
                  {entry.is_active ? "Withdraw" : "Restore"}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <form className="admin-form" onSubmit={add}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} aria-describedby="lookup-name-error" required />
          </label>
          <p id="lookup-name-error" role="alert">{fieldError}</p>
          <button type="submit">Add to list</button>
        </form>
        <p className="admin-note">Entries are not removed from these lists. A film may already be using one, and removing it would change what that film says.</p>
      </div>
    </section>
  );
}
