import { DashboardInsights } from "@/types/research";
import {
  Sparkles,
  Target,
  Compass,
  ArrowRight,
  Zap,
} from "lucide-react";

interface DashboardInsightsPanelProps {
  insights: DashboardInsights;
}

export const DashboardInsightsPanel = ({
  insights,
}: DashboardInsightsPanelProps) => {
  return (
    <section className="space-y-3 pt-1">
      {/* Executive Summary Banner */}
      {insights.executive_summary && (
        <div className="p-4 rounded-lg bg-zinc-900 text-white shadow-sm">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400 mb-2">
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI-Curated Intelligence Brief</span>
          </div>
          <p className="text-sm text-zinc-200 leading-relaxed font-medium">
            {insights.executive_summary}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Highlighted Weaknesses */}
        {insights.highlight_weaknesses.length > 0 && (
          <div className="p-3.5 rounded-lg bg-white border border-zinc-200 shadow-2xs space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-rose-700 uppercase tracking-wider">
              <Target className="w-3.5 h-3.5 text-rose-500" />
              Exploitable Weaknesses
            </div>
            <ul className="space-y-1.5">
              {insights.highlight_weaknesses.map((w, i) => (
                <li
                  key={i}
                  className="text-xs text-zinc-700 leading-relaxed flex items-start gap-1.5"
                >
                  <ArrowRight className="w-3 h-3 text-rose-400 mt-0.5 shrink-0" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Highlight Opportunities */}
        {insights.highlight_opportunities.length > 0 && (
          <div className="p-3.5 rounded-lg bg-white border border-zinc-200 shadow-2xs space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 uppercase tracking-wider">
              <Compass className="w-3.5 h-3.5 text-emerald-500" />
              Market Opportunities
            </div>
            <ul className="space-y-1.5">
              {insights.highlight_opportunities.map((o, i) => (
                <li
                  key={i}
                  className="text-xs text-zinc-700 leading-relaxed flex items-start gap-1.5"
                >
                  <ArrowRight className="w-3 h-3 text-emerald-400 mt-0.5 shrink-0" />
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommended Actions */}
        {insights.recommended_actions.length > 0 && (
          <div className="p-3.5 rounded-lg bg-white border border-zinc-200 shadow-2xs space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-amber-700 uppercase tracking-wider">
              <Zap className="w-3.5 h-3.5 text-amber-500" />
              Recommended Actions
            </div>
            <ol className="space-y-1.5">
              {insights.recommended_actions.map((a, i) => (
                <li
                  key={i}
                  className="text-xs text-zinc-700 leading-relaxed flex items-start gap-2"
                >
                  <span className="w-4 h-4 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <span>{a}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {/* Priority Differentiators */}
      {insights.priority_attributes.length > 0 && (
        <div className="flex items-center flex-wrap gap-1.5 text-xs">
          <span className="font-bold text-zinc-500 uppercase tracking-wider text-[10px]">
            Priority Differentiators:
          </span>
          {insights.priority_attributes.map((attr, i) => (
            <span
              key={i}
              className="px-2 py-0.5 rounded bg-zinc-900 text-zinc-100 text-[11px] font-medium"
            >
              {attr.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </section>
  );
};
