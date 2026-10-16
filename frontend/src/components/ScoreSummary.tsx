import type { EvaluationResult, Severity } from "../types";
import { Badge, Card, ScoreBar, StatusDot, scoreTone, toneText } from "./ui";

function Metric({ label, value }: { label: string; value: number }) {
  const tone = scoreTone(value);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className={`font-mono text-sm ${toneText[tone]}`}>{value}</span>
      </div>
      <ScoreBar value={value} tone={tone} />
    </div>
  );
}

function countBySeverity(result: EvaluationResult, severity: Severity) {
  return result.failures.filter((f) => f.severity === severity).length;
}

export default function ScoreSummary({ result }: { result: EvaluationResult }) {
  const tone = scoreTone(result.overall_score);
  const critical = countBySeverity(result, "HIGH");
  const warnings = countBySeverity(result, "MEDIUM");
  const notes = countBySeverity(result, "LOW");
  const gamingTone =
    result.gaming_risk === "none" ? "good" : result.gaming_risk === "low" ? "warn" : "bad";

  return (
    <Card title="Evaluation result">
      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
        <span className="font-mono text-zinc-300">{result.repository_name}</span>
        <span>{result.task_title}</span>
        <span className="font-mono">#{result.evaluation_id}</span>
      </div>

      <div className="grid gap-6 md:grid-cols-[200px_1fr]">
        <div>
          <p className="text-xs text-zinc-500">Overall score</p>
          <p className={`font-mono text-6xl font-semibold tabular-nums ${toneText[tone]}`}>
            {result.overall_score}
            <span className="text-2xl text-zinc-600">/100</span>
          </p>
          {result.score_cap_applied && (
            <p className="mt-2 text-xs text-red-300">
              Integrity cap applied (raw score {result.raw_score}). See Test Gaming.
            </p>
          )}
          <div className="mt-4 space-y-1.5 text-sm">
            <p className="flex items-center gap-2">
              <StatusDot tone={critical ? "bad" : "good"} />
              <span className="font-mono">{critical}</span> critical
            </p>
            <p className="flex items-center gap-2">
              <StatusDot tone={warnings ? "warn" : "good"} />
              <span className="font-mono">{warnings}</span> warnings
            </p>
            <p className="flex items-center gap-2">
              <StatusDot tone="muted" />
              <span className="font-mono">{notes}</span> notes
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            <Metric label="Functional" value={result.functional_score} />
            <Metric label="Edge cases" value={result.edge_case_score} />
            <Metric label="Requirements" value={result.requirement_score} />
            <Metric label="Security" value={result.security_score} />
            <Metric label="Code quality" value={result.quality_score} />
          </div>
          <div className="flex flex-wrap gap-2 border-t border-zinc-800 pt-3">
            <Badge tone={result.tests_failed ? "bad" : "good"}>
              hidden tests {result.tests_passed}/{result.tests_passed + result.tests_failed}
            </Badge>
            <Badge tone={result.own_tests.failed ? "warn" : "muted"}>
              own tests {result.own_tests.passed}/{result.own_tests.total}
            </Badge>
            <Badge tone={gamingTone}>gaming risk: {result.gaming_risk} (heuristic)</Badge>
          </div>
        </div>
      </div>
    </Card>
  );
}
