// Dollars to cents at the interface boundary, with no floating point anywhere (P-ADM-10, FR-ADR-036).
// The API takes integer minor units only; the admin types dollars. "250.00" becomes 25000 by string arithmetic,
// never by 250.00 * 100, which is how 0.1 + 0.2 reaches a price. The currency is USD (SRC-006 CUR-1); the
// "rupees"/"paise" names below are kept and mean major unit / 1/100 minor unit (see config.py's ponytail note).

// Cents per dollar (SRC-006 CUR-1). Named once; a one-way door, so never a scattered literal.
export const MINOR_UNIT_RATIO = 100;
const MINOR_DIGITS = String(MINOR_UNIT_RATIO).length - 1;

/** "250", "250.5" or "250.00" -> 25000, 25050, 25000. Anything else, or a value too large to send
 *  exactly, -> null, and the form says so rather than sending a rounded figure. */
export function rupeesToPaise(text: string): number | null {
  const match = new RegExp(`^(\\d+)(?:\\.(\\d{1,${MINOR_DIGITS}}))?$`).exec(text.trim());
  if (!match) return null;
  const paise = BigInt(match[1]) * BigInt(MINOR_UNIT_RATIO) + BigInt((match[2] ?? "").padEnd(MINOR_DIGITS, "0"));
  return paise <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(paise) : null;
}

/** 25000 -> "250.00", the form's own input text, by integer division only. */
export function paiseToRupeesText(paise: number): string {
  return `${Math.floor(paise / MINOR_UNIT_RATIO)}.${String(paise % MINOR_UNIT_RATIO).padStart(MINOR_DIGITS, "0")}`;
}

/** 1299 -> "$12.99", 166146 -> "$1,661.46" (en-US grouping). Rendering only; the integer is the value. */
export function formatPaise(paise: number): string {
  const whole = Math.floor(paise / MINOR_UNIT_RATIO);
  const minor = String(paise % MINOR_UNIT_RATIO).padStart(MINOR_DIGITS, "0");
  return `$${whole.toLocaleString("en-US")}.${minor}`;
}

/** The body SCR-ADM-03's form submits: dollars typed, integer cents sent (S-ADM-12). One function, so the
 *  conversion is tested where it happens rather than re-implemented in a test. */
export function showtimeBody(form: { movie_id: string; screen_id: string; starts_at: string; ends_at: string; rupees: string }) {
  return {
    movie_id: Number(form.movie_id),
    screen_id: Number(form.screen_id),
    starts_at: form.starts_at,
    ends_at: form.ends_at,
    base_price_paise: rupeesToPaise(form.rupees),
  };
}
