import { useCallback, useEffect, useState } from "react";
import { fetchEvaluation, fetchExamples, fetchHealth, fetchTasks, runEvaluation } from "../api";
import ExecutionDetails from "../components/ExecutionDetails";
import FindingsTabs from "../components/FindingsTabs";
import ReportPanel from "../components/ReportPanel";
import RunHistory, { type RunSummary } from "../components/RunHistory";
import ScoreBreakdown from "../components/ScoreBreakdown";
import ScoreSummary from "../components/ScoreSummary";
import TaskForm, { type RepoSource } from "../components/TaskForm";
import { StatusDot } from "../components/ui";
import type { EvaluationResult, ExampleInfo, HealthInfo } from "../types";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthInfo | null | "down">(null);
  const [examples, setExamples] = useState<ExampleInfo[]>([]);
  const [description, setDescription] = useState("");
  const [source, setSource] = useState<RepoSource>("example");
  const [example, setExample] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth("down"));
    fetchExamples()
      .then((items) => {
        setExamples(items);
        setExample((current) => current || items.find((i) => i.name === "buggy_solution")?.name || items[0]?.name || "");
      })
      .catch(() => setExamples([]));
    fetchTasks()
      .then((tasks) => setDescription((current) => current || tasks[0]?.default_description || ""))
      .catch(() => undefined);
  }, []);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const evaluation = await runEvaluation({
        description,
        example: source === "example" ? example : null,
        file: source === "upload" ? file : null,
      });
      setResult(evaluation);
      setRuns((previous) => [
        ...previous,
        { id: evaluation.evaluation_id, name: evaluation.repository_name, score: evaluation.overall_score },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setLoading(false);
    }
  }, [description, example, file, source]);

  const select = async (id: string) => {
    try {
      setResult(await fetchEvaluation(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load that evaluation");
    }
  };

  const backendDown = health === "down";

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="font-mono text-lg font-semibold tracking-tight text-zinc-100">
            agentbench<span className="text-emerald-400">/</span>lite
          </h1>
          <p className="text-xs text-zinc-500">
            Evaluate AI-generated Python code with hidden tests, static checks and failure analysis
          </p>
        </div>
        <p className="flex items-center gap-2 font-mono text-xs text-zinc-500">
          <StatusDot tone={backendDown ? "bad" : health ? "good" : "muted"} />
          {backendDown
            ? "backend unreachable"
            : health
              ? `backend ok · ${health.execution_mode} execution`
              : "connecting…"}
        </p>
      </header>

      {backendDown && (
        <p role="alert" className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          Cannot reach the API. Start it with{" "}
          <code className="font-mono">uvicorn app.main:app --port 8000</code> in the backend folder.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <div className="space-y-4">
          <TaskForm
            description={description}
            onDescription={setDescription}
            source={source}
            onSource={setSource}
            examples={examples}
            example={example}
            onExample={setExample}
            file={file}
            onFile={setFile}
            loading={loading}
            onRun={run}
          />
          <RunHistory runs={runs} activeId={result?.evaluation_id ?? null} onSelect={select} />
        </div>

        <div className="min-w-0 space-y-4" aria-live="polite">
          {error && (
            <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </p>
          )}
          {result ? (
            <>
              <ScoreSummary result={result} />
              <FindingsTabs result={result} />
              <ScoreBreakdown result={result} />
              <ExecutionDetails result={result} />
              <ReportPanel result={result} />
            </>
          ) : (
            !error && (
              <div className="rounded-lg border border-dashed border-zinc-800 p-10 text-center">
                <p className="text-sm text-zinc-400">No evaluation yet.</p>
                <p className="mt-1 text-xs text-zinc-600">
                  Pick a bundled example and run it. Try buggy, then good, then cheating.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
