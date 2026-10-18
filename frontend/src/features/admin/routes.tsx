// Admin screens (/admin/...) - owned by the admin lanes. Add { path, render } entries here;
// src/router.tsx collects them. Authorisation is the server's (the /api/admin router); hiding a screen
// here is convenience, never the control.
import type { AppRoute } from "../../router";
import { Link } from "../../router";
import "./admin.css";
import { CategoriesScreen } from "./CategoriesScreen";
import { HallsScreen } from "./HallsScreen";
import { ManagersScreen } from "./ManagersScreen";
import { ShowtimesScreen } from "./ShowtimesScreen";
import { VenueScreen } from "./VenueScreen";

function AdminHome() {
  return (
    <section className="admin">
      <h1>Administration</h1>
      <ul className="admin-list">
        <li><Link to="/admin/venue">Venue</Link></li>
        <li><Link to="/admin/halls">Halls</Link></li>
        <li><Link to="/admin/seat-categories">Seat categories and pricing</Link></li>
        <li><Link to="/admin/showtimes">Showtimes</Link></li>
        <li><Link to="/admin/managers">Manager accounts</Link></li>
      </ul>
    </section>
  );
}

export const adminRoutes: AppRoute[] = [
  { path: "/admin", render: () => <AdminHome /> },
  { path: "/admin/venue", render: () => <VenueScreen /> },
  { path: "/admin/halls", render: () => <HallsScreen /> },
  { path: "/admin/seat-categories", render: () => <CategoriesScreen /> },
  { path: "/admin/showtimes", render: () => <ShowtimesScreen /> },
  { path: "/admin/managers", render: () => <ManagersScreen /> },
];
