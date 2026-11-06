// SCR-RPT-01 - the dashboard (/dashboard). Read only: no control here writes anything or produces a file (P-RPT-09/10).
// The four figures come from EP-RPT-01 alone and render together or not at all (P-RPT-07); hall names come from
// EP-RPT-03 alone. `seed` is the screen's first state, so the render harness can show any state an effect would set.
import { useEffect, useState } from "react";
import { Link } from "../../../router";
import { browserGet, errorText, getJson, type Get } from "../api";
import { formatPaise, paiseWords, pctText, pctWords, whenText } from "../format";
import {
  DEFAULT_SORT, FILM_COLUMNS, PERIODS, dashboardUrl, figuresSentence, hallOptions, headerName, isManager, openingLoad,
  periodLine, positionLine, scopeLine, shift, showsUrl, sortFilms, stepperNames, toggle,
  type Dashboard, type Loaded, type Period, type Query, type Scope, type Shows, type Sort,
} from "./logic";

export interface DashboardState {
  query: Query;
  scope: Scope | null;
  dash: Dashboard | null; // null while the figures request is pending: every figure shows its loading block
  shows: Shows | null;
  error: string;
  sort: Sort;
  live: string;
}

const FIRST: DashboardState = {
  query: { period: "day", anchor: null, screenId: "", offset: 0 }, scope: null, dash: null, shows: null, error: "",
  sort: DEFAULT_SORT, live: "Loading figures.",
};

