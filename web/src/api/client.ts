// API client. Every request carries the per-launch session token (spec §3.1).
// The launcher opens the app at /#token=<token>; we move it into sessionStorage
// and strip it from the URL so it isn't left in the address bar or history.

import type { ExtractedProblem, Extraction, ProblemList, ProblemView, ProvidersResponse, Status } from "./types";

const TOKEN_KEY = "mathassistant.token";
let token: string | null = null;

export function initToken(): string | null {
  const m = window.location.hash.match(/token=([A-Za-z0-9_\-]+)/);
  if (m) {
    token = m[1];
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* private mode: keep in memory only */
    }
    history.replaceState(null, "", window.location.pathname + window.location.search);
  } else {
    try {
      token = sessionStorage.getItem(TOKEN_KEY);
    } catch {
      token = null;
    }
  }
  return token;
}

export class ApiError extends Error {
  constructor(
    public kind: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Session-Token": token ?? "",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("offline", "Can't reach MathAssistant. It may have been closed. Start it again.", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.error ?? "error", data.message ?? "Something went wrong.", res.status);
  }
  return data as T;
}

export const api = {
  status: () => request<Status>("GET", "/api/status"),
  providers: () => request<ProvidersResponse>("GET", "/api/providers"),
  setModel: (provider: string, model: string) =>
    request<Status>("POST", "/api/settings/model", { provider, model }),
  testKey: (provider: string, model: string, key?: string) =>
    request<{ ok: boolean; status: Status }>("POST", "/api/key/test", { provider, model, key: key || null }),
  removeKey: (provider: string) =>
    request<Status>("DELETE", `/api/key?provider=${encodeURIComponent(provider)}`),
  listProblems: () => request<ProblemList>("GET", "/api/problems"),
  // Either LaTeX (math field) or plain text (word problem).
  startProblem: (latex: string, text = "", extractionIds: string[] = [], queuedId: string | null = null) =>
    request<ProblemView>("POST", "/api/problems", { latex, text, extraction_ids: extractionIds, queued_id: queuedId }),
  // Save not-yet-started problems (rest of a worksheet) to "Up next". No AI calls.
  queue: (items: ExtractedProblem[], source: string) =>
    request<{ ok: boolean; added: number }>("POST", "/api/queue", { items, source }),
  deleteQueued: (id: string) => request<{ ok: boolean }>("DELETE", `/api/queue/${encodeURIComponent(id)}`),
  // Phase 2: one cropped image -> problem text to confirm (one vision call; not stored).
  extract: (imageBase64: string, mediaType: string) =>
    request<Extraction>("POST", "/api/extract", { image_base64: imageBase64, media_type: mediaType }),
  getProblem: (id: string) => request<ProblemView>("GET", `/api/problems/${encodeURIComponent(id)}`),
  turn: (id: string, text: string, latex: string) =>
    request<ProblemView>("POST", `/api/problems/${encodeURIComponent(id)}/turn`, { text, latex }),
  deleteProblem: (id: string) => request<{ ok: boolean }>("DELETE", `/api/problems/${encodeURIComponent(id)}`),
  deleteAll: () => request<{ ok: boolean; deleted: number }>("DELETE", "/api/problems"),
  quit: () => request<{ ok: boolean }>("POST", "/api/quit"),
};
