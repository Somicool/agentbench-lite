import type { ChangeEvent } from "react";
import type { ExampleInfo } from "../types";
import { Card } from "./ui";

export type RepoSource = "example" | "upload";

interface Props {
  description: string;
  onDescription: (value: string) => void;
  source: RepoSource;
  onSource: (value: RepoSource) => void;
  examples: ExampleInfo[];
  example: string;
  onExample: (value: string) => void;
  file: File | null;
  onFile: (file: File | null) => void;
  loading: boolean;
  onRun: () => void;
}

const tabClass = (active: boolean) =>
  `rounded px-3 py-1 text-xs font-medium transition-colors ${
    active ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
  }`;

export default function TaskForm(props: Props) {
  const { source, examples, example, file, loading } = props;
  const canRun =
    !loading && props.description.trim().length > 0 && (source === "example" ? !!example : !!file);

  const handleFile = (event: ChangeEvent<HTMLInputElement>) =>
    props.onFile(event.target.files?.[0] ?? null);

  return (
    <Card title="Evaluation input">
      <div className="space-y-4">
        <div>
          <label htmlFor="task" className="mb-1.5 block text-xs text-zinc-400">
            Task description
          </label>
          <textarea
            id="task"
            value={props.description}
            onChange={(e) => props.onDescription(e.target.value)}
            rows={9}
            className="w-full resize-y rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-200 placeholder:text-zinc-600"
            placeholder="Describe what the AI-generated repository should do"
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs text-zinc-400">Repository</span>
            <div className="flex gap-1 rounded-md bg-zinc-950 p-0.5" role="tablist">
              <button
                role="tab"
                aria-selected={source === "example"}
                className={tabClass(source === "example")}
                onClick={() => props.onSource("example")}
              >
                Bundled example
              </button>
              <button
                role="tab"
                aria-selected={source === "upload"}
                className={tabClass(source === "upload")}
                onClick={() => props.onSource("upload")}
              >
                Upload ZIP
              </button>
            </div>
          </div>

          {source === "example" ? (
            <div className="space-y-1.5">
              {examples.map((item) => (
                <label
                  key={item.name}
                  className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 text-sm transition-colors ${
                    example === item.name
                      ? "border-emerald-500/50 bg-emerald-500/5"
                      : "border-zinc-800 hover:border-zinc-700"
                  }`}
                >
                  <input
                    type="radio"
                    name="example"
                    value={item.name}
                    checked={example === item.name}
                    onChange={() => props.onExample(item.name)}
                    className="mt-1 accent-emerald-400"
                  />
                  <span>
                    <span className="block font-mono text-xs text-zinc-100">{item.name}</span>
                    <span className="block text-xs text-zinc-500">{item.description}</span>
                  </span>
                </label>
              ))}
              {examples.length === 0 && (
                <p className="text-xs text-zinc-500">No bundled examples found.</p>
              )}
            </div>
          ) : (
            <div>
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={handleFile}
                aria-label="Repository ZIP file"
                className="block w-full text-xs text-zinc-400 file:mr-3 file:cursor-pointer file:rounded file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-xs file:text-zinc-200 hover:file:bg-zinc-700"
              />
              <p className="mt-1.5 text-xs text-zinc-500">
                Max 5 MB. Must contain <span className="font-mono">url_validator.py</span>. Treated
                as untrusted input.
              </p>
            </div>
          )}
        </div>

        <button
          onClick={props.onRun}
          disabled={!canRun}
          className="w-full rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-zinc-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
        >
          {loading ? "Running hidden tests…" : "Run Evaluation"}
        </button>
      </div>
    </Card>
  );
}
