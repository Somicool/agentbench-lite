import { useState } from "react";
import type { CaseCategory, EvaluationResult, Failure, RequirementStatus } from "../types";
import { Badge, Card, ScoreBar, StatusDot, severityTone, type Tone } from "./ui";

type TabKey = "functional" | "security" | "requirements" | "gaming";

const FUNCTIONAL_CATEGORIES = new Set([
  "FUNCTIONAL_ERROR",
  "EDGE_CASE_FAILURE",
  "ROBUSTNESS_FAILURE",
  "PERFORMANCE_FAILURE",
  "TEST_FAILURE",
  "ENVIRONMENT_FAILURE",
]);

const CASE_LABELS: Record<CaseCategory, string> = {
  normal: "Normal",
  edge: "Edge cases",
  robustness: "Robustness",
  performance: "Performance",
};

function FailureRow({ failure }: { failure: Failure }) {
  return (
    <li className="flex items-start gap-3 py-2">
      <span className="mt-1.5">
        <StatusDot tone={severityTone(failure.severity)} />
      </span>
      <div className="min-w-0">
        <p className="font-mono text-[11px] text-zinc-500">
          {failure.category}
          {failure.file && ` · ${failure.file}${failure.line ? `:${failure.line}` : ""}`}
        </p>
        <p className="break-words font-mono text-xs text-zinc-200">{failure.message}</p>
      </div>
    </li>
  );
}

function Empty({ children }: { children: string }) {
  return <p className="py-6 text-center text-sm text-emerald-400">{children}</p>;
}

function FunctionalTab({ result }: { result: EvaluationResult }) {
  const failures = result.failures.filter((f) => FUNCTIONAL_CATEGORIES.has(f.category));
  const groups = (Object.keys(CASE_LABELS) as CaseCategory[])
    .map((category) => {
      const cases = result.cases.filter((c) => c.category === category);
      return { category, total: cases.length, passed: cases.filter((c) => c.outcome === "passed").length };
    })
    .filter((g) => g.total > 0);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {groups.map((g) => {
          const pct = Math.round((g.passed / g.total) * 100);
          const tone: Tone = pct === 100 ? "good" : pct >= 60 ? "warn" : "bad";
          return (
            <div key={g.category} className="rounded-md border border-zinc-800 p-3">
              <p className="text-xs text-zinc-400">{CASE_LABELS[g.category]}</p>
              <p className="my-1 font-mono text-lg">
                {g.passed}/{g.total}
              </p>
              <ScoreBar value={pct} tone={tone} />
            </div>
          );
        })}
      </div>
      {failures.length === 0 ? (
        <Empty>All hidden tests passed.</Empty>
      ) : (
        <ul className="divide-y divide-zinc-800/70">
          {failures.map((f, i) => (
            <FailureRow key={i} failure={f} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SecurityTab({ result }: { result: EvaluationResult }) {
  const findings = [...result.security_findings, ...result.quality_findings.filter((f) => f.rule === "QUALITY-EXCEPT-001")];
  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-500">
        AST rules{result.bandit_used ? " + Bandit" : ""} and dependency inspection. Not a complete
        security scanner.
        {result.dependencies.length > 0 && ` Dependencies: ${result.dependencies.join(", ")}.`}
      </p>
      {findings.length === 0 ? (
        <Empty>No findings from the implemented rules.</Empty>
      ) : (
        <ul className="divide-y divide-zinc-800/70">
          {findings.map((f, i) => (
            <li key={i} className="flex items-start gap-3 py-2">
              <span className="mt-0.5">
                <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
              </span>
              <div className="min-w-0">
                <p className="font-mono text-xs text-zinc-200">{f.message}</p>
                <p className="font-mono text-[11px] text-zinc-500">
                  {f.rule} · {f.file}
                  {f.line ? `:${f.line}` : ""}
                </p>
                {f.recommendation && (
                  <p className="mt-0.5 text-[11px] text-zinc-500">Fix: {f.recommendation}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const STATUS_TONE: Record<RequirementStatus, Tone> = {
  met: "good",
  partial: "warn",
  not_met: "bad",
  not_evaluated: "muted",
};

function RequirementsTab({ result }: { result: EvaluationResult }) {
  return (
    <ul className="divide-y divide-zinc-800/70">
      {result.requirements.map((r) => (
        <li key={r.id} className="flex items-center gap-3 py-2">
          <StatusDot tone={STATUS_TONE[r.status]} />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-zinc-200">{r.description}</p>
            <p className="font-mono text-[11px] text-zinc-500">{r.id}</p>
          </div>
          <Badge tone={STATUS_TONE[r.status]}>
            {r.passed}/{r.total} · {r.status.replace("_", " ")}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function GamingTab({ result }: { result: EvaluationResult }) {
  return (
    <div className="space-y-3">
      <p className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200/80">
        Heuristic only. These checks look for hardcoded URL literals, references to test-runner
        internals and a gap between visible and hidden test results. They can be wrong in both
        directions. A HIGH-confidence signal caps the overall score at 60.
      </p>
      {result.gaming_signals.length === 0 ? (
        <Empty>No suspicious patterns found.</Empty>
      ) : (
        <ul className="divide-y divide-zinc-800/70">
          {result.gaming_signals.map((s, i) => (
            <li key={i} className="flex items-start gap-3 py-2">
              <span className="mt-0.5">
                <Badge tone={severityTone(s.confidence)}>{s.confidence}</Badge>
              </span>
              <div>
                <p className="text-sm text-zinc-200">{s.message}</p>
                <p className="font-mono text-[11px] text-zinc-500">
                  {s.rule}
                  {s.file && ` · ${s.file}${s.line ? `:${s.line}` : ""}`}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function FindingsTabs({ result }: { result: EvaluationResult }) {
  const [tab, setTab] = useState<TabKey>("functional");
  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: "functional", label: "Functional", count: result.failures.filter((f) => FUNCTIONAL_CATEGORIES.has(f.category)).length },
    { key: "security", label: "Security", count: result.security_findings.length },
    { key: "requirements", label: "Requirements", count: result.requirements.filter((r) => r.status !== "met").length },
    { key: "gaming", label: "Test Gaming", count: result.gaming_signals.length },
  ];

  return (
    <Card title="Detailed findings">
      <div className="mb-4 flex flex-wrap gap-1 border-b border-zinc-800" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
              tab === t.key
                ? "border-emerald-400 text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.label}
            <span className={`ml-2 font-mono text-xs ${t.count ? "text-amber-400" : "text-zinc-600"}`}>
              {t.count}
            </span>
          </button>
        ))}
      </div>
      {tab === "functional" && <FunctionalTab result={result} />}
      {tab === "security" && <SecurityTab result={result} />}
      {tab === "requirements" && <RequirementsTab result={result} />}
      {tab === "gaming" && <GamingTab result={result} />}
    </Card>
  );
}
