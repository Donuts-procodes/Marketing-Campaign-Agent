import type { MarketOverview } from "@/types/research";
import { PointList, SourceTag } from "./Sourced";

const SIGNAL: Record<string, { icon: string; cls: string }> = {
  rising: { icon: "↑", cls: "text-[#3F9068]" },
  falling: { icon: "↓", cls: "text-[#C7431F]" },
  new: { icon: "✦", cls: "text-[#B07A12]" },
  steady: { icon: "→", cls: "text-[#8A8176]" },
};

/** Market summary, findings, openings and trends; every line links to its source. */
export function MarketOverviewPanel({ market }: { market?: MarketOverview | null }) {
  if (!market) return null;
  const empty =
    !market.summary && !market.key_findings.length && !market.positioning_opportunities.length && !market.trends.length;
  if (empty) return null;
  return (
    <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-5">
      <div className="space-y-2">
        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Market overview</h3>
        {market.summary && <p className="text-sm text-[#4A4239] leading-relaxed">{market.summary}</p>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <PointList title="Key market findings" points={market.key_findings} />
        <PointList title="Positioning opportunities" points={market.positioning_opportunities} marker="◎" />
      </div>
      {market.trends.length > 0 && (
        <div className="space-y-2">
          <div className="text-[11px] font-bold uppercase tracking-wide text-[#8A8176]">Market trends</div>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {market.trends.map((t, i) => {
              const s = SIGNAL[t.signal] ?? SIGNAL.steady;
              return (
                <li key={i} className="flex gap-2 p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] text-xs text-[#4A4239]">
                  <span aria-label={t.signal} className={`font-bold ${s.cls}`}>{s.icon}</span>
                  <span className="min-w-0 leading-relaxed">
                    {t.text} <SourceTag point={t} />
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
