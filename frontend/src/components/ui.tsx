import type { ReactNode } from "react";
import type { Severity } from "../types";

export type Tone = "good" | "warn" | "bad" | "muted";

export const toneText: Record<Tone, string> = {
  good: "text-emerald-400",
  warn: "text-amber-400",
  bad: "text-red-400",
  muted: "text-zinc-400",
};

export const toneBg: Record<Tone, string> = {
  good: "bg-emerald-400",
  warn: "bg-amber-400",
  bad: "bg-red-400",
  muted: "bg-zinc-500",
};

export function scoreTone(score: number): Tone {
  if (score >= 80) return "good";
  if (score >= 60) return "warn";
  return "bad";
}

export function severityTone(severity: Severity): Tone {
  return severity === "HIGH" ? "bad" : severity === "MEDIUM" ? "warn" : "muted";
}

export function StatusDot({ tone }: { tone: Tone }) {
  return <span aria-hidden className={`inline-block h-2 w-2 shrink-0 rounded-full ${toneBg[tone]}`} />;
}

export function Card({
  title,
  action,
  children,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60">
      {title && (
        <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-400">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  const styles: Record<Tone, string> = {
    good: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    warn: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    bad: "border-red-500/30 bg-red-500/10 text-red-300",
    muted: "border-zinc-700 bg-zinc-800/60 text-zinc-300",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[11px] ${styles[tone]}`}>
      {children}
    </span>
  );
}

export function ScoreBar({ value, tone }: { value: number; tone: Tone }) {
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`h-full rounded-full ${toneBg[tone]}`} style={{ width: `${value}%` }} />
    </div>
  );
}
