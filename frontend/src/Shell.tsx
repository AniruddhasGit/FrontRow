// SCR-XCT-05's nav and account area, filled into the Layout's slots. The role comes from /api/auth/me, re-read on
// every navigation (a sign-in or sign-out changes it). Loading draws fixed-size blocks so the header never resizes;
// a failed check renders as guest and never blocks the page.
// CR-008 T5/T7: the ☰ account menu. A signed-in caller's summary (points, unread count) is read on the same
// navigations, and once more when an account page says it changed something - never on a timer.
import { useEffect, useState, type ReactNode } from "react";
import { type Summary, takeBookmark } from "./features/account/account";
import { AccountMenu } from "./features/account/AccountMenu";
import { signOut } from "./features/account/MyBookingsScreen";
import { leaveForSignIn, signInHref } from "./features/auth/session";
import { get, send } from "./features/browse/api";
import { Layout } from "./layout";
import { currentTo, navFor, shortEmail } from "./nav";
import { Link, usePathname } from "./router";

type Who = "loading" | null | { email: string; role: string };

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [who, setWho] = useState<Who>("loading");
  const [leaving, setLeaving] = useState(false);
  const [summary, setSummary] = useState<Summary | "loading" | "error">("loading");
  const [changed, setChanged] = useState(0);
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
  useEffect(() => {
    const bump = () => setChanged((n) => n + 1);
    window.addEventListener("fr:account-changed", bump);
    return () => window.removeEventListener("fr:account-changed", bump);
  }, []);
  const signedIn = who !== "loading" && who !== null;
  useEffect(() => {
    if (!signedIn) return;
    let live = true;
    // CR-008 T4: a guest's Save survived the sign-in in fr.pending_bookmark; apply it now, once.
    let pending: number | null = null;
    try {
      pending = takeBookmark(window.sessionStorage);
    } catch {
      // no storage: nothing was remembered
    }
    const first = pending ? send("PUT", `/api/me/bookmarks/${pending}`, { saved: true }) : Promise.resolve(null);
    void first.then(() => get<Summary>("/api/me/summary", AbortSignal.timeout(15000)))
      .then((r) => {
        if (!live) return;
        setSummary(r.ok ? r.body : "error");
        if (pending) window.dispatchEvent(new Event("fr:bookmarks-changed")); // the page's Save buttons re-read once
      });
    return () => {
      live = false;
    };
  }, [signedIn, pathname, changed]);

  if (who === "loading") {
    return <Layout nav={<span className="fr-shell-wait" aria-hidden="true" />} account={<span className="fr-shell-wait" aria-hidden="true" />}>{children}</Layout>;
  }
  const doSignOut = () => {
    if (leaving) return;
    setLeaving(true);
    void signOut().finally(() => { setLeaving(false); setWho(null); });
  };
  if (who === null) {
    // From a seat map this link is the second route out, and writes the same fr.pending_selection (P-ACC-13).
    const leave = () => {
      try {
        leaveForSignIn(window.location.pathname, window.sessionStorage, Date.now());
      } catch {
        // no storage: nothing is stored
      }
    };
    const account = (
      <>
        <Link to={signInHref(pathname)} className="fr-signin" before={leave}>Sign in</Link>
        <AccountMenu summary={null} pathname={pathname} onSignOut={doSignOut} leaving={leaving} />
      </>
    );
    return <Layout account={account}>{children}</Layout>;
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
      <AccountMenu summary={summary} pathname={pathname} onSignOut={doSignOut} leaving={leaving} />
    </>
  );
  return <Layout nav={nav} account={account}>{children}</Layout>;
}
