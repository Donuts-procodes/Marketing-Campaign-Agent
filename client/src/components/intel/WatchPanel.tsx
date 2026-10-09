import { useMemo, useState } from "react";
import { RivalView } from "@/lib/rivalMetrics";
import { safeHref, cn } from "@/lib/utils";
import { LeapBenchmark, ThreatEntry, ThreatWatch, WedgeCandidate, WedgeScan } from "@/types/research";
import { AlertTriangle, ArrowRight, Compass, ExternalLink, Loader2, Search, Sparkles, TrendingDown, TrendingUp } from "lucide-react";

/**
 * Two tiers on one panel, summary before detail:
 *  - "Who could overtake you": the few peer rivals with the most momentum (Tier 2).
 *  - "Everyone in your niche": the broad scan, so an emerging brand is never missed (Tier 1).
 */

const H = "text-[10px] font-bold uppercase tracking-wider text-ink-faint";

const MOMENTUM: Record<string, { label: string; cls: string }> = {
  accelerating: { label: "Accelerating", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  steady: { label: "Steady", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  slowing: { label: "Slowing", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  baseline: { label: "Baseline set", cls: "bg-canvas text-ink-soft border-line" },
  no_data: { label: "No movement data", cls: "bg-white text-ink-faint border-line border-dashed" },
};

const SCALE: Record<string, { label: string; cls: string }> = {
  peer: { label: "Your size", cls: "bg-sky-50 text-sky-800 border-sky-200" },
  larger: { label: "Larger", cls: "bg-violet-50 text-violet-800 border-violet-200" },
  incumbent: { label: "Category giant", cls: "bg-zinc-100 text-zinc-700 border-zinc-200" },
  unknown: { label: "Size unknown", cls: "bg-white text-ink-faint border-line" },
};

function Chip({ label, cls }: { label: string; cls: string }) {
  return <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded-md border text-[10px] font-semibold", cls)}>{label}</span>;
}

function DirectionIcon({ direction }: { direction?: string }) {
  if (direction === "up") return <TrendingUp className="w-3 h-3 text-rose-600 shrink-0" aria-label="rising" />;
  if (direction === "down") return <TrendingDown className="w-3 h-3 text-emerald-600 shrink-0" aria-label="falling" />;
  if (direction === "new") return <Sparkles className="w-3 h-3 text-ink-faint shrink-0" aria-label="first reading" />;
  return <ArrowRight className="w-3 h-3 text-ink-faint shrink-0" aria-label="flat" />;
}

function ThreatBar({ score }: { score: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const tone = score >= 0.6 ? "bg-rose-500" : score >= 0.35 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2" title={`Threat score ${pct}/100`}>
      <div className="h-1.5 flex-1 rounded-full bg-canvas overflow-hidden">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-semibold tabular-nums text-ink w-7 text-right">{pct}</span>
    </div>
  );
}

function ThreatCard({ entry, onOpen }: { entry: ThreatEntry; onOpen?: () => void }) {
  const m = MOMENTUM[entry.momentum] ?? MOMENTUM.baseline;
  const s = SCALE[entry.scale ?? "unknown"] ?? SCALE.unknown;
  const signals = (entry.signals ?? []).filter((x) => x.value || x.change).slice(0, 3);
  return (
    <article className="rounded-2xl border border-line bg-white p-4 shadow-card flex flex-col gap-3 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {onOpen ? (
            <button type="button" onClick={onOpen} className="font-display text-base font-bold text-ink hover:underline text-left truncate max-w-full">
              {entry.brand_name}
            </button>
          ) : (
            <span className="font-display text-base font-bold text-ink truncate">{entry.brand_name}</span>
          )}
          {entry.headline && <p className="text-xs text-ink-soft mt-0.5">{entry.headline}</p>}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <Chip {...m} />
          <Chip {...s} />
        </div>
      </div>

      <ThreatBar score={entry.threat_score} />

      {signals.length > 0 && (
        <ul className="space-y-1.5">
          {signals.map((sig) => (
            <li key={sig.key} className="flex items-start gap-1.5 text-[11px] leading-snug min-w-0">
              <DirectionIcon direction={sig.direction} />
              <span className="text-ink-faint shrink-0">{sig.label}</span>
              <span className="text-ink min-w-0 break-words">
                {sig.value}
                {sig.change && <span className="text-ink-faint"> · {sig.change}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {!!entry.what_changed?.length && (
        <div className="space-y-1">
          <div className={H}>Since last scan</div>
          <ul className="space-y-0.5">
            {entry.what_changed.slice(0, 3).map((c, i) => (
              <li key={i} className="text-[11px] text-ink-soft pl-2 border-l-2 border-line">
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {entry.counter_move && (
        <div className="mt-auto rounded-lg bg-amber-50 border border-amber-200 px-2.5 py-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Your move</div>
          <p className="text-[11px] text-amber-900 leading-relaxed mt-0.5">{entry.counter_move}</p>
        </div>
      )}
    </article>
  );
}

type Filter = "all" | "peer" | "emerging";

function CandidateRow({
  c,
  isNew,
  busy,
  onResearch,
  onOpen,
}: {
  c: WedgeCandidate;
  isNew: boolean;
  busy: boolean;
  onResearch?: () => void;
  onOpen?: () => void;
}) {
  const s = SCALE[c.scale ?? "unknown"] ?? SCALE.unknown;
  const href = c.url ? safeHref(c.url) : null;
  return (
    <li className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 px-3 py-2.5 min-w-0">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-semibold text-ink truncate">{c.brand_name}</span>
          {href && (
            <a href={href} target="_blank" rel="noreferrer" className="text-ink-faint hover:text-ink" aria-label={`Open ${c.brand_name}`}>
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
          <Chip {...s} />
          {c.emerging && <Chip label="Emerging" cls="bg-rose-50 text-rose-700 border-rose-200" />}
          {isNew && <Chip label="New since last scan" cls="bg-indigo-50 text-indigo-700 border-indigo-200" />}
        </div>
        <p className="text-[11px] text-ink-soft mt-0.5 line-clamp-2">
          {c.positioning || <span className="italic text-ink-faint">No stated angle found</span>}
        </p>
        <p className="text-[10px] text-ink-faint mt-0.5 tabular-nums">
          {c.mentions ?? 0} mention{c.mentions === 1 ? "" : "s"}
          {c.launch_date ? ` · launched ${c.launch_date}` : ""}
          {c.first_seen ? ` · first seen ${c.first_seen}` : ""}
        </p>
      </div>
      <div className="shrink-0">
        {c.deep_researched ? (
          onOpen ? (
            <button type="button" onClick={onOpen} className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink hover:underline">
              Open profile <ArrowRight className="w-3 h-3" />
            </button>
          ) : (
            <span className="text-[11px] text-ink-faint">Profiled</span>
          )
        ) : onResearch ? (
          <button
            type="button"
            onClick={onResearch}
            disabled={busy}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-line bg-white hover:bg-canvas text-[11px] font-semibold text-ink disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
            Research deeper
          </button>
        ) : null}
      </div>
    </li>
  );
}

interface WatchPanelProps {
  threatWatch?: ThreatWatch | null;
  wedgeScan?: WedgeScan | null;
  leapBenchmarks?: LeapBenchmark[] | null;
  rivals: RivalView[];
  onOpenRival: (index: number) => void;
  /** Promotes a niche candidate into a full profile (the find-more flow). */
  onResearch?: (name: string) => Promise<void>;
  busy?: boolean;
}

export function WatchPanel({
  threatWatch,
  wedgeScan,
  leapBenchmarks,
  rivals,
  onOpenRival,
  onResearch,
  busy,
}: WatchPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const [pending, setPending] = useState<string | null>(null);

  const indexByName = useMemo(() => {
    const m = new Map<string, number>();
    rivals.forEach((r) => m.set(r.name.toLowerCase(), r.index));
    return m;
  }, [rivals]);
  const openFor = (name: string) => {
    const idx = indexByName.get(name.toLowerCase());
    return idx == null ? undefined : () => onOpenRival(idx);
  };

  const newSet = useMemo(() => new Set((wedgeScan?.new_since_last_scan ?? []).map((n) => n.toLowerCase())), [wedgeScan]);
  const candidates = useMemo(() => {
    const all = wedgeScan?.candidates ?? [];
    if (filter === "peer") return all.filter((c) => c.scale === "peer");
    if (filter === "emerging") return all.filter((c) => c.emerging);
    return all;
  }, [wedgeScan, filter]);

  const research = async (name: string) => {
    if (!onResearch || pending) return;
    setPending(name);
    try {
      await onResearch(name);
    } finally {
      setPending(null);
    }
  };

  const watched = threatWatch?.watched ?? [];
  const alerts = threatWatch?.alerts ?? [];
  const peerCount = (wedgeScan?.candidates ?? []).filter((c) => c.scale === "peer").length;
  const emergingCount = (wedgeScan?.candidates ?? []).filter((c) => c.emerging).length;

  if (!watched.length && !(wedgeScan?.candidates?.length) && !(leapBenchmarks?.length)) {
    return (
      <p className="rounded-2xl border border-dashed border-line bg-white/50 p-6 text-center text-xs text-ink-faint">
        Momentum tracking starts with the next research run. Refresh to set the baseline.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {alerts.length > 0 && (
        <div role="status" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 space-y-1">
          {alerts.map((a, i) => (
            <p key={i} className="flex items-start gap-2 text-xs text-rose-900">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-rose-600" />
              {a}
            </p>
          ))}
        </div>
      )}

      {!!leapBenchmarks?.length && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className={cn(H, "flex items-center gap-1.5")}>
              <Sparkles className="w-3 h-3 text-indigo-600" /> Breakout Leap Benchmarks (Wedge Peers Who Scaled Big)
            </div>
            <div className="text-[11px] text-ink-faint">
              Rivals that originated in this wedge and leaped to marquee enterprise clients, deals & scale
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {leapBenchmarks.map((b) => {
              const openRival = openFor(b.brand_name);
              return (
                <article
                  key={b.brand_name}
                  className="rounded-2xl border border-indigo-200/80 bg-gradient-to-b from-indigo-50/40 via-white to-white p-4 shadow-card flex flex-col justify-between gap-3 min-w-0"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        {openRival ? (
                          <button
                            type="button"
                            onClick={openRival}
                            className="font-display text-base font-bold text-ink hover:text-indigo-600 hover:underline text-left truncate max-w-full"
                          >
                            {b.brand_name}
                          </button>
                        ) : (
                          <span className="font-display text-base font-bold text-ink truncate">
                            {b.brand_name}
                          </span>
                        )}
                        <p className="text-[11px] text-indigo-900 font-medium mt-0.5">
                          {b.current_scale}
                        </p>
                      </div>
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-indigo-200 bg-white text-[10px] font-semibold text-indigo-800 shrink-0">
                        <Sparkles className="w-3 h-3 text-indigo-500" />
                        Breakout Leap
                      </span>
                    </div>

                    <p className="text-xs text-ink-soft leading-relaxed line-clamp-2">
                      <strong className="text-ink font-semibold">Origin:</strong> {b.origin_story}
                    </p>

                    {(b.flagship_clients ?? []).length > 0 && (
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-ink-faint">
                          Marquee Clients:
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {(b.flagship_clients ?? []).slice(0, 4).map((client, i) => (
                            <span
                              key={i}
                              className="px-1.5 py-0.5 rounded bg-white border border-line text-[10px] font-semibold text-ink"
                            >
                              {client}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {(b.merchant_takeaway_playbook ?? []).length > 0 && (
                      <div className="rounded-lg bg-emerald-50/70 border border-emerald-100 p-2 space-y-0.5">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">
                          Takeaway Playbook
                        </span>
                        <p className="text-[11px] text-emerald-950 leading-relaxed line-clamp-2">
                          {(b.merchant_takeaway_playbook ?? [])[0]}
                        </p>
                      </div>
                    )}
                  </div>

                  {openRival && (
                    <button
                      type="button"
                      onClick={openRival}
                      className="inline-flex items-center justify-center gap-1.5 w-full py-1.5 px-3 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-800 text-xs font-semibold transition"
                    >
                      <span>Study Full Trajectory & Playbook</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}

      {watched.length > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className={H}>Who could overtake you</div>
            <div className="text-[11px] text-ink-faint">
              {threatWatch?.baseline_date ? `Movement since ${threatWatch.baseline_date}` : "First scan: movement shows from the next refresh"}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {watched.map((e) => (
              <ThreatCard key={e.brand_name} entry={e} onOpen={openFor(e.brand_name)} />
            ))}
          </div>
        </div>
      )}

      {!!wedgeScan?.candidates?.length && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div className="min-w-0">
              <div className={cn(H, "flex items-center gap-1.5")}>
                <Compass className="w-3 h-3" /> Everyone in your niche
              </div>
              {wedgeScan.wedge && <p className="text-xs text-ink-soft mt-0.5">{wedgeScan.wedge}</p>}
            </div>
            <div role="tablist" aria-label="Filter niche players" className="inline-flex rounded-lg border border-line bg-white p-0.5">
              {(
                [
                  ["all", `All ${wedgeScan.candidates.length}`],
                  ["peer", `Your size ${peerCount}`],
                  ["emerging", `Emerging ${emergingCount}`],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={filter === id}
                  onClick={() => setFilter(id)}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-[11px] font-semibold transition",
                    filter === id ? "bg-ink text-white" : "text-ink-soft hover:text-ink"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {candidates.length ? (
            <ul className="rounded-2xl border border-line bg-white divide-y divide-line">
              {candidates.map((c) => (
                <CandidateRow
                  key={c.brand_name}
                  c={c}
                  isNew={newSet.has(c.brand_name.toLowerCase())}
                  busy={!!busy || pending === c.brand_name}
                  onResearch={onResearch ? () => research(c.brand_name) : undefined}
                  onOpen={openFor(c.brand_name)}
                />
              ))}
            </ul>
          ) : (
            <p className="rounded-2xl border border-dashed border-line bg-white/50 p-4 text-center text-xs text-ink-faint">
              No players match this filter.
            </p>
          )}
        </div>
      )}

      {threatWatch?.method_note && <p className="text-[11px] text-ink-faint leading-relaxed max-w-3xl">{threatWatch.method_note}</p>}
    </div>
  );
}
