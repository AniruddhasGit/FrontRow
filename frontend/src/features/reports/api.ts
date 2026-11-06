// The reporting screens' one way to call /api/reports. GET only: nothing on this surface writes (P-RPT-09).
// The server renders every message, except the 429 wait, which is computed here from Retry-After at render time
// (S7.20 rule 6: a literal is a defect).
import { spanText } from "./format";

export type Get = (url: string) => Promise<{ status: number; headers: { get(name: string): string | null }; json(): Promise<unknown> }>;

export class ReportError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export const browserGet: Get = (url) => fetch(url, { credentials: "same-origin" });

export async function getJson<T>(get: Get, url: string): Promise<T> {
  const r = await get(url);
  const data = (await r.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  if (r.status === 429) {
    const wait = Number(r.headers.get("Retry-After")) || 1;
    throw new ReportError(429, "RATE_LIMITED", `Too many requests. Try again in ${spanText(wait)}.`);
  }
  if (r.status >= 400) {
    throw new ReportError(r.status, data?.error?.code ?? "INTERNAL_ERROR", data?.error?.message ?? "The request failed.");
  }
  return data as T;
}

export function errorText(e: unknown): string {
  return e instanceof ReportError ? e.message : "The request failed.";
}
