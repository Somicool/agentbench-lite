import type { EvaluationResult, ExampleInfo, HealthInfo, TaskInfo } from "./types";

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  let detail = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail)) {
      detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    }
  } catch {
    // keep the status text
  }
  throw new Error(detail);
}

export const fetchHealth = () => fetch("/health").then((r) => parse<HealthInfo>(r));
export const fetchExamples = () => fetch("/api/examples").then((r) => parse<ExampleInfo[]>(r));
export const fetchTasks = () => fetch("/api/tasks").then((r) => parse<TaskInfo[]>(r));
export const fetchEvaluation = (id: string) =>
  fetch(`/api/evaluations/${id}`).then((r) => parse<EvaluationResult>(r));

export interface EvaluationRequest {
  description: string;
  example: string | null;
  file: File | null;
}

export function runEvaluation(request: EvaluationRequest): Promise<EvaluationResult> {
  const form = new FormData();
  form.append("task_description", request.description);
  if (request.example) {
    form.append("example", request.example);
  }
  if (request.file) {
    form.append("repository", request.file);
  }
  return fetch("/api/evaluate", { method: "POST", body: form }).then((r) =>
    parse<EvaluationResult>(r),
  );
}

export const createReport = (id: string) =>
  fetch(`/api/evaluations/${id}/report`, { method: "POST" }).then((r) =>
    parse<{ content: string }>(r),
  );
