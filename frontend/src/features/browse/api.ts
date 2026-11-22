// GET against the public read path. Every message the customer reads on a failure is the server's or the screen's
// published copy; this file composes none (SCR-XCT-01). The read path reads no session, so nothing is sent with it
// but what the browser sends anyway.

export type Got<T> =
  | { ok: true; status: number; body: T }
  | { ok: false; status: number; code: string; message: string; requestId: string | null; retryAfter: number | null };

export async function get<T>(path: string, signal?: AbortSignal): Promise<Got<T>> {
  return request<T>(path, { credentials: "same-origin", signal });
}

/** A JSON write (CR-008 account screens): the same envelope handling as get(). `details` carries field errors. */
export async function send<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<Got<T> & { details?: unknown }> {
  // A write that never answers ends as a failure after 15 s (web-app-pitfalls rule 2), so its form never sticks on Sending.
  return request<T>(path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                            signal: AbortSignal.timeout(15000) });
}

async function request<T>(path: string, init: RequestInit): Promise<Got<T> & { details?: unknown }> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, code: "NETWORK", message: "", requestId: null, retryAfter: null };
  }
  const data = await response.json().catch(() => null);
  if (response.ok && data !== null) return { ok: true, status: response.status, body: data as T };
  const error = data?.error ?? {};
  const retry = Number(response.headers.get("Retry-After"));
  return {
    ok: false,
    status: response.status,
    code: error.code ?? "INTERNAL_ERROR",
    message: error.message ?? "",
    requestId: error.request_id ?? null,
    retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
    details: error.details,
  };
}

export function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface Film {
  id: number;
  title: string;
  synopsis: string;
  runtime_minutes: number;
  certification: { id: number; name: string };
  language: { id: number; name: string };
  genres: { id: number; name: string }[];
  poster_url: string;
  display_until: string;
  // CR-008 T10-T12: on every card
  release_date: string | null;
  coming_soon: boolean;
  rating: { average_tenths: number | null; count: number };
  likes: number;
}

/** EP-BRW-02 adds the film page's full details (CR-008 T12). */
export interface FilmDetail extends Film {
  rating: { average_tenths: number | null; count: number; breakdown: number[] };
  cast: { name: string; role: string | null }[];
  crew: { name: string; role: string | null }[];
}

export interface Showtime {
  id: number;
  starts_at: string;
  ends_at: string;
  sales_close_at: string;
  sales_closed: boolean;
  screen: { id: number; name: string };
  cinema: { id: number; name: string };
  format: { id: number; name: string } | null;
  base_price_paise: number;
}
