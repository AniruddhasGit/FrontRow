// The film screens' shared shapes and words (SCR-ADM-01, SCR-ADM-02, SCR-ADM-07). Pure: the render tests import it.
import { plural } from "./text";

export interface Named {
  id: number;
  name: string;
}
export interface Film {
  id: number;
  title: string;
  synopsis: string;
  runtime_minutes: number;
  certification_id: number;
  language_id: number;
  genre_ids: number[];
  certification: Named;
  language: Named;
  genres: Named[];
  poster_present: boolean;
  published_at: string | null;
  display_from: string | null; // naive local, the venue's zone - never converted here (E6 S4)
  display_until: string | null;
  published: boolean;
  window_open: boolean;
  is_visible_now: boolean;
  version: number;
}
export interface Entry {
  id: number;
  name: string;
  is_active: boolean;
  reference_count: number;
}
export type Kind = "language" | "certification" | "genre" | "format";

export const KINDS: { kind: Kind; tab: string }[] = [
  { kind: "language", tab: "Languages" },
  { kind: "certification", tab: "Certifications" },
  { kind: "genre", tab: "Genres" },
  { kind: "format", tab: "Formats" },
];

// SCR-ADM-01's position readout: every form is published, including one film and none.
export function readout(offset: number, shown: number, total: number): string {
  if (total === 0 || shown === 0) return "No films";
  if (total === 1) return "Film 1 of 1";
  return `Films ${offset + 1} to ${offset + shown} of ${total}`;
}

export function windowMark(film: Film): string {
  if (film.window_open) return "In window";
  return film.display_from === null || film.display_until === null ? "No display window set" : "Outside its display window";
}

// SCR-ADM-07: a singular, a plural and a zero, each its own sentence.
export function usage(kind: Kind, n: number): string {
  const [one, many] = kind === "format" ? ["showtime", "showtimes"] : ["film", "films"];
  return n === 0 ? `Not used by any ${one} yet` : `Used by ${plural(n, one, many)}`;
}

// SCR-ADM-02's second gate line. `nowLocal` is the venue's current local time, naive, as the window is.
export function windowLine(film: Film, nowLocal: string): string {
  if (film.window_open) return "Inside its display window.";
  if (film.display_from === null || film.display_until === null) return "No display window set. Customers cannot see this film.";
  return nowLocal < film.display_from
    ? "Its display window has not started yet. Customers cannot see this film until then."
    : "Its display window has ended. Customers can no longer see this film.";
}

export const EMPTY_VOCABULARY: Record<"language" | "certification" | "genre", string> = {
  language: "There are no languages on the list yet. Add one before saving this film.",
  certification: "There are no certifications on the list yet. Add one before saving this film.",
  genre: "There are no genres on the list yet. Add one before saving this film.",
};
