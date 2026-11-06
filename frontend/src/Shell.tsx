// SCR-XCT-05's nav and account area, filled into the Layout's slots. The role comes from /api/auth/me, re-read on
// every navigation (a sign-in or sign-out changes it). Loading draws fixed-size blocks so the header never resizes;
// a failed check renders as guest and never blocks the page.
import { useEffect, useState, type ReactNode } from "react";
import { signOut } from "./features/account/MyBookingsScreen";
import { leaveForSignIn, signInHref } from "./features/auth/session";
import { Layout } from "./layout";
import { currentTo, navFor, shortEmail } from "./nav";
import { Link, usePathname } from "./router";

type Who = "loading" | null | { email: string; role: string };

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [who, setWho] = useState<Who>("loading");
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    let live = true;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => live && setWho(b && typeof b.email === "string" ? { email: b.email, role: String(b.role) } : null))
      .catch(() => live && setWho(null));
    return () => {
      live = false;
    };
  }, [pathname]);

  if (who === "loading") {
    return <Layout nav={<span className="fr-shell-wait" aria-hidden="true" />} account={<span className="fr-shell-wait" aria-hidden="true" />}>{children}</Layout>;
  }
  if (who === null) {
    // From a seat map this link is the second route out, and writes the same fr.pending_selection (P-ACC-13).
    const leave = () => {
      try {
        leaveForSignIn(window.location.pathname, window.sessionStorage, Date.now());
      } catch {
        // no storage: nothing is stored
      }
    };
    return <Layout account={<Link to={signInHref(pathname)} className="fr-signin" before={leave}>Sign in</Link>}>{children}</Layout>;
  }
  const links = navFor(who.role);
  const here = currentTo(links, pathname);
  const nav = links.length ? (
    <>
      {links.map((l) => (
        <Link key={l.to} to={l.to} className={l.to === here ? "fr-nav-link fr-nav-current" : "fr-nav-link"}
              aria-current={l.to === here ? "page" : undefined}>{l.label}</Link>
      ))}
    </>
  ) : undefined;
  const account = (
    <>
      <span className="fr-account-email" aria-label={who.email} title={who.email}>{shortEmail(who.email)}</span>
      <button type="button" className="fr-signout" disabled={leaving}
              onClick={() => { if (leaving) return; setLeaving(true); void signOut().finally(() => { setLeaving(false); setWho(null); }); }}>
        Sign out
      </button>
    </>
  );
  return <Layout nav={nav} account={account}>{children}</Layout>;
}
