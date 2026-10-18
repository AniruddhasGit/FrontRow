// SCR-ADM-06 - manager accounts and the halls each can see (P-ADM-17). No password is typed here.
import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "./api";

interface Manager {
  user_id: number;
  email: string;
  assigned_screen_ids: number[];
  has_signed_in: boolean;
}
interface Hall {
  id: number;
  name: string;
}

export function ManagersScreen() {
  const [managers, setManagers] = useState<Manager[]>([]);
  const [halls, setHalls] = useState<Hall[]>([]);
  const [message, setMessage] = useState("");
  const load = () => api<{ items: Manager[] }>("GET", "/api/admin/managers").then((r) => setManagers(r.items), (e) => setMessage(errorText(e)));
  useEffect(() => {
    void load();
    void api<{ items: Hall[] }>("GET", "/api/admin/screens").then((r) => setHalls(r.items), (e) => setMessage(errorText(e)));
  }, []);

  return (
    <section className="admin">
      <h1>Manager accounts</h1>
      {message ? <p role="alert">{message}</p> : null}
      <p className="admin-help">
        A manager can only view figures for the halls assigned to them. They cannot add or change films, showtimes, prices or halls.
      </p>
      {managers.length === 0 ? <p>No manager accounts yet.</p> : null}
      {managers.map((m) => (
        <HallPicker key={`${m.user_id}-${m.assigned_screen_ids.join(",")}`} title={m.email} note={m.has_signed_in ? "" : "Has not signed in yet"}
          halls={halls} initial={m.assigned_screen_ids} action="Save halls" onSubmit={(ids) => api("PUT", `/api/admin/managers/${m.user_id}/screens`, { screen_ids: ids })}
          onDone={load} onError={setMessage} />
      ))}
      <NewManager halls={halls} onDone={load} onError={setMessage} />
    </section>
  );
}

function NewManager({ halls, onDone, onError }: { halls: Hall[]; onDone: () => void; onError: (m: string) => void }) {
  const [email, setEmail] = useState("");
  return (
    <div>
      <h2>New manager</h2>
      <label>
        Email address <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} required />
      </label>
      <p className="admin-help">You do not set a password. The manager sets their own by using the password reset link on the sign-in page.</p>
      <p className="admin-help">
        Creating this account does not send anything. Tell the manager it exists and ask them to use the password reset link on the sign-in
        page with this address.
      </p>
      <HallPicker key="new" title="" note="" halls={halls} initial={[]} action="Create manager"
        onSubmit={(ids) => api("POST", "/api/admin/managers", { email, screen_ids: ids })} onDone={() => { setEmail(""); onDone(); }} onError={onError} />
    </div>
  );
}

function HallPicker(props: {
  title: string;
  note: string;
  halls: Hall[];
  initial: number[];
  action: string;
  onSubmit: (ids: number[]) => Promise<unknown>;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [chosen, setChosen] = useState<number[]>(props.initial);
  const flip = (id: number) => setChosen(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await props.onSubmit(chosen);
      props.onError("");
      props.onDone();
    } catch (err) {
      props.onError(errorText(err));
    }
  };
  return (
    <form className="admin-form" onSubmit={submit}>
      {props.title ? <h3>{props.title}</h3> : null}
      {props.note ? <p>{props.note}</p> : null}
      <fieldset>
        <legend>Halls this manager can see</legend>
        {props.halls.map((h) => (
          <label key={h.id}>
            <input type="checkbox" checked={chosen.includes(h.id)} onChange={() => flip(h.id)} /> {h.name}
          </label>
        ))}
      </fieldset>
      {chosen.length === 0 ? <p className="admin-help">A manager with no halls assigned sees an empty dashboard. That is allowed.</p> : null}
      <button type="submit">{props.action}</button>
    </form>
  );
}
