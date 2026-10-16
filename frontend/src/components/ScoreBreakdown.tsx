import type { EvaluationResult } from "../types";
import { Card } from "./ui";

export default function ScoreBreakdown({ result }: { result: EvaluationResult }) {
  return (
    <Card title="How the score was calculated">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-zinc-500">
            <tr>
              <th className="pb-2 font-normal">Dimension</th>
              <th className="pb-2 text-right font-normal">Points</th>
              <th className="pb-2 pl-4 font-normal">Evidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/70">
            {result.score_breakdown.map((c) => (
              <tr key={c.key}>
                <td className="py-1.5 pr-3 text-zinc-300">{c.label}</td>
                <td className="whitespace-nowrap py-1.5 text-right font-mono text-zinc-100">
                  {c.points.toFixed(1)}/{c.weight}
                </td>
                <td className="py-1.5 pl-4 font-mono text-zinc-500">{c.explanation}</td>
              </tr>
            ))}
            {result.score_cap_applied && (
              <tr>
                <td className="py-1.5 text-zinc-300">Raw total</td>
                <td className="py-1.5 text-right font-mono text-zinc-100">{result.raw_score}/100</td>
                <td className="py-1.5 pl-4 font-mono text-red-300">
                  capped: HIGH-confidence gaming signal
                </td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="border-t border-zinc-700">
              <td className="pt-2 font-medium text-zinc-100">TOTAL</td>
              <td className="pt-2 text-right font-mono font-medium text-zinc-100">
                {result.overall_score}/100
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}
