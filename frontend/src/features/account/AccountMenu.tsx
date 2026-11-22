// CR-008 T5: the personal account sidebar - a ☰ button in the header opening a panel from the right.
// A native modal <dialog>: the browser makes the page behind it inert (focus stays inside), Esc closes it, and
// close() hands focus back here, which this file also does by hand for browsers that do not. Its content renders
// only while open, so the closed page carries none of its controls.
import { useEffect, useRef, useState } from "react";
import { Link } from "../../router";
import { signInHref } from "../auth/session";
import { greeting, points, unreadBadge, unreadName, type Summary } from "./account";
import "./account.css";

/** `summary`: null for a guest; "loading" | "error" while the signed-in summary is not there. */
export function AccountMenu({ summary, pathname, onSignOut, leaving }: {
  summary: Summary | null | "loading" | "error"; pathname: string; onSignOut: () => void; leaving: boolean;
}) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const d = dialog.current;
    if (open && d && !d.open) d.showModal();
  }, [open]);
  useEffect(() => {
    dialog.current?.close(); // a navigation closes the panel (a link inside it, or Back)
  }, [pathname]);
  const close = () => dialog.current?.close();
  const unread = typeof summary === "object" && summary ? summary.unread_notifications : 0;
  const badge = unreadBadge(unread);
  return (
    <>
      <button ref={opener} type="button" className="fr-menu-button" aria-haspopup="dialog" aria-expanded={open}
              aria-label={summary === null ? "Account menu" : `Account menu, ${unreadName(unread)}`} onClick={() => setOpen(true)}>
        <span aria-hidden="true">☰</span>
        {badge ? <span className="fr-menu-badge" aria-hidden="true">{badge}</span> : null}
      </button>
      <dialog ref={dialog} className="fr-sidebar" aria-labelledby="fr-sidebar-h"
              onClose={() => { setOpen(false); opener.current?.focus(); }}
              onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
        {open ? (
          <div className="fr-sidebar-inner">
            <div className="fr-sidebar-top">
              <h2 id="fr-sidebar-h">{typeof summary === "object" && summary ? greeting(summary) : summary === null ? "Welcome" : "Your account"}</h2>
              <button type="button" className="fr-sidebar-close" onClick={close} aria-label="Close account menu">×</button>
            </div>
            {summary === null ? (
              <div className="fr-sidebar-nudge">
                <p><strong>Unlock rewards and bookmarks.</strong> Earn points on every booking and save films for later.</p>
                <Link to={signInHref(pathname)} className="fr-action" before={close}>Sign in</Link>
                <Link to="/register" className="fr-action-secondary" before={close}>Create an account</Link>
              </div>
            ) : (
              <p className="fr-sidebar-points">
                {summary === "loading" ? "Loading your points…" : summary === "error" ? "Your points cannot be shown right now."
                  : <><span className="fr-mono">{points(summary.points_balance)}</span> to spend</>}
              </p>
            )}
            <nav aria-label="Account">
              <ul className="fr-sidebar-links">
                {summary === null ? null : (
                  <>
                    <li><Link to="/bookings" before={close}>My bookings</Link></li>
                    <li><Link to="/account/wishlist" before={close}>Wishlist</Link></li>
                    <li><Link to="/account/rewards" before={close}>Rewards</Link></li>
                    <li>
                      <Link to="/account/notifications" before={close}>
                        Notifications{badge ? <><span className="fr-menu-badge fr-menu-badge-inline" aria-hidden="true">{badge}</span>
                          <span className="fr-visually-hidden">, {unreadName(unread)}</span></> : null}
                      </Link>
                    </li>
                    <li><Link to="/account/profile" before={close}>Profile &amp; settings</Link></li>
                  </>
                )}
                <li><Link to="/help" before={close}>Help &amp; support</Link></li>
              </ul>
            </nav>
            {summary === null ? null : (
              <button type="button" className="fr-signout" disabled={leaving} onClick={() => { close(); onSignOut(); }}>Sign out</button>
            )}
          </div>
        ) : null}
      </dialog>
    </>
  );
}
