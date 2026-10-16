import { useEffect, useState } from "react";
import { createReport } from "../api";
import type { EvaluationResult } from "../types";
import { Card } from "./ui";

export default function ReportPanel({ result }: { result: EvaluationResult }) {
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setReport(null);
    setError(null);
  }, [result.evaluation_id]);

  const generate = async () => {
    setError(null);
    try {
      setReport((await createReport(result.evaluation_id)).content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate the report");
    }
  };

  const copy = async () => {
    if (!report) return;
    await navigator.clipboard.writeText(report);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const button =
    "rounded border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100";

  return (
    <Card
      title="Report"
      action={
        <div className="flex gap-2">
          {report && (
            <button className={button} onClick={copy}>
              {copied ? "Copied" : "Copy"}
            </button>
          )}
          <button className={button} onClick={generate}>
            {report ? "Regenerate" : "Generate report"}
          </button>
        </div>
      }
    >
      {error && <p className="text-sm text-red-400">{error}</p>}
      {report ? (
        <pre className="max-h-[32rem] overflow-auto whitespace-pre font-mono text-xs leading-relaxed text-zinc-300">
          {report}
        </pre>
      ) : (
        !error && (
          <p className="text-sm text-zinc-500">
            Generate a plain-text report with the score calculation, failures and recommendations.
          </p>
        )
      )}
    </Card>
  );
}
