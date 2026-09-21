import type {
  CaseDetail,
  CaseList,
  CheckSummary,
  MetricsResponse,
  Project,
  Summary,
  Verdict,
} from "./types";

const BASE = "/api";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { signal });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${path}`);
  }
  return (await response.json()) as T;
}

export const api = {
  summary: (signal?: AbortSignal) => get<Summary>("/summary", signal),
  metrics: (detector?: string, signal?: AbortSignal) =>
    get<MetricsResponse>(detector ? `/metrics?detector=${detector}` : "/metrics", signal),
  projects: (signal?: AbortSignal) => get<Project[]>("/projects", signal),
  caseDetail: (id: string, signal?: AbortSignal) =>
    get<CaseDetail>(`/cases/${encodeURIComponent(id)}`, signal),
  cases: (params: Record<string, string | undefined>, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) query.set(key, value);
    }
    const suffix = query.toString();
    return get<CaseList>(suffix ? `/cases?${suffix}` : "/cases", signal);
  },
};

export interface CheckHandlers {
  onStart?: () => void;
  onVerdict: (verdict: Verdict) => void;
  onSummary: (summary: CheckSummary) => void;
  onError?: (message: string) => void;
}

/**
 * POST /api/check returns Server-Sent Events, which EventSource cannot request,
 * so the stream is read off the response body directly.
 */
export async function runCheck(
  body: { project: string; case_id?: string | null },
  handlers: CheckHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    handlers.onError?.(`check failed: ${response.status} ${response.statusText}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      const payload = JSON.parse(data);
      if (event === "start") handlers.onStart?.();
      else if (event === "verdict") handlers.onVerdict(payload as Verdict);
      else if (event === "summary") handlers.onSummary(payload as CheckSummary);
    }
  }
}
