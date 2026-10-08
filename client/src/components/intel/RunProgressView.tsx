import { useEffect, useMemo, useState } from "react";
import { TelemetryLogItem } from "@/types/campaign";
import { STAGES, formatElapsed, parseRunProgress } from "@/lib/runProgress";
import { cn } from "@/lib/utils";
import { AlertCircle, ArrowRight, CheckCircle2, Loader2, RefreshCw, Terminal } from "lucide-react";

interface RunProgressViewProps {
  logs: TelemetryLogItem[];
  connectionStatus: string;
  error?: string | null;
  productName?: string;
  onRetry?: () => void;
  onOpenLog?: () => void;
}

const SHIMMER =
  "bg-[linear-gradient(90deg,#F1ECE1_0px,#FBF8F2_120px,#F1ECE1_240px)] bg-[length:800px_100%] animate-shimmer";

export function RunProgressView({
  logs,
  connectionStatus,
  error,
  productName,
  onRetry,
  onOpenLog,
}: RunProgressViewProps) {
  const progress = useMemo(() => parseRunProgress(logs), [logs]);
  const failed = connectionStatus === "ERROR";

  // Ticks the elapsed clock; stops once the run is over.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (failed) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [failed]);
  const elapsed = progress.startedAt ? now - progress.startedAt : 0;

  const counters = [
    { label: "web results scanned", value: progress.stats.results },
    { label: "competitors considered", value: progress.candidates ?? 0 },
    { label: "rival pages read", value: progress.stats.pages },
    { label: "live ads found", value: progress.stats.adHooks },
  ];
  const recent = progress.activity.slice(-6).reverse();

  return (
    <div className="w-full max-w-4xl mx-auto pt-6 pb-16 space-y-5 animate-fade-up">
      {/* Headline */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
            Competitor research{productName ? ` · ${productName}` : ""}
          </p>
          <h1 className="mt-1 font-display text-2xl sm:text-3xl font-bold tracking-tight text-ink">
            {failed ? "The research run stopped" : STAGES[progress.stageIndex].label + "…"}
          </h1>
        </div>
        <div className="flex items-center gap-3 text-xs text-ink-soft">
          {!failed && (
            <span className="inline-flex items-center gap-1.5 font-mono tabular-nums">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {formatElapsed(elapsed)}
            </span>
          )}
          {onOpenLog && (
            <button
              type="button"
              onClick={onOpenLog}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-line bg-white hover:bg-[#FBF8F2] font-medium text-ink transition"
            >
              <Terminal className="w-3.5 h-3.5" />
              Agent log
            </button>
          )}
        </div>
      </div>

      {/* Stage stepper */}
      <ol className="grid grid-cols-2 md:grid-cols-4 gap-2" aria-label="Research stages">
        {STAGES.map((stage, i) => {
          const done = i < progress.stageIndex;
          const current = i === progress.stageIndex && !failed;
          return (
            <li
              key={stage.id}
              aria-current={current ? "step" : undefined}
              className={cn(
                "rounded-xl border px-3 py-2.5 transition-colors",
                done && "border-emerald-200 bg-emerald-50/60",
                current && "border-ink bg-white shadow-card",
                !done && !current && "border-line bg-white/50"
              )}
            >
              <div className="flex items-center gap-2">
                {done ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                ) : current ? (
                  <span className="relative flex h-2.5 w-2.5 shrink-0 mx-[3px]">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ink/40" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-ink" />
                  </span>
                ) : (
                  <span className="w-4 h-4 rounded-full border border-line shrink-0 text-[9px] flex items-center justify-center text-ink-faint">
                    {i + 1}
                  </span>
                )}
                <span className={cn("text-xs font-semibold", !done && !current ? "text-ink-faint" : "text-ink")}>
                  {stage.label}
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      {/* Live counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {counters.map((c) => (
          <div key={c.label} className="rounded-xl border border-line bg-white px-3.5 py-3 shadow-card">
            <div className="font-display text-2xl font-bold tabular-nums text-ink">{c.value.toLocaleString()}</div>
            <div className="text-[11px] text-ink-soft">{c.label}</div>
          </div>
        ))}
      </div>

      {/* Shortlist: the five rivals are known long before the report exists */}
      <section className="rounded-2xl border border-line bg-white p-4 sm:p-5 shadow-card space-y-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-bold text-ink">Your closest rivals</h2>
          <span className="text-[11px] text-ink-faint">
            {progress.shortlist.length
              ? "Locked in — now reading their websites, reviews and ads"
              : "Appears as soon as the search settles on the top five"}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
          {(progress.shortlist.length ? progress.shortlist : Array.from({ length: 5 }, () => "")).map((name, i) =>
            name ? (
              <div
                key={name}
                className="rounded-xl border border-line px-3 py-2.5 animate-fade-up"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div className="text-xs font-bold text-ink truncate" title={name}>
                  {name}
                </div>
                <div className={cn("mt-2 h-1.5 rounded-full", progress.stageIndex >= 3 ? "bg-emerald-200" : SHIMMER)} />
                <div className="mt-1 text-[10px] text-ink-faint">
                  {progress.stageIndex >= 3 ? "Researched" : "Researching…"}
                </div>
              </div>
            ) : (
              <div key={i} className="rounded-xl border border-dashed border-line px-3 py-2.5">
                <div className={cn("h-3 w-2/3 rounded", SHIMMER)} />
                <div className={cn("mt-2 h-1.5 rounded-full", SHIMMER)} />
              </div>
            )
          )}
        </div>
      </section>

      {/* Activity feed in plain language */}
      <section className="rounded-2xl border border-line bg-white p-4 sm:p-5 shadow-card">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-ink">What the agent is doing</h2>
          {onOpenLog && (
            <button
              type="button"
              onClick={onOpenLog}
              className="text-[11px] font-semibold text-ink-soft hover:text-ink inline-flex items-center gap-1"
            >
              Full log <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
        {recent.length ? (
          <ul className="divide-y divide-line">
            {recent.map((a, i) => (
              <li key={a.id} className="flex items-center gap-3 py-2 animate-fade-up">
                <span
                  className={cn(
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    i === 0 && !failed ? "bg-ink animate-pulse" : "bg-zinc-300"
                  )}
                />
                <span className={cn("text-xs flex-1", i === 0 ? "text-ink font-medium" : "text-ink-soft")}>
                  {a.text}
                </span>
                {progress.startedAt && (
                  <span className="text-[10px] font-mono text-ink-faint tabular-nums">
                    {formatElapsed(a.timestamp - progress.startedAt)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-ink-faint py-2">Connecting to the research agent…</p>
        )}
      </section>

      {failed && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-rose-800">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error || "The connection to the research run was lost."}</span>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
