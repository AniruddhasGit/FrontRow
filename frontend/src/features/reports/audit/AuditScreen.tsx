// SCR-RPT-02 - the change log (/dashboard/audit), administrators only (the server refuses everyone else, P-RPT-11).
// The filters do not auto-submit: Apply sends the whole set as one request. Values are rendered verbatim with their
// field name and never unit-converted. `seed` is the screen's first state, for the render harness.
import { useEffect, useState, type FormEvent } from "react";
import { ReportError, browserGet, errorText, type Get } from "../api";
import { whenText } from "../format";
import { NO_FILTERS, countLine, load, reconcile, type Filters, type Page, type Row } from "./logic";

export interface AuditState {
  draft: Filters; // what the fields hold
  applied: Filters; // what the rows were fetched with
  page: Page | null;
  rows: Row[];
  error: string;
  forbidden: boolean;
  live: string;
}

const FIRST: AuditState = { draft: NO_FILTERS, applied: NO_FILTERS, page: null, rows: [], error: "", forbidden: false, live: "" };

export function AuditScreen({ seed, get = browserGet }: { seed?: Partial<AuditState>; get?: Get }) {
  const [s, setS] = useState<AuditState>({ ...FIRST, ...seed });
  const patch = (p: Partial<AuditState>) => setS((prev) => ({ ...prev, ...p }));

  const run = (f: Filters) => {
    patch({ rows: [], error: "" });
    load(get, f).then((page) => {
      const datesMoved = f.from !== s.applied.from || f.to !== s.applied.to;
      const { filters, notes } = datesMoved ? reconcile(f, page) : { filters: f, notes: [] };
      const settle = (p: Page) => patch({ page: p, rows: p.rows, draft: filters, applied: filters, live: [...notes, countLine(p.rows.length)].join(" ") });
      // A dropped filter is a different query: fetch the rows that match what the controls now show.
      if (filters !== f) load(get, filters).then(settle, fail);
      else settle(page);
    }, fail);
  };
  const fail = (e: unknown) => {
    if (e instanceof ReportError && e.status === 403) patch({ forbidden: true });
    else patch({ error: errorText(e), live: errorText(e) });
  };
  const older = () => {
    if (!s.page?.next_cursor) return;
    load(get, s.applied, s.page.next_cursor).then((p) => patch({ page: p, rows: [...s.rows, ...p.rows], live: countLine(s.rows.length + p.rows.length) }), fail);
  };

  useEffect(() => {
    if (!seed) run(NO_FILTERS);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (s.forbidden) {
    return <section className="rpt-panel"><p>This page is for administrators.</p></section>;
  }
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => patch({ draft: { ...s.draft, [k]: e.target.value } });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(s.draft);
  };
  const actions = s.page?.available_actions ?? [];
  const actors = s.page?.available_actors ?? [];

  return (
    <section className="rpt-panel" aria-labelledby="rpt-audit-heading">
      <h1 id="rpt-audit-heading">Change log</h1>
      <p>Every change an administrator made, with what it was before and what it became.</p>
      <p className="rpt-note">All dates and times are Asia/Kolkata.</p>
      <form className="rpt-filters" onSubmit={submit}>
        <label className="rpt-field">From <input type="date" value={s.draft.from} onChange={set("from")} /></label>
        <label className="rpt-field">To <input type="date" value={s.draft.to} onChange={set("to")} /></label>
        <label className="rpt-field">
          Action
          <select value={s.draft.action} onChange={set("action")}>
            <option value="">Any action</option>
            {actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        {s.page && actions.length === 0 ? <p className="rpt-help">Nothing was changed in this period.</p> : null}
        <label className="rpt-field">Record type <input type="text" maxLength={64} value={s.draft.entityType} onChange={set("entityType")} /></label>
        <label className="rpt-field">
          Record id <input type="text" inputMode="numeric" value={s.draft.entityId} onChange={set("entityId")} disabled={!s.draft.entityType} />
        </label>
        <label className="rpt-field">
          Administrator
          <select value={s.draft.actor} onChange={set("actor")}>
            <option value="">Any administrator</option>
            {actors.map((a) => <option key={a.actor_user_id} value={String(a.actor_user_id)}>{a.actor_email}</option>)}
          </select>
        </label>
        {s.page && actors.length === 0 ? <p className="rpt-help">Nobody changed anything in this period.</p> : null}
        <button type="submit" className="rpt-apply">Apply</button>
      </form>
      {s.error ? <p role="alert" className="rpt-error">{s.error}</p> : null}
      <p className="rpt-count" aria-live="polite">{s.live}</p>
      {s.page && !s.error ? (
        s.rows.length === 0 ? <p className="rpt-state">No changes were recorded in this period.</p> : (
          <div className="rpt-scroll">
            <table className="rpt-table">
              <thead>
                <tr>{["When", "Who", "Action", "Record", "Before", "After"].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
              </thead>
              <tbody>
                {s.rows.map((r) => (
                  <tr key={r.id}>
                    <td>{whenText(r.occurred_at)}</td>
                    <td>{r.actor_email}</td>
                    <td className="rpt-num">{r.action}</td>
                    <td className="rpt-num">{r.entity_type} {r.entity_id}</td>
                    <td><Values values={r.before} /></td>
                    <td><Values values={r.after} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
      {s.page && s.rows.length ? (
        s.page.next_cursor ? <button type="button" onClick={older}>Load older changes</button> : <p className="rpt-note">That is the oldest change in this period.</p>
      ) : null}
    </section>
  );
}

/** Verbatim, with the field name as the term: "base_price_paise 25000". The renderer interprets no unit. */
function Values({ values }: { values: Record<string, unknown> | null }) {
  if (!values) return null;
  return (
    <dl className="rpt-values">
      {Object.entries(values).map(([k, v]) => (
        <div key={k}><dt>{k}</dt><dd className="rpt-num">{typeof v === "string" ? v : JSON.stringify(v)}</dd></div>
      ))}
    </dl>
  );
}
