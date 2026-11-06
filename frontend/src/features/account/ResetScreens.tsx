// SCR-ACC-02 · request a reset at /account/reset, and SCR-ACC-03 · choose a new password at /account/reset/confirm.
// The server renders every sentence (P-ACC-07, P-ACC-08), the "expires in N minutes" one included, so the minutes on
// the confirmation panel are PASSWORD_RESET_TTL_SECONDS's and never typed here.
//
// THE TOKEN IS IN THE URL FRAGMENT (#token=...), not the query string: a browser never sends a fragment to a server, so
// no ALB, proxy or request log can record it (app/workers/render.py's [JUDGMENT CALL] on P-ACC-07's link form). It
// is never rendered, never put in a field, and the URL is replaced on success so it does not sit in history.
import { useState, type FormEvent } from "react";
import { Link, navigate } from "../../router";
import "../booking/booking.css";

/** The reset token from a location.hash such as "#token=abc", or null. */
export function tokenFrom(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, "")).get("token");
}

async function post(path: string, body: unknown): Promise<{ ok: boolean; data: any }> {
  const r = await fetch(path, {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).catch(() => null);
  return { ok: !!r?.ok, data: r ? await r.json().catch(() => ({})) : {} };
}

const FAILED = "Something went wrong and your password was not changed.";

export function ResetRequestScreen({ seed = {} }: { seed?: { sent?: string } }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(seed.sent ?? null);
  const [banner, setBanner] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    setFieldError(null);
    const { ok, data } = await post("/api/auth/password-reset/request", { email });
    setBusy(false);
    if (ok) return setSent(data.message);
    const error = data.error ?? {};
    if (error.code === "VALIDATION_FAILED") setFieldError(error.message);
    else setBanner(error.message || "Password reset is unavailable right now. Try again shortly.");
  };

  return (
    <section className="fr-auth">
      <div className="fr-banner-region" aria-live="assertive">{banner ? <p className="fr-banner">{banner}</p> : null}</div>
      <h1>Reset your password</h1>
      {sent ? (
        // The form is replaced: no second send control (SCR-ACC-02 Success).
        <div className="fr-panel" aria-live="polite"><p>{sent}</p></div>
      ) : (
        <form onSubmit={(e) => void submit(e)} noValidate>
          <p>Enter the email address on your account. If it has one, we will send a link that lets you set a new password.</p>
          <label className="fr-form-label" htmlFor="fr-reset-email">Email address</label>
          <input id="fr-reset-email" className="fr-form-field" type="email" autoComplete="email" inputMode="email" value={email}
            aria-describedby={fieldError ? "fr-reset-email-error" : undefined} onChange={(e) => setEmail(e.target.value)} />
          {fieldError ? <p id="fr-reset-email-error" className="fr-field-error" aria-live="polite">{fieldError}</p> : null}
          <button type="submit" className="fr-action" disabled={busy}>Send a reset link</button>
        </form>
      )}
      <Link to="/sign-in">Back to sign in</Link>
    </section>
  );
}

export function ResetConfirmScreen({ token, seed = {} }: { token: string | null; seed?: { tokenError?: string } }) {
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(seed.tokenError ?? null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    setFieldError(null);
    const { ok, data } = await post("/api/auth/password-reset/confirm", { token, password });
    setBusy(false);
    if (ok) {
      // Signed in. Replace the URL first so the token is not left in the address bar or history (SCR-ACC-03).
      // [JUDGMENT CALL] /bookings, the app's my-bookings route; the PRD names /account/bookings, which is not mounted.
      window.history.replaceState(null, "", "/account/reset/confirm");
      return navigate("/bookings");
    }
    const error = data.error ?? {};
    if (error.code === "RESET_TOKEN_INVALID" || (error.code === "VALIDATION_FAILED" && error.details?.field === "token")) {
      setTokenError(error.message);
    } else if (error.code === "VALIDATION_FAILED") {
      setFieldError(error.message); // the field keeps its value and the action stays enabled
    } else {
      setBanner(error.message || FAILED);
    }
  };

  if (tokenError || !token) {
    return (
      <section className="fr-auth">
        <h1>Set a new password</h1>
        <p role="alert">{tokenError ?? "That reset link is not valid. Request a new one."}</p>
        <Link to="/account/reset">Request a new link</Link>
      </section>
    );
  }
  return (
    <section className="fr-auth">
      <div className="fr-banner-region" aria-live="assertive">{banner ? <p className="fr-banner">{banner}</p> : null}</div>
      <h1>Set a new password</h1>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <label className="fr-form-label" htmlFor="fr-new-password">New password</label>
        <input id="fr-new-password" className="fr-form-field" type={shown ? "text" : "password"} autoComplete="new-password"
          value={password} aria-describedby={fieldError ? "fr-new-password-error" : "fr-new-password-help"}
          onChange={(e) => setPassword(e.target.value)} />
        <p id="fr-new-password-help" className="fr-help">At least 12 characters. No numbers or symbols required. Maximum 72 bytes.</p>
        {fieldError ? <p id="fr-new-password-error" className="fr-field-error" aria-live="polite">{fieldError}</p> : null}
        <button type="button" className="fr-link-action" onClick={() => setShown(!shown)}>{shown ? "Hide password" : "Show password"}</button>
        <button type="submit" className="fr-action" disabled={busy}>Set new password</button>
      </form>
    </section>
  );
}
