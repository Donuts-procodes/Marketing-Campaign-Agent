import { useMemo, useState } from "react";
import { SWOTReportDelta } from "@/types/research";
import { confidenceOf, hostOf } from "@/lib/rivalMetrics";
import { safeHref, cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";

export function SourcesPanel({ report }: { report: SWOTReportDelta }) {
  const [openHost, setOpenHost] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const groups = useMemo(() => {
    const byHost = new Map<string, string[]>();
    for (const url of report.source_urls ?? []) {
      if (!safeHref(url)) continue;
      const host = hostOf(url) ?? "other";
      byHost.set(host, [...(byHost.get(host) ?? []), url]);
    }
    return [...byHost.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [report.source_urls]);

  const conf = confidenceOf(report.dqs_score, report.assumptions_tagged);
  const diags = report.validation_diagnostics ?? [];
  const reviewerRemoved = diags.filter((d) => d.startsWith("[VALIDATOR]"));
  const yourEdits = diags.filter((d) => d.startsWith("[MERCHANT_EDIT]"));
  const corrections = diags.length - reviewerRemoved.length - yourEdits.length;
  const visible = showAll ? groups : groups.slice(0, 12);

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="lg:col-span-2 rounded-2xl border border-line bg-white shadow-card overflow-hidden">
        <div className="px-4 py-3 border-b border-line flex items-baseline justify-between">
          <h3 className="text-xs font-bold text-ink">Where this came from</h3>
          <span className="text-[11px] text-ink-faint">
            {report.source_urls?.length ?? 0} pages · {groups.length} websites
          </span>
        </div>
        <ul className="divide-y divide-line">
          {visible.map(([host, urls]) => {
            const open = openHost === host;
            return (
              <li key={host}>
                <button
                  type="button"
                  onClick={() => setOpenHost(open ? null : host)}
                  aria-expanded={open}
                  className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-[#FBF8F2] transition"
                >
                  {open ? <ChevronDown className="w-3.5 h-3.5 text-ink-faint" /> : <ChevronRight className="w-3.5 h-3.5 text-ink-faint" />}
                  <span className="text-xs font-semibold text-ink flex-1 truncate">{host}</span>
                  <span className="text-[10px] font-mono text-ink-faint">{urls.length}</span>
                </button>
                {open && (
                  <ul className="pb-2 px-4 space-y-0.5 animate-fade-in">
                    {urls.map((u) => (
                      <li key={u}>
                        <a
                          href={safeHref(u)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 pl-5 py-1 text-[11px] text-ink-soft hover:text-ink truncate"
                        >
                          <ExternalLink className="w-3 h-3 shrink-0" />
                          <span className="truncate">{u.replace(/^https?:\/\/(www\.)?/, "")}</span>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
        {groups.length > 12 && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="w-full px-4 py-2 border-t border-line text-[11px] font-semibold text-ink-soft hover:text-ink"
          >
            {showAll ? "Show fewer websites" : `Show all ${groups.length} websites`}
          </button>
        )}
      </div>

      <div className="rounded-2xl border border-line bg-white p-4 shadow-card space-y-3 h-fit">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-ink" />
          <h3 className="text-xs font-bold text-ink">About this data</h3>
        </div>
        <span className={cn("inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border text-[11px] font-semibold", conf.tone)}>
          <span className={cn("w-1.5 h-1.5 rounded-full", conf.dot)} />
          {conf.label} · quality score {Math.round(report.dqs_score * 100)}%
        </span>
        <ul className="space-y-1.5 text-[11px] text-ink-soft leading-relaxed">
          <li>Every claim in the report was checked against the page it came from{corrections ? ` — ${corrections} were corrected or removed` : ""}.</li>
          {reviewerRemoved.length > 0 && (
            <li>
              A second reviewer then compared each item with its source passage and removed {reviewerRemoved.length} that the
              passage didn't back up (wrong company, not a real customer opinion, or generic filler).
            </li>
          )}
          {yourEdits.length > 0 && <li>You corrected {yourEdits.length} item{yourEdits.length === 1 ? "" : "s"} yourself.</li>}
          <li>Pages older than about 18 months were left out.</li>
          {report.assumptions_tagged && <li className="text-amber-800">Some gaps could not be filled; those parts are marked as assumptions.</li>}
          {report.sample_data && <li className="text-rose-700">This is built-in sample data — no live search keys were configured.</li>}
        </ul>
        {reviewerRemoved.length + yourEdits.length > 0 && (
          <details className="text-[11px] text-ink-faint">
            <summary className="cursor-pointer font-semibold text-ink-soft hover:text-ink">What was removed or corrected</summary>
            <ul className="mt-1.5 space-y-1 list-disc pl-4">
              {[...reviewerRemoved, ...yourEdits].map((d, i) => (
                <li key={i}>{d.replace(/^\[(VALIDATOR|MERCHANT_EDIT)\]\s*/, "")}</li>
              ))}
            </ul>
          </details>
        )}
        {!!report.dqs_diagnostics?.length && (
          <details className="text-[11px] text-ink-faint">
            <summary className="cursor-pointer font-semibold text-ink-soft hover:text-ink">What held the score back</summary>
            <ul className="mt-1.5 space-y-1 list-disc pl-4">
              {report.dqs_diagnostics.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
