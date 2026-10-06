import { useState } from "react";
import { CompetitorProfile, DynamicParameterTaxonomy, MarketPositioningGap } from "@/types/research";
import {
  Target,
  Sparkles,
  ArrowRight,
  Copy,
  Check,
} from "lucide-react";

interface ActionablePlaybookProps {
  competitors: CompetitorProfile[];
  positioningGap?: MarketPositioningGap | null;
  dynamicTaxonomy?: DynamicParameterTaxonomy;
}

interface CounterStrategyItem {
  id: string;
  competitorBrand: string;
  weaknessTargeted: string;
  recommendedAngle: string;
  suggestedAdHeadline: string;
  suggestedAdBody: string;
  callToAction: string;
}

export const ActionablePlaybook = ({
  competitors,
  positioningGap,
}: ActionablePlaybookProps) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Synthesize concrete counter-attack campaigns from competitor weaknesses
  const counterStrategies: CounterStrategyItem[] = competitors.flatMap((comp, compIdx) => {
    const weaknesses = comp.weaknesses_mined || [];
    return weaknesses.slice(0, 2).map((weakness, wIdx) => {
      const id = `strategy-${compIdx}-${wIdx}`;
      return {
        id,
        competitorBrand: comp.brand_name,
        weaknessTargeted: weakness,
        recommendedAngle: `Overcoming ${comp.brand_name}'s friction: Lead with guaranteed reliability, transparent terms, and direct self-serve access.`,
        suggestedAdHeadline: `Tired of ${weakness.slice(0, 48).toLowerCase()}? Switch to a simpler alternative.`,
        suggestedAdBody: `While ${comp.brand_name} struggles with ${weakness.toLowerCase()}, our solution is purpose-built to deliver without the headaches. Transparent pricing, zero lock-in, and instant onboarding.`,
        callToAction: "Compare Features & Start Free",
      };
    });
  });

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (counterStrategies.length === 0 && !positioningGap) {
    return null;
  }

  return (
    <section className="space-y-4 pt-2">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-zinc-200">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-amber-500/10 flex items-center justify-center text-amber-600">
            <Target className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-900">
              Merchant Action Plan &amp; Counter-Campaign Playbook
            </h3>
            <p className="text-[11px] text-zinc-500">
              Turn competitor complaints and positioning voids into ready-to-run marketing hooks.
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 shrink-0">
          {counterStrategies.length} Actionable Angles Generated
        </span>
      </div>

      {/* Positioning Gap Banner if present */}
      {positioningGap && positioningGap.hook_angle && (
        <div className="p-4 rounded-lg bg-zinc-900 text-white shadow-xs space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Primary Core Value Proposition (White-Space Win)</span>
            </div>
            {positioningGap.quadrant && (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-zinc-800 text-emerald-300 border border-zinc-700">
                {positioningGap.quadrant}
              </span>
            )}
          </div>
          <p className="text-xs sm:text-sm text-zinc-200 font-medium leading-relaxed">
            "{positioningGap.hook_angle}"
          </p>
        </div>
      )}

      {/* Grid of Actionable Angle Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {counterStrategies.map((strat) => {
          const isCopied = copiedId === strat.id;
          const copyContent = `Headline: ${strat.suggestedAdHeadline}\nBody: ${strat.suggestedAdBody}\nCTA: ${strat.callToAction}`;

          return (
            <div
              key={strat.id}
              className="p-4 rounded-lg bg-white border border-zinc-200 shadow-2xs hover:shadow-xs transition flex flex-col justify-between space-y-3"
            >
              <div className="space-y-2">
                {/* Header row: target rival & gripe badge */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs font-bold text-zinc-900">
                      vs. {strat.competitorBrand}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-rose-50 text-rose-700 border border-rose-200">
                      Exploits Competitor Weakness
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopy(strat.id, copyContent)}
                    className="p-1 rounded text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition cursor-pointer"
                    title="Copy ad copy to clipboard"
                  >
                    {isCopied ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                {/* Gripe quote */}
                <div className="p-2.5 rounded bg-zinc-50 border border-zinc-200 text-xs text-zinc-700">
                  <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-0.5">
                    Customer Gripe Mined
                  </span>
                  <span className="italic">"{strat.weaknessTargeted}"</span>
                </div>

                {/* Campaign Copy Proposal */}
                <div className="space-y-1.5 text-xs">
                  <div>
                    <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                      Recommended Ad Headline
                    </span>
                    <p className="font-semibold text-zinc-900 mt-0.5">
                      {strat.suggestedAdHeadline}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                      Ad Body Hook
                    </span>
                    <p className="text-zinc-600 text-[11px] leading-relaxed mt-0.5">
                      {strat.suggestedAdBody}
                    </p>
                  </div>
                </div>
              </div>

              {/* Action Button & CTA footer */}
              <div className="pt-2 border-t border-zinc-100 flex items-center justify-between text-xs">
                <span className="text-[11px] text-zinc-500">CTA: <strong>{strat.callToAction}</strong></span>
                <button
                  type="button"
                  onClick={() => handleCopy(strat.id, copyContent)}
                  className="text-xs font-semibold text-zinc-900 hover:underline flex items-center gap-1 cursor-pointer"
                >
                  {isCopied ? "Copied!" : "Copy Ad Copy"}
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
