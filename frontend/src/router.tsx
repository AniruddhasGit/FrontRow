// A minimal client-side router on the browser's own History API. No dependency: the product needs a
// path -> screen table and links that do not reload the page, and nothing else (PONYTAIL).
// nginx already falls back to index.html for unknown paths (nginx.conf `location /`), so a deep link
// such as /admin/movies loads the app and this table picks the screen.
//
// FEATURE LANES: add routes in your own feature's routes.tsx, never here. This file only collects them.
import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { adminRoutes } from "./features/admin/routes";
import { authRoutes } from "./features/auth/routes";
import { browseRoutes } from "./features/browse/routes";
// lane p8-reports: /dashboard and /dashboard/audit
import { reportsRoutes } from "./features/reports/routes";

export type RouteParams = Record<string, string>;
export interface AppRoute {
  // "/movies/:movieId" - a ":name" segment matches one path segment and is passed in params.
  path: string;
  render: (params: RouteParams) => ReactNode;
}

const NAVIGATE_EVENT = "fr:navigate";

export function navigate(to: string): void {
  window.history.pushState(null, "", to);
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", update);
    window.addEventListener(NAVIGATE_EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(NAVIGATE_EVENT, update);
    };
  }, []);
  return pathname;
}

export function match(pattern: string, pathname: string): RouteParams | null {
  const want = pattern.split("/").filter(Boolean);
  const got = pathname.split("/").filter(Boolean);
  if (want.length !== got.length) return null;
  const params: RouteParams = {};
  for (let i = 0; i < want.length; i++) {
    if (want[i].startsWith(":")) params[want[i].slice(1)] = decodeURIComponent(got[i]);
    else if (want[i] !== got[i]) return null;
  }
  return params;
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    // A modified click (new tab, new window) keeps the browser's own behaviour.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} onClick={onClick} className={className}>
      {children}
    </a>
  );
}

// Every feature's routes, in one table. First match wins.
export function allRoutes(): AppRoute[] {
  return [...browseRoutes, ...authRoutes, ...adminRoutes, ...reportsRoutes];
}

export function Outlet({ routes, notFound }: { routes: AppRoute[]; notFound: ReactNode }) {
  const pathname = usePathname();
  for (const route of routes) {
    const params = match(route.path, pathname);
    if (params) return <>{route.render(params)}</>;
  }
  return <>{notFound}</>;
}
