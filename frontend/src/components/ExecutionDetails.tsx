import type { EvaluationResult } from "../types";
import { Badge, Card } from "./ui";

export default function ExecutionDetails({ result }: { result: EvaluationResult }) {
  return (
    <Card title="Execution details">
      <p className="mb-3 text-xs text-zinc-500">
        Mode: <span className="font-mono text-zinc-300">{result.execution_mode}</span> · total{" "}
        <span className="font-mono text-zinc-300">{result.duration_seconds}s</span> · Bandit{" "}
        {result.bandit_used ? "used" : "not installed"}
      </p>
      <div className="space-y-2">
        {result.executions.map((run) => (
          <details key={run.name} className="rounded-md border border-zinc-800 bg-zinc-950/60">
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-xs">
              <span className="font-mono text-zinc-200">{run.name}</span>
              <Badge tone={run.timed_out ? "bad" : run.exit_code === 0 ? "good" : "muted"}>
                {run.timed_out ? "timed out" : `exit ${run.exit_code}`}
              </Badge>
              <span className="font-mono text-zinc-500">{run.duration_seconds}s</span>
            </summary>
            <div className="space-y-2 border-t border-zinc-800 p-3">
              <p className="break-all font-mono text-[11px] text-zinc-500">$ {run.command}</p>
              {run.stdout && (
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-zinc-300">
                  {run.stdout}
                </pre>
              )}
              {run.stderr && (
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-red-300">
                  {run.stderr}
                </pre>
              )}
              {run.output_truncated && <p className="text-[11px] text-amber-400">Output truncated.</p>}
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}
