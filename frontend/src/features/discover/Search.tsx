// CR-008 T9: the header search. Films by title or genre as you type: the request waits for a 250 ms pause in typing,
// the previous one is aborted, and an answer is kept only for the query it was asked for (web-app-pitfalls rule 3), so
// an old answer never overwrites a newer one. ARIA 1.2 combobox with a listbox popup: arrows move through the results,
// Enter opens the active film (or the first), Escape closes, then clears. One status union (discover.ts Search).
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { navigate } from "../../router";
import { get } from "../browse/api";
import { answered, moveActive, SEARCH_WAIT_MS, wants, type Hit, type Search as Status } from "./discover";
import "./discover.css";

export function Search() {
  const id = useId();
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLDivElement>(null);
  const q = wants(text);

  useEffect(() => {
    if (q === null) {
      setStatus({ kind: "idle" });
      return;
    }
    const ctl = new AbortController();
    // the debounce: a timer that fires once per pause in typing, cleared by the next key (not a poll)
    const t = window.setTimeout(() => {
      setStatus({ kind: "loading", q });
      // a search that never answers ends as an error after 10 s (web-app-pitfalls rule 2)
      const signal = AbortSignal.any([ctl.signal, AbortSignal.timeout(10_000)]);
      void get<{ items: Hit[] }>(`/api/search?q=${encodeURIComponent(q)}`, signal).then((r) => {
        if (ctl.signal.aborted) return;
        setStatus((s) => answered(s, q, r.ok ? { ok: true, items: r.body.items } : { ok: false }));
        setActive(-1);
      });
    }, SEARCH_WAIT_MS);
    return () => {
      window.clearTimeout(t);
      ctl.abort();
    };
  }, [q]);

  // A click anywhere outside closes the list (focus leaving does the same below).
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  const items = status.kind === "results" ? status.items : [];
  const shown = open && status.kind !== "idle";
  const choose = (hit: Hit) => {
    setOpen(false);
    setText("");
    navigate(`/movies/${hit.id}`);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => moveActive(a, items.length, e.key as "ArrowDown" | "ArrowUp"));
    } else if (e.key === "Enter") {
      const hit = items[active] ?? (active === -1 ? items[0] : undefined);
      if (hit) {
        e.preventDefault();
        choose(hit);
      }
    } else if (e.key === "Escape") {
      if (open && status.kind !== "idle") setOpen(false);
      else setText("");
    }
  };
  const optionId = (i: number) => `${id}-opt-${i}`;

  return (
    <div className="fr-search" ref={box} role="search"
         onBlur={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && setOpen(false)}>
      <label htmlFor={`${id}-q`} className="fr-visually-hidden">Search films by title or genre</label>
      <span className="fr-search-icon" aria-hidden="true">⌕</span>
      <input id={`${id}-q`} className="fr-search-input" type="search" role="combobox" autoComplete="off" spellCheck={false}
             placeholder="Search films or genres" value={text} maxLength={100}
             aria-expanded={shown} aria-controls={`${id}-list`} aria-autocomplete="list"
             aria-activedescendant={shown && active >= 0 && items[active] ? optionId(active) : undefined}
             onChange={(e) => { setText(e.target.value); setOpen(true); setActive(-1); }}
             onFocus={() => setOpen(true)} onKeyDown={onKey} />
      <div className="fr-search-pop" hidden={!shown}>
        <ul id={`${id}-list`} role="listbox" aria-label="Films found" className="fr-search-list">
          {items.map((hit, i) => (
            <li key={hit.id} id={optionId(i)} role="option" aria-selected={i === active} className="fr-search-option"
                onPointerDown={(e) => e.preventDefault()} onClick={() => choose(hit)} onPointerEnter={() => setActive(i)}>
              <img src={hit.poster_url} alt="" width={32} height={48} loading="lazy" />
              <span className="fr-search-text">
                <span className="fr-search-title">{hit.title}</span>
                <span className="fr-search-genres">{hit.genres.map((g) => g.name).join(" · ")}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="fr-search-state" role="status">
          {status.kind === "loading" ? "Searching…"
            : status.kind === "error" ? "Search is not available right now. Try again in a moment."
            : status.kind === "results" && items.length === 0 ? `No films match "${status.q}".`
            : status.kind === "results" ? `${items.length} ${items.length === 1 ? "film" : "films"} found.` : ""}
        </p>
      </div>
    </div>
  );
}
