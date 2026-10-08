import { useState } from "react";
import { SWOTReportDelta } from "@/types/research";
import { cn } from "@/lib/utils";
import { Compass, Sparkles } from "lucide-react";

const QUADRANTS = [
  { key: "strengths", label: "Strengths", tone: "border-emerald-200", dot: "bg-emerald-500" },
  { key: "weaknesses", label: "Weaknesses", tone: "border-rose-200", dot: "bg-rose-500" },
  { key: "opportunities", label: "Opportunities", tone: "border-sky-200", dot: "bg-sky-500" },
  { key: "threats", label: "Threats", tone: "border-amber-200", dot: "bg-amber-500" },
] as const;

export function MarketBrief({ report }: { report: SWOTReportDelta }) {
  const summary = report.dashboard_insights?.executive_summary;
  const gap = report.positioning_gap || report.market_positioning_gap;
  if (!summary && !gap?.hook_angle) return null;

  return (
    <div className="grid gap-3 lg:grid-cols-5">
      {summary && (
        <div className={cn("rounded-2xl bg-ink text-white p-5 shadow-lift", gap?.hook_angle ? "lg:col-span-3" : "lg:col-span-5")}>
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            <Sparkles className="w-3.5 h-3.5" /> The landscape in brief
          </div>
          <p className="mt-2 text-sm leading-relaxed text-zinc-100">{summary}</p>
        </div>
      )}
      {gap?.hook_angle && (
        <div className={cn("rounded-2xl border border-line bg-white p-5 shadow-card", summary ? "lg:col-span-2" : "lg:col-span-5")}>
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            <Compass className="w-3.5 h-3.5" /> Gap no rival covers
          </div>
          {gap.quadrant && <div className="mt-2 font-display text-base font-bold text-ink">{gap.quadrant}</div>}
          <p className="mt-1 text-xs text-ink-soft leading-relaxed">{gap.hook_angle}</p>
        </div>
      )}
    </div>
  );
}

export function MarketPanel({ report }: { report: SWOTReportDelta }) {
  const [showAllAttrs, setShowAllAttrs] = useState(false);
  const swot = report.swot || report.swot_analysis;
  const taxonomy = report.dynamic_taxonomy;
  // ponytail: mirrors the backend's furniture filter so reports saved before it stay readable;
  // delete once old runs have aged out.
  const minor = (taxonomy?.minor_attributes ?? []).filter(
    (a) => !/\d|monday|tuesday|wednesday|thursday|friday|saturday|sunday|_ago$/i.test(a)
  );

  return (
    <div className="space-y-3">
      {swot && (
        <div className="grid gap-3 sm:grid-cols-2">
          {QUADRANTS.map((q) => {
            const items = swot[q.key] ?? [];
            return (
              <div key={q.key} className={cn("rounded-2xl border bg-white p-4 shadow-card", q.tone)}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn("w-2 h-2 rounded-full", q.dot)} />
                  <h3 className="text-xs font-bold text-ink">{q.label}</h3>
                  <span className="text-[10px] font-mono text-ink-faint">{items.length}</span>
                </div>
                {items.length ? (
                  <ul className="space-y-1.5">
                    {items.map((item, i) => (
                      <li key={i} className="text-xs text-ink-soft leading-relaxed">
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-ink-faint italic">Nothing evidenced.</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {taxonomy && (
        <div className="rounded-2xl border border-line bg-white p-4 shadow-card space-y-3">
          <div>
            <h3 className="text-xs font-bold text-ink">What buyers in this market compare</h3>
            <p className="text-[11px] text-ink-faint">Learned from the pages read during this run — the deal-breakers first.</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {taxonomy.critical_jtbd_drivers.map((d) => (
              <span key={d} className="px-2.5 py-1 rounded-lg bg-ink text-white text-[11px] font-medium">
                {d.split(":")[0].replace(/_/g, " ")}
              </span>
            ))}
            {(showAllAttrs ? minor : minor.slice(0, 8)).map((a) => (
              <span key={a} className="px-2 py-1 rounded-lg bg-canvas text-ink-soft text-[11px]">
                {a.replace(/_/g, " ")}
              </span>
            ))}
            {minor.length > 8 && (
              <button
                type="button"
                onClick={() => setShowAllAttrs((v) => !v)}
                className="px-2 py-1 rounded-lg text-[11px] font-semibold text-ink-soft hover:text-ink"
              >
                {showAllAttrs ? "Show fewer" : `+${minor.length - 8} more`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
