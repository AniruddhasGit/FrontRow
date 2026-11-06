// Rendering helpers shared by the dashboard (SCR-RPT-01) and the change log (SCR-RPT-02). No clock, no zone
// arithmetic: every instant arrives already carrying the cinema's offset and is read as the wall-clock it states.
import { formatPaise } from "../admin/money";

export { formatPaise };

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08-12T15:40:00+05:30" -> "12 Aug 2026, 3:40 pm" (S7.19's date-with-time form; no zone suffix). */
export function whenText(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return iso;
  const hour = Number(m[4]);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${Number(m[3])} ${MONTHS_SHORT[Number(m[2]) - 1]} ${m[1]}, ${h12}:${m[5]} ${hour < 12 ? "am" : "pm"}`;
}

/** 29.5 -> "29.5 %"; null -> "—" (capacity zero is not zero per cent, P-RPT-04). */
export function pctText(pct: number | null): string {
  return pct === null ? "—" : `${pct.toFixed(1)} %`;
}

/** S7.20: a wait under 120 s in seconds, otherwise whole minutes; singular for 1. Computed, never typed. */
export function spanText(seconds: number): string {
  if (seconds < 120) return seconds === 1 ? "1 second" : `${seconds} seconds`;
  return `${Math.ceil(seconds / 60)} minutes`;
}

const ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
  "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function belowHundred(n: number): string {
  return n < 20 ? ONES[n] : TENS[Math.floor(n / 10)] + (n % 10 ? `-${ONES[n % 10]}` : "");
}

function belowThousand(n: number): string {
  const h = Math.floor(n / 100);
  const rest = n % 100;
  if (!h) return belowHundred(rest);
  return `${ONES[h]} hundred` + (rest ? ` and ${belowHundred(rest)}` : "");
}

/** 27833 -> "twenty-seven thousand eight hundred and thirty-three" (British "and").
 *  ponytail: short scale (thousand, million, billion), not lakh and crore - the PRD's one example is below a lakh;
 *  the Indian scale is the upgrade if the copy owner asks for it. */
export function words(n: number): string {
  if (n === 0) return "zero";
  const parts: string[] = [];
  const scales: [number, string][] = [[1e9, "billion"], [1e6, "million"], [1e3, "thousand"]];
  let rest = n;
  for (const [size, label] of scales) {
    if (rest >= size) {
      parts.push(`${belowThousand(Math.floor(rest / size))} ${label}`);
      rest %= size;
    }
  }
  if (rest) parts.push(parts.length && rest < 100 ? `and ${belowHundred(rest)}` : belowThousand(rest));
  return parts.join(" ");
}

/** 2783331 -> "twenty-seven thousand eight hundred and thirty-three rupees and thirty-one paise". */
export function paiseWords(paise: number): string {
  const rupees = Math.floor(paise / 100);
  const minor = paise % 100;
  return `${words(rupees)} ${rupees === 1 ? "rupee" : "rupees"} and ${words(minor)} ${minor === 1 ? "paisa" : "paise"}`;
}

/** 29.5 -> "twenty-nine point five per cent". */
export function pctWords(pct: number): string {
  const tenths = Math.round(pct * 10);
  return `${words(Math.floor(tenths / 10))} point ${ONES[tenths % 10]} per cent`;
}
