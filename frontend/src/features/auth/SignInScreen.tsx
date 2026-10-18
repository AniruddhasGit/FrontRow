// SCR-ACC-01 · sign in or register at /sign-in and /register - one screen, two tabs. The server renders every
// failure sentence (P-ACC-01, P-ACC-02); this screen shows it and composes none.
import { useState, type FormEvent } from "react";
import { navigate } from "../../router";
import "../booking/booking.css";
import { CONTEXT_NOTE, destination, pending } from "./session";

type Tab = "sign-in" | "register";

function store() {
  try {
    return window.sessionStorage;
  } catch {
    return { getItem: () => null, removeItem: () => undefined };
  }
}

export function SignInScreen({ initial }: { initial: Tab }) {
  const [tab, setTab] = useState<Tab>(initial);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ field: string; message: string } | null>(null);
  const hasPending = pending(store(), Date.now()) !== null;

  const switchTo = (next: Tab) => {
    setTab(next);
    setPassword(""); // the email survives a tab switch; the password does not
    setBanner(null);
    setFieldError(null);
    window.history.replaceState(null, "", `/${next}${window.location.search}`); // no navigation: back returns to the map
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    setFieldError(null);
    const r = await fetch(tab === "sign-in" ? "/api/auth/login" : "/api/auth/register", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }).catch(() => null);
    setBusy(false);
    if (r && r.ok) {
      navigate(destination(window.location.search, store(), Date.now()));
      return;
    }
    const error = r ? ((await r.json().catch(() => null))?.error ?? {}) : {};
    setPassword("");
    const field = error.details?.field;
    if (field === "email" || field === "password") setFieldError({ field, message: error.message });
    else setBanner(error.message || "Something went wrong and you were not signed in.");
  };

  const err = (field: string) => (fieldError?.field === field ? fieldError.message : null);
  return (
    <section className="fr-auth">
      <div className="fr-banner-region" aria-live="assertive">{banner ? <p className="fr-banner">{banner}</p> : null}</div>
      <div role="tablist" aria-label="Account" className="fr-tabs">
        {(["sign-in", "register"] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className="fr-tab" onClick={() => switchTo(t)}>
            {t === "sign-in" ? "Sign in" : "Register"}
          </button>
        ))}
      </div>
      {hasPending ? <p className="fr-context-note">{CONTEXT_NOTE}</p> : null}
      <form role="tabpanel" onSubmit={(e) => void submit(e)} noValidate>
        <label className="fr-form-label" htmlFor="fr-email">Email address</label>
        <input id="fr-email" className="fr-form-field" type="email" autoComplete="email" inputMode="email" value={email}
          aria-describedby={err("email") ? "fr-email-error" : undefined} onChange={(e) => setEmail(e.target.value)} />
        {err("email") ? <p id="fr-email-error" className="fr-field-error" aria-live="polite">{err("email")}</p> : null}
        <label className="fr-form-label" htmlFor="fr-password">Password</label>
        <input id="fr-password" className="fr-form-field" type={shown ? "text" : "password"} value={password}
          autoComplete={tab === "sign-in" ? "current-password" : "new-password"}
          aria-describedby={err("password") ? "fr-password-error" : tab === "register" ? "fr-password-help" : undefined}
          onChange={(e) => setPassword(e.target.value)} />
        {tab === "register" ? (
          <p id="fr-password-help" className="fr-help">At least 12 characters. No numbers or symbols required. Maximum 72 bytes.</p>
        ) : null}
        {err("password") ? <p id="fr-password-error" className="fr-field-error" aria-live="polite">{err("password")}</p> : null}
        <button type="button" className="fr-link-action" onClick={() => setShown(!shown)}>{shown ? "Hide password" : "Show password"}</button>
        <button type="submit" className="fr-action" disabled={busy}>{tab === "sign-in" ? "Sign in" : "Create account"}</button>
      </form>
    </section>
  );
}
