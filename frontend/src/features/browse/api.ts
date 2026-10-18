// GET against the public read path. Every message the customer reads on a failure is the server's or the screen's
// published copy; this file composes none (SCR-XCT-01). The read path reads no session, so nothing is sent with it
// but what the browser sends anyway.

export type Got<T> =
  | { ok: true; status: number; body: T }
  | { ok: false; status: number; code: string; message: string; requestId: string | null; retryAfter: number | null };

export async function get<T>(path: string, signal?: AbortSignal): Promise<Got<T>> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", signal });
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
