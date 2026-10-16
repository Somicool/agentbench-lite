import { scoreTone, toneText } from "./ui";

export interface RunSummary {
  id: string;
  name: string;
  score: number;
}

interface Props {
  runs: RunSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

export default function RunHistory({ runs, activeId, onSelect }: Props) {
  if (runs.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-zinc-500">Runs</span>
      {runs.map((run) => (
        <button
          key={run.id}
          onClick={() => onSelect(run.id)}
          aria-pressed={run.id === activeId}
          className={`rounded-md border px-2.5 py-1 font-mono text-xs transition-colors ${
            run.id === activeId
              ? "border-zinc-500 bg-zinc-800"
              : "border-zinc-800 hover:border-zinc-600"
          }`}
        >
          {run.name} <span className={toneText[scoreTone(run.score)]}>{run.score}</span>
        </button>
      ))}
    </div>
  );
}
