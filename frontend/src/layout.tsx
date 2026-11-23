// The application shell (SCR-XCT-05): three landmarks - header, main, footer - and nothing else.
// The guest sees only the wordmark; the role's nav links and the account area (Sign in / Sign out)
// are the account lane's and slot in through `nav` and `account`. The nav is never the authorisation
// boundary - the server's routers are.
import { type ReactNode, useEffect, useRef } from "react";
import { Search } from "./features/discover/Search";
import "./layout.css";
import { goBack, Link, usePathname } from "./router";

export function Layout({ children, nav, account }: { children: ReactNode; nav?: ReactNode; account?: ReactNode }) {
  const home = usePathname() === "/";
  const app = useRef<HTMLDivElement>(null);
  // --fr-head: what the hall pages keep clear of - the header's real height (it wraps to 2-3 rows on phones)
  useEffect(() => {
    const head = app.current?.querySelector<HTMLElement>(".fr-header");
    if (!head) return;
    const ro = new ResizeObserver(() => app.current?.style.setProperty("--fr-head", `${head.offsetHeight + 4}px`));
    ro.observe(head);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={app} className="fr-app">
      <a className="fr-skip" href="#main">
        Skip to content
      </a>
      <header className="fr-header">
        <div className="fr-header-inner">
          {home ? null : (
            // CR-007: one dedicated Back on every screen but home, in the same place every time
            <button type="button" className="fr-back" onClick={goBack}>
              <span aria-hidden="true">←</span> Back
            </button>
          )}
          <Link to="/" className="fr-brand">
            FrontRow
          </Link>
          {/* CR-008 T9: search films by title or genre, on every page */}
          <Search />
          {nav ? (
            <nav aria-label="Main" className="fr-nav">
              {nav}
            </nav>
          ) : null}
          <div className="fr-account">{account}</div>
        </div>
      </header>
      <main className="fr-main" id="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="fr-footer">
        <p>Demonstration environment. Payments are simulated and no card details are ever taken.</p>
        {/* CR-008 T8: Help & support is reachable from every page's footer */}
        <p className="fr-footer-links"><Link to="/help">Help &amp; support</Link></p>
      </footer>
    </div>
  );
}
