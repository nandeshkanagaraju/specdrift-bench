import type {
  CaseDetail,
  CaseList,
  CheckSummary,
  MetricsResponse,
  Project,
  RuleDetail,
  SourceFile,
  StageEvent,
  SweepCase,
  SweepResult,
  Summary,
  UploadRecord,
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
  projectCode: (name: string, signal?: AbortSignal) =>
    get<SourceFile[]>(`/projects/${encodeURIComponent(name)}/code`, signal),
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
  onStage?: (stage: StageEvent) => void;
  onRuleStart?: (rule: { rule_id: string; text: string }) => void;
  onRuleDetail?: (detail: RuleDetail) => void;
  onVerdict: (verdict: Verdict) => void;
  onSummary: (summary: CheckSummary) => void;
  onError?: (message: string) => void;
}

export interface UploadInput {
  name: string;
  spec: string;
  files: { path: string; source: string }[];
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* the body was not JSON */
  }
  return `${response.status} ${response.statusText}`;
}

/** Save a spec and Python files the user typed or pasted. */
export async function uploadProject(body: UploadInput, signal?: AbortSignal): Promise<UploadRecord> {
  const response = await fetch(`${BASE}/uploads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(await errorDetail(response));
  return (await response.json()) as UploadRecord;
}

/** Save a zip of spec.md plus Python sources. The body is the archive itself. */
export async function uploadArchive(
  file: File,
  name: string,
  signal?: AbortSignal,
): Promise<UploadRecord> {
  const response = await fetch(`${BASE}/uploads/archive?name=${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/zip" },
    body: file,
    signal,
  });
  if (!response.ok) throw new Error(await errorDetail(response));
  return (await response.json()) as UploadRecord;
}

/**
 * POST /api/check returns Server-Sent Events, which EventSource cannot request,
 * so the stream is read off the response body directly.
 */
export async function runCheck(
  body: { project?: string | null; case_id?: string | null; upload_id?: string | null },
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

  await readEvents(response, (event, payload) => {
    if (event === "start") handlers.onStart?.();
    else if (event === "stage") handlers.onStage?.(payload as StageEvent);
    else if (event === "rule_start") handlers.onRuleStart?.(payload);
    else if (event === "rule_detail") handlers.onRuleDetail?.(payload as RuleDetail);
    else if (event === "verdict") handlers.onVerdict(payload as Verdict);
    else if (event === "summary") handlers.onSummary(payload as CheckSummary);
  });
}


/** Read a Server-Sent Events body frame by frame, dispatching each one. */
async function readEvents(
  response: Response,
  dispatch: (event: string, payload: any) => void,
): Promise<void> {
  const reader = response.body!.getReader();
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
      if (data) dispatch(event, JSON.parse(data));
    }
  }
}

export interface SweepHandlers {
  onCase: (row: SweepCase) => void;
  onResult: (row: SweepResult) => void;
  onSummary: (summary: { total: number; caught: number }) => void;
  onError?: (message: string) => void;
}

/** Check one representative case of every drift category, category by category. */
export async function runSweep(handlers: SweepHandlers, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${BASE}/sweep`, { method: "POST", signal });
  if (!response.ok || !response.body) {
    handlers.onError?.(`sweep failed: ${response.status} ${response.statusText}`);
    return;
  }

  await readEvents(response, (event, payload) => {
    if (event === "case_start") handlers.onCase(payload as SweepCase);
    else if (event === "case_result") handlers.onResult(payload as SweepResult);
    else if (event === "sweep_summary") handlers.onSummary(payload);
  });
}
