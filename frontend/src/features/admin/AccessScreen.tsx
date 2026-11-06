// Admin access (SRC-008 ROLE-1 and its ADDENDUM, S-ADM-30): the emails that become admins, EP-ADM-30..32.
// The server decides every rule and writes every refusal; this screen only hides Remove on the caller's own email.
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";

export interface Grant {
  id: number;
  email: string;
}
interface Seed {
  grants: Grant[];
  me: string;
}

export function AccessScreen({ seed }: { seed?: Seed }) {
  const [grants, setGrants] = useState<Grant[]>(seed?.grants ?? []);
  const [me, setMe] = useState(seed?.me ?? "");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const load = () => api<{ items: Grant[] }>("GET", "/api/admin/admin-grants").then((r) => setGrants(r.items), (e) => setMessage(errorText(e)));
  useEffect(() => {
    void load();
    void api<{ email: string }>("GET", "/api/auth/me").then((r) => setMe(r.email), () => undefined);
  }, []);
  const run = async (call: Promise<unknown>, done?: () => void) => {
    try {
      await call;
      setMessage("");
      done?.();
      await load();
    } catch (err) {
      setMessage(errorText(err));
    }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    void run(api("POST", "/api/admin/admin-grants", { email }), () => setEmail(""));
  };

  return (
    <section className="admin" aria-labelledby="access-title">
      <h1 id="access-title">Admin access</h1>
      <p className="admin-help">
        People with these emails become admins when they sign up or sign in. Removing an email makes that person a customer again.
        A manager whose email is added becomes an admin too.
      </p>
      {message ? <p role="alert">{message}</p> : null}
      {grants.length === 0 ? <p>No emails have been given admin access.</p> : null}
      <ul className="admin-list">
        {grants.map((g) => (
          <li key={g.id} className="admin-entry admin-grant">
            <span className="admin-grant-email">{g.email}</span>
            {sameEmail(g.email, me) ? (
              <span className="admin-note">Your email. Another admin can remove it.</span>
            ) : (
              <button type="button" aria-label={`Remove ${g.email}`} onClick={() => void run(api("DELETE", `/api/admin/admin-grants/${g.id}`))}>
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
      <form className="admin-form" onSubmit={add}>
        <h2>Add an email</h2>
        <label>
          Email address <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="off" required />
        </label>
        <button type="submit">Give admin access</button>
      </form>
    </section>
  );
}

/** Addresses are compared the way the server compares them: trimmed, case-insensitively. */
export function sameEmail(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}
