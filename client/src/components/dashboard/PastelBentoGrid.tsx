import { SWOTReportDelta } from "@/types/research";
import { Users, ShieldCheck, Layers, Compass } from "lucide-react";

interface PastelBentoGridProps {
  swotReport?: SWOTReportDelta | null;
  competitorCount?: number;
}

export const PastelBentoGrid: React.FC<PastelBentoGridProps> = ({
  swotReport,
  competitorCount = 0,
}) => {
  const dqsPercent = swotReport ? Math.round(swotReport.dqs_score * 100) : 0;
  const sourceCount = swotReport?.source_urls?.length || 0;
  const criticalDrivers = swotReport?.dynamic_taxonomy?.critical_jtbd_drivers || [];
  const minorAttrs = swotReport?.dynamic_taxonomy?.minor_attributes || [];
  const densityPercent =
    swotReport?.attribute_density !== undefined
      ? Math.round(swotReport.attribute_density * 100)
      : 0;

  const gapQuadrant = swotReport?.positioning_gap?.quadrant || swotReport?.market_positioning_gap?.quadrant;
  const gapHook = swotReport?.positioning_gap?.hook_angle || swotReport?.market_positioning_gap?.hook_angle;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
      {/* 1. Competitors & Sources */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4 flex flex-col justify-between shadow-xs">
        <div>
          <div className="flex items-center justify-between text-zinc-500 text-xs font-semibold uppercase tracking-wider">
            <span>Competitor Intel</span>
            <Users className="w-4 h-4 text-zinc-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-zinc-900">
              {competitorCount}
            </span>
            <span className="text-xs text-zinc-500 font-medium">rival profiles</span>
          </div>
          <p className="mt-2 text-xs text-zinc-600">
            Grounding extracted across <span className="font-semibold text-zinc-900">{sourceCount}</span> verified source domains.
          </p>
        </div>
        <div className="mt-3 pt-2.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Search Status</span>
          <span className="inline-flex items-center gap-1.5 font-medium text-emerald-700">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {competitorCount > 0 ? "Indexed & Grounded" : "Discovering..."}
          </span>
        </div>
      </div>

      {/* 2. DQS Quality Metric */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4 flex flex-col justify-between shadow-xs">
        <div>
          <div className="flex items-center justify-between text-zinc-500 text-xs font-semibold uppercase tracking-wider">
            <span>Data Quality (DQS)</span>
            <ShieldCheck className="w-4 h-4 text-zinc-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-zinc-900">
              {dqsPercent}%
            </span>
            <span className="text-xs text-zinc-500 font-medium">confidence</span>
          </div>
          <p className="mt-2 text-xs text-zinc-600">
            {swotReport?.assumptions_tagged
              ? "Hypotheses flagged with explicit assumptions."
              : "Strict claim verification against scraped pages."}
          </p>
        </div>
        <div className="mt-3 pt-2.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Reliability Gate</span>
          <span className={`inline-flex items-center gap-1.5 font-medium ${dqsPercent >= 80 ? "text-emerald-700" : "text-amber-700"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${dqsPercent >= 80 ? "bg-emerald-500" : "bg-amber-500"}`} />
            {dqsPercent >= 80 ? "Pass (>=80%)" : "Gating Notice"}
          </span>
        </div>
      </div>

      {/* 3. Learned Parameter Matrix */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4 flex flex-col justify-between shadow-xs">
        <div>
          <div className="flex items-center justify-between text-zinc-500 text-xs font-semibold uppercase tracking-wider">
            <span>Market Attributes</span>
            <Layers className="w-4 h-4 text-zinc-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-zinc-900">
              {densityPercent}%
            </span>
            <span className="text-xs text-zinc-500 font-medium">spec density</span>
          </div>
          <p className="mt-2 text-xs text-zinc-600">
            <span className="font-semibold text-zinc-900">{criticalDrivers.length}</span> critical dealbreakers &amp;{" "}
            <span className="font-semibold text-zinc-900">{minorAttrs.length}</span> minor spec parameters.
          </p>
        </div>
        <div className="mt-3 pt-2.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Taxonomy Engine</span>
          <span className="inline-flex items-center gap-1.5 font-medium text-blue-700">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            Dynamic JTBD
          </span>
        </div>
      </div>

      {/* 4. Strategic Positioning Gap */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4 flex flex-col justify-between shadow-xs">
        <div>
          <div className="flex items-center justify-between text-zinc-500 text-xs font-semibold uppercase tracking-wider">
            <span>Positioning Gap</span>
            <Compass className="w-4 h-4 text-zinc-400" />
          </div>
          <div className="mt-3">
            <span className="text-sm font-semibold font-mono text-zinc-900 truncate block">
              {gapQuadrant || "Blue Ocean Angle"}
            </span>
          </div>
          <p className="mt-2 text-xs text-zinc-600 line-clamp-2 italic">
            {gapHook ? `"${gapHook}"` : "Synthesizing market white-space angle from competitor crawl..."}
          </p>
        </div>
        <div className="mt-3 pt-2.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
          <span>Strategy Angle</span>
          <span className="font-medium text-zinc-700">Actionable White-Space</span>
        </div>
      </div>
    </div>
  );
};