export function DashboardScreen({ seed, get = browserGet }: { seed?: Partial<DashboardState>; get?: Get }) {
  const [s, setS] = useState<DashboardState>({ ...FIRST, ...seed });
  const patch = (p: Partial<DashboardState>) => setS((prev) => ({ ...prev, ...p }));

  useEffect(() => {
    if (seed) return;
    void openingLoad(get, FIRST.query, (part: Loaded) => {
      if (part.error) patch({ error: errorText(part.error), dash: null, live: errorText(part.error) });
      else patch(part as Partial<DashboardState>);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // The local anchor: EP-RPT-03's today until the reader steps. Never the device's date.
  const anchor = s.query.anchor ?? s.scope?.today ?? null;

  const reload = (q: Query) => {
    // The previous period's figures are CLEARED, never left beside a live tab (SCR-RPT-01 Loading).
    patch({ query: q, dash: null, shows: null, error: "", live: "Loading figures." });
    getJson<Dashboard>(get, dashboardUrl(q)).then(async (dash) => {
      const label = PERIODS.find(([p]) => p === q.period)?.[1];
      const at = q.anchor ?? anchor;
      const line = at ? periodLine(at, q.period) : "";
      patch({ dash, live: `${label}, ${line}. ${figuresSentence(dash)}`.trim() });
      if (!dash.scope_empty) patch({ shows: await getJson<Shows>(get, showsUrl(q)) });
    }).catch((e) => patch({ error: errorText(e), dash: null, live: errorText(e) }));
  };
  const page = (offset: number) => {
    const q = { ...s.query, offset };
    patch({ query: q });
    getJson<Shows>(get, showsUrl(q)).then((shows) => patch({ shows, live: positionLine(shows) }), (e) => patch({ error: errorText(e) }));
  };

  const manager = isManager(s.scope);
  const empty = s.dash?.scope_empty === true;
  const [prev, next] = stepperNames(s.query.period);

  return (
    <section className="rpt-panel" aria-labelledby="rpt-heading">
      <h1 id="rpt-heading">Dashboard</h1>
      <p className="rpt-note">All dates and times are Asia/Kolkata.</p>
      {s.dash && !empty ? (
        <p className="rpt-note rpt-live-note">
          These figures are recomputed from current records each time this page loads.
          {manager ? " If a figure has changed, ask an administrator to check the change log." : ""}
        </p>
      ) : null}

      <div role="tablist" aria-label="Period" className="rpt-tabs">
        {PERIODS.map(([p, label]) => (
          <button key={p} type="button" role="tab" aria-selected={s.query.period === p} tabIndex={s.query.period === p ? 0 : -1}
            onClick={() => reload({ ...s.query, period: p as Period, offset: 0 })}>{label}</button>
        ))}
      </div>
      {anchor ? (
        <>
          <div className="rpt-stepper">
            <button type="button" onClick={() => reload({ ...s.query, anchor: shift(anchor, s.query.period, -1), offset: 0 })}>{prev}</button>
            <button type="button" onClick={() => reload({ ...s.query, anchor: shift(anchor, s.query.period, 1), offset: 0 })}>{next}</button>
          </div>
          <p className="rpt-period">{periodLine(anchor, s.query.period)}</p>
        </>
      ) : null}

      {s.scope && s.dash && !empty ? <p className="rpt-scope">{scopeLine(s.scope, s.dash)}</p> : null}
      {s.scope && !s.scope.scope_empty && !empty ? (
        <label className="rpt-field">
          Hall
          <select value={s.query.screenId} onChange={(e) => reload({ ...s.query, screenId: e.target.value, offset: 0 })}>
            {hallOptions(s.scope).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      ) : null}
      {s.scope && !manager ? <Link to="/dashboard/audit" className="rpt-link">Change log</Link> : null}

      {s.error ? <p role="alert" className="rpt-error">{s.error}</p> : <Figures dash={s.dash} />}

      {s.dash && !empty && !s.error ? (
        <>
          <FilmTable films={s.dash.films} sort={s.sort} manager={manager} onSort={(key) => patch({ sort: toggle(s.sort, key) })} />
          {s.dash.films_truncated ? (
            <p className="rpt-note">Showing the top 100 films by takings. The figures above cover every film in this period.</p>
          ) : null}
          {s.shows ? <ShowTable shows={s.shows} onPage={page} /> : null}
        </>
      ) : null}
      <p className="rpt-sr" aria-live="polite">{s.live}</p>
    </section>
  );
}

function Figures({ dash }: { dash: Dashboard | null }) {
  const empty = dash?.scope_empty === true;
  const cell = (label: string, value: string | null, spoken: string) => (
    <p className="rpt-figure">
      <span className="rpt-label" aria-hidden="true">{label}</span>
      {value === null ? <span className="rpt-loading" aria-hidden="true" /> : <span className="rpt-value" aria-hidden="true">{value}</span>}
      {value === null ? null : <span className="rpt-sr">{spoken}</span>}
    </p>
  );
  const dash0 = dash && !empty ? dash : null;
  const takings = dash0 ? formatPaise(dash0.takings_paise) : empty ? "—" : null;
  const occupancy = dash0 ? pctText(dash0.occupancy_pct) : empty ? "—" : null;
  const sold = dash0 ? String(dash0.seats_sold) : empty ? "—" : null;
  const shows = dash0 ? String(dash0.shows) : empty ? "—" : null;
  let line = "";
  if (empty) line = "No halls are assigned to this account. Ask an administrator to assign one.";
  else if (dash0 && dash0.capacity === 0) line = "No shows were scheduled in this period.";
  else if (dash0 && dash0.seats_sold === 0) line = "No seats were sold in this period.";
  return (
    <div className="rpt-figures">
      {cell("TAKINGS", takings, dash0 ? `Takings, ${paiseWords(dash0.takings_paise)}` : "Takings, —")}
      {cell("OCCUPANCY", occupancy, dash0 && dash0.occupancy_pct !== null ? `Occupancy, ${pctWords(dash0.occupancy_pct)}` : "Occupancy, —")}
      {dash0 && dash0.occupancy_pct !== null ? (
        <div className="rpt-bar" aria-hidden="true"><div className="rpt-bar-fill" style={{ width: `${dash0.occupancy_pct}%` }} /></div>
      ) : null}
      {cell("SEATS SOLD", sold, `Seats sold, ${sold}`)}
      {cell("SHOWS", shows, `Shows, ${shows}`)}
      {line ? <p className="rpt-state">{line}</p> : null}
    </div>
  );
}

function FilmTable({ films, sort, manager, onSort }: { films: Dashboard["films"]; sort: Sort; manager: boolean; onSort: (k: Sort["key"]) => void }) {
  return (
    <div className="rpt-scroll">
      <table className="rpt-table">
        <caption>{manager ? "Per film, in your halls" : "Per film"}</caption>
        <thead>
          <tr>
            {FILM_COLUMNS.map(([key, label]) => (
              <th key={key} scope="col" aria-sort={sort.key === key ? (sort.dir === "desc" ? "descending" : "ascending") : "none"}>
                <button type="button" aria-label={headerName(label, key, sort)} onClick={() => onSort(key)}>{label}</button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortFilms(films, sort).map((f) => (
            <tr key={f.movie_id} data-movie-id={f.movie_id}>
              <td>{f.title}</td>
              <td className="rpt-num">{f.shows}</td>
              <td className="rpt-num">{f.seats_sold}</td>
              <td className="rpt-num">{f.capacity}</td>
              <td className="rpt-num">{pctText(f.occupancy_pct)}</td>
              <td className="rpt-num">{formatPaise(f.takings_paise)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShowTable({ shows, onPage }: { shows: Shows; onPage: (offset: number) => void }) {
  const earlier = shows.offset > 0;
  const later = shows.offset + shows.rows.length < shows.total;
  return (
    <>
      <div className="rpt-scroll" tabIndex={0}>
        <table className="rpt-table">
          <caption>Every show in this period</caption>
          <thead>
            <tr>{["Start", "Hall", "Film", "Seats sold", "Capacity", "Occupancy", "Takings"].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
          </thead>
          <tbody>
            {shows.rows.map((r) => (
              <tr key={r.showtime_id}>
                <td>{whenText(r.starts_at)}{r.has_started ? null : <span className="rpt-marker">Still selling</span>}</td>
                <td>{r.screen_name}</td>
                <td>{r.title}</td>
                <td className="rpt-num">{r.seats_sold}</td>
                <td className="rpt-num">{r.capacity}</td>
                <td className="rpt-num">{pctText(r.occupancy_pct)}</td>
                <td className="rpt-num">{formatPaise(r.takings_paise)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shows.total === 0 ? <p className="rpt-state">No shows were scheduled in this period.</p> : null}
      <div className="rpt-pager">
        {earlier ? <button type="button" onClick={() => onPage(Math.max(0, shows.offset - shows.limit))}>Earlier shows</button> : null}
        <p className="rpt-position">{positionLine(shows)}</p>
        {later ? <button type="button" onClick={() => onPage(shows.offset + shows.limit)}>Later shows</button> : null}
      </div>
    </>
  );
}
