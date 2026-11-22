// CR-008 T8: Help & support at /help - an FAQ and a contact form that stores the message (no email is sent).
// The accordion is native <details>/<summary>: keyboard, screen reader and find-in-page support come from the browser.
// Open to everyone; a signed-in sender's message is filed under their account by the server.
import { useState } from "react";
import { send } from "../browse/api";
import { UNAVAILABLE, type Send } from "./account";
import "./account.css";

export const FAQ: { q: string; a: string }[] = [
  { q: "How do I book seats?", a: "Pick a film, then a showtime. Tap free seats on the map (up to 10), choose Hold seats, then pay on the checkout page. Your booking reference appears on screen and in your email." },
  { q: "What does the countdown mean?", a: "Held seats are kept for you for 3 minutes. The countdown shows the time left. Pay before it reaches zero; when it does, the seats are released for others and you can choose again." },
  { q: "Is the payment real?", a: "No. This is a demonstration system: payments are simulated, nothing is charged and no card details are ever asked for or stored." },
  { q: "How do rewards points work?", a: "Every paid booking earns 10 points per whole dollar you pay, once per booking. At checkout you can choose to use your points: 100 points take $1.00 off, up to half of the order. If a payment fails or your hold ends, the points are not spent." },
  { q: "What are bookmarks?", a: "Press Save on any film to keep it on your Wishlist, which you can open from the account menu. Sign in first; if you are not signed in, we bring you back and save it once you have." },
  { q: "Can I cancel a booking?", a: "Not in this version: a booking cannot be changed or cancelled online, and the payment here is simulated anyway. Send us a message below if something went wrong." },
  { q: "How do I get in to the hall?", a: "Show your booking reference (FR-XXXX-XXXX) at the door. It is on your confirmation page, under My bookings, and in your receipt email." },
];

const TOPICS = [["booking", "A booking"], ["payment", "Payment"], ["rewards", "Rewards points"], ["account", "My account"], ["other", "Something else"]];

export function HelpScreen() {
  const [topic, setTopic] = useState("booking");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Send>({ kind: "idle" });
  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault();
    if (status.kind === "sending") return;
    if (!message.trim()) return setErrors({ message: "Write a message of 1 to 2000 characters." });
    setErrors({});
    setStatus({ kind: "sending" });
    const r = await send<{ message: string }>("POST", "/api/support/messages", { topic, message, email: email.trim() || null });
    if (r.ok) {
      setMessage("");
      return setStatus({ kind: "done", message: r.body.message });
    }
    setErrors((r.details as { fields?: Record<string, string> } | undefined)?.fields ?? {});
    setStatus({ kind: "failed", message: r.message || UNAVAILABLE });
  };
  const describe = (k: string) => ({ "aria-invalid": errors[k] ? true : undefined, "aria-describedby": errors[k] ? `fr-h-${k}-err` : undefined });
  return (
    <section className="fr-account-page" aria-labelledby="fr-help-h">
      <h1 id="fr-help-h">Help &amp; support</h1>
      <h2>Questions people ask</h2>
      <div className="fr-faq">
        {FAQ.map((f) => (
          <details key={f.q} className="fr-faq-item">
            <summary>{f.q}</summary>
            <p>{f.a}</p>
          </details>
        ))}
      </div>
      <h2 id="fr-contact-h">Send us a message</h2>
      <form className="fr-profile" aria-labelledby="fr-contact-h" onSubmit={(e) => void submit(e)} noValidate>
        <div className="fr-field">
          <label htmlFor="fr-h-topic">Topic</label>
          <select id="fr-h-topic" value={topic} onChange={(e) => setTopic(e.target.value)}>
            {TOPICS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="fr-field">
          <label htmlFor="fr-h-email">Your email (not needed when signed in)</label>
          <input id="fr-h-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" {...describe("email")} />
          {errors.email ? <p className="fr-field-error" id="fr-h-email-err">{errors.email}</p> : null}
        </div>
        <div className="fr-field">
          <label htmlFor="fr-h-message">Message</label>
          <textarea id="fr-h-message" rows={5} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)} {...describe("message")} />
          {errors.message ? <p className="fr-field-error" id="fr-h-message-err">{errors.message}</p> : null}
        </div>
        <div aria-live="polite" className="fr-profile-status">
          {status.kind === "failed" ? <p className="fr-banner">{status.message}</p> : status.kind === "done" ? <p>{status.message}</p> : null}
        </div>
        <button type="submit" className="fr-action" disabled={status.kind === "sending"} aria-busy={status.kind === "sending" || undefined}>
          {status.kind === "sending" ? "Sending…" : "Send message"}
        </button>
      </form>
    </section>
  );
}
