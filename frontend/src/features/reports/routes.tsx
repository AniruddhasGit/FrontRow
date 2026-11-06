// The reporting screens (/dashboard, /dashboard/audit) - lane p8-reports. src/router.tsx collects them. Authorisation
// is the server's (the /api/reports routers); a screen the server refuses renders the refusal it was sent.
import type { AppRoute } from "../../router";
import { AuditScreen } from "./audit/AuditScreen";
import { DashboardScreen } from "./dashboard/DashboardScreen";
import "./reports.css";

export const reportsRoutes: AppRoute[] = [
  { path: "/dashboard", render: () => <DashboardScreen /> },
  { path: "/dashboard/audit", render: () => <AuditScreen /> },
];
