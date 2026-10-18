// The admin screens' one way to call /api/admin. The server renders every message; this file never
// composes one (SCR-XCT-01). The session cookie rides along on same-origin requests.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown>,
  ) {
    super(message);
  }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(response.status, error.code ?? "INTERNAL_ERROR", error.message ?? "The request failed.", error.details ?? {});
  }
  return data as T;
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "The request failed.";
}
