// SCR-XCT-05's nav, by role, with no DOM: which links a role sees, in order. A link a role may not follow is never
// returned for it (the server's routers stay the authorisation boundary, P-XCT-05).
// Paths are the routes this app actually registers. [JUDGMENT CALL] The PRD table names /account/bookings and
// /admin/pricing; the built routes are /bookings and /admin/seat-categories (pricing lives there), so those are used.
// Run: node --test frontend/src/nav.test.mjs

export type Role = "customer" | "manager" | "admin";
export interface NavLink { label: string; to: string }

const BOOKINGS: NavLink = { label: "My bookings", to: "/bookings" };
const DASHBOARD: NavLink = { label: "Dashboard", to: "/dashboard" };

export function navFor(role: string | null): NavLink[] {
  if (role === "customer") return [BOOKINGS];
  if (role === "manager") return [DASHBOARD, BOOKINGS];
  if (role === "admin") {
    return [DASHBOARD, { label: "Change log", to: "/dashboard/audit" }, { label: "Films", to: "/admin/movies" },
      { label: "Showtimes", to: "/admin/showtimes" }, { label: "Pricing", to: "/admin/seat-categories" },
      { label: "Halls", to: "/admin/halls" }, { label: "Managers", to: "/admin/managers" },
      { label: "Lists", to: "/admin/lookups" }, { label: "Admin access", to: "/admin/access" }, BOOKINGS];
  }
  return []; // guest, or an unknown role: no links (never speculative)
}

/** The link that marks the current area: the longest `to` that is the path or a parent of it. */
export function currentTo(links: NavLink[], pathname: string): string | null {
  const hits = links.filter((l) => pathname === l.to || pathname.startsWith(l.to + "/"));
  return hits.length ? hits.reduce((a, b) => (b.to.length > a.to.length ? b : a)).to : null;
}

/** The address as shown: truncated past 24 characters (the accessible name keeps it whole). */
export function shortEmail(email: string): string {
  return email.length > 24 ? email.slice(0, 23) + "…" : email;
}
