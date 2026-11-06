// SCR-RPT-02's rules, with no DOM. Both selects are populated from the response alone (available_actions,
// available_actors); no action vocabulary is typed here (P-RPT-11).
import { getJson, type Get } from "../api";

export interface Actor { actor_user_id: number; actor_email: string }
export interface Row {
  id: number; occurred_at: string; actor_user_id: number; actor_email: string; actor_role: string; action: string;
  entity_type: string; entity_id: number; before: Record<string, unknown> | null; after: Record<string, unknown> | null;
}
export interface Page { rows: Row[]; next_cursor: number | null; available_actions: string[]; available_actors: Actor[] }
export interface Filters { from: string; to: string; action: string; entityType: string; entityId: string; actor: string }

export const NO_FILTERS: Filters = { from: "", to: "", action: "", entityType: "", entityId: "", actor: "" };

/** The request for one filter set; an "any" option (empty value) sends no parameter at all. */
export function auditUrl(f: Filters, cursor?: number | null): string {
  const p: [string, string][] = [["from", f.from], ["to", f.to], ["action", f.action], ["entity_type", f.entityType],
    ["entity_id", f.entityType ? f.entityId : ""], ["actor_user_id", f.actor]];
  const parts = p.filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  if (cursor) parts.push(`cursor=${cursor}`);
  return `/api/reports/audit${parts.length ? `?${parts.join("&")}` : ""}`;
}

export function load(get: Get, f: Filters, cursor?: number | null): Promise<Page> {
  return getJson<Page>(get, auditUrl(f, cursor));
}

/** After a date change: a selected option that left its set is dropped and the drop is announced (SCR-RPT-02). */
export function reconcile(f: Filters, page: Page): { filters: Filters; notes: string[] } {
  const notes: string[] = [];
  let next = f;
  if (f.action && !page.available_actions.includes(f.action)) {
    next = { ...next, action: "" };
    notes.push("The action filter was cleared. No change of that kind was recorded in this period.");
  }
  if (f.actor && !page.available_actors.some((a) => String(a.actor_user_id) === f.actor)) {
    next = { ...next, actor: "" };
    notes.push("The administrator filter was cleared. That account made no changes in this period.");
  }
  return { filters: next, notes };
}

export function countLine(n: number): string {
  return n === 1 ? "1 change." : `${n} changes.`;
}
