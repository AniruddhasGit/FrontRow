// The application shell (SCR-XCT-05): three landmarks - header, main, footer - and nothing else.
// The guest sees only the wordmark; the role's nav links and the account area (Sign in / Sign out)
// are the account lane's and slot in through `nav` and `account`. The nav is never the authorisation
// boundary - the server's routers are.
import type { ReactNode } from "react";
import "./layout.css";
import { goBack, Link, usePathname } from "./router";

export function Layout({ children, nav, account }: { children: ReactNode; nav?: ReactNode; account?: ReactNode }) {
  const home = usePathname() === "/";
  return (
    <div className="fr-app">
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
      </footer>
    </div>
  );
}
