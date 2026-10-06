import { useState } from "react";
import { CompetitorProfile } from "@/types/research";
import {
  Stethoscope,
  Activity,
  Video,
  FileText,
  ExternalLink,
  ShieldCheck,
  Megaphone,
} from "lucide-react";
import { cn, pricingLabel, safeHref } from "@/lib/utils";

interface CompetitorListAndDetailProps {
  competitors: CompetitorProfile[];
  onFindMore?: () => void;
  isFindingMore?: boolean;
}

export const CompetitorListAndDetail: React.FC<CompetitorListAndDetailProps> = ({
  competitors,
  onFindMore,
  isFindingMore = false,
}) => {
  const [selectedIndex, setSelectedIndex] = useState<number>(0);
  const activeComp = competitors[selectedIndex] || competitors[0];

  const avatarStyles = [
    { bg: "bg-[#F8B4D9]", text: "text-[#3D102A]", icon: Stethoscope },
    { bg: "bg-[#96BFE6]", text: "text-[#0F2D4A]", icon: Activity },
    { bg: "bg-[#D8B4E2]", text: "text-[#3B1245]", icon: Video },
    { bg: "bg-[#96C87C]", text: "text-[#19350E]", icon: FileText },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 select-none">
      {/* ── Left Box: Competitor's list ─────────────────────────── */}
      <div className="lg:col-span-5 bg-[#FFFDF9] rounded-[28px] p-5 border border-[#EDE7D8] shadow-xs flex flex-col justify-between space-y-4">
        <div>
          <div className="flex items-center justify-between pb-3 border-b border-[#EDE7D8]/80">
            <h3 className="text-base font-bold text-[#19191B]">Identified Competitors</h3>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#FAF7EE] text-[#5C4D18] border border-[#EDE7D8]">
              {competitors.length} Found
            </span>
          </div>

          <div className="space-y-2 mt-3">
            {competitors.length === 0 && (
              <div className="py-12 flex flex-col items-center justify-center text-center space-y-2">
                <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center text-amber-700 animate-pulse">
                  <Activity className="w-4 h-4" />
                </div>
                <p className="text-xs font-medium text-zinc-500 max-w-[200px]">
                  Autonomous search is scanning web & directories for rivals...
                </p>
              </div>
            )}
            {competitors.map((comp, idx) => {
              const isSelected = idx === selectedIndex;
              const style = avatarStyles[idx % avatarStyles.length];
              const Icon = style.icon;

              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setSelectedIndex(idx)}
                  className={cn(
                    "w-full flex items-center justify-between p-3 rounded-2xl transition-all text-left group cursor-pointer",
                    isSelected
                      ? "bg-[#FCE7F3] border border-[#F8B4D9] shadow-xs"
                      : "bg-[#FAF7EE]/60 hover:bg-[#FAF7EE] border border-transparent"
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={cn(
                        "w-9 h-9 rounded-full flex items-center justify-center shrink-0 shadow-xs",
                        style.bg,
                        style.text
                      )}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-[#19191B] truncate">
                        {comp.brand_name} {comp.product_name}
                      </h4>
                      <p className="text-[11px] text-zinc-500 truncate">
                        {comp.core_claims?.[0] || "Competitive Alternative"}
                      </p>
                    </div>
                  </div>

                  <div className="shrink-0 pl-2">
                    <span
                      className={cn(
                        "px-2.5 py-1 rounded-full text-[10px] font-mono font-bold tracking-tight",
                        isSelected
                          ? "bg-white text-[#3D102A] shadow-xs"
                          : "bg-white/80 text-zinc-600 border border-[#EDE7D8]"
                      )}
                    >
                      {pricingLabel(comp.pricing_model)}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {onFindMore && (
          <button
            type="button"
            onClick={onFindMore}
            disabled={isFindingMore}
            className="w-full py-2.5 rounded-full text-xs font-bold bg-[#19191B] hover:bg-black text-white transition text-center disabled:opacity-60 cursor-pointer"
          >
            {isFindingMore ? "Searching Web for More..." : "+ Find More Competitors from Web"}
          </button>
        )}
      </div>

      {/* ── Right Box: Competitor Details / Visit details ───────────── */}
      <div className="lg:col-span-7 bg-[#F9CADF] text-[#2C1322] rounded-[28px] p-6 shadow-xs flex flex-col justify-between space-y-4">
        {activeComp ? (
          <>
            <div>
              {/* Header Info */}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-bold tracking-tight text-[#2C1322]">
                    {activeComp.brand_name} {activeComp.product_name}
                  </h3>
                  <p className="text-xs text-[#5C2341] font-medium mt-0.5">
                    {pricingLabel(activeComp.pricing_model)} • {activeComp.sources?.length ?? 0} source(s)
                  </p>
                </div>
              </div>

              {/* Spec & Condition Pills */}
              <div className="flex flex-wrap gap-1.5 mt-3.5">
                {Object.entries(activeComp.dynamic_attributes ?? {})
                  .filter(([, v]) => Boolean(v))
                  .slice(0, 5)
                  .map(([k, v], i) => (
                    <span
                      key={i}
                      title={k.replace(/_/g, " ")}
                      className="px-3 py-1 rounded-full text-xs font-semibold bg-white/90 text-[#3D102A] shadow-xs"
                    >
                      {v}
                    </span>
                  ))}
              </div>

              {/* Observation & Diagnosis Rows */}
              <div className="space-y-3 mt-4 text-xs">
                <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4 border-b border-[#2C1322]/15 pb-2.5">
                  <span className="text-[11px] font-bold text-[#5C2341] uppercase tracking-wider w-24 shrink-0">
                    Pricing & Tier
                  </span>
                  <span className="font-semibold text-[#2C1322]">
                    {pricingLabel(activeComp.pricing_model)}
                  </span>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4 border-b border-[#2C1322]/15 pb-2.5">
                  <span className="text-[11px] font-bold text-[#5C2341] uppercase tracking-wider w-24 shrink-0">
                    Observation
                  </span>
                  <p className="text-[#2C1322] leading-relaxed">
                    {activeComp.weaknesses_mined?.[0]
                      ? `User pain points: "${activeComp.weaknesses_mined[0]}"`
                      : activeComp.core_claims?.[0] || "No claims or complaints captured."}
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4 border-b border-[#2C1322]/15 pb-2.5">
                  <span className="text-[11px] font-bold text-[#5C2341] uppercase tracking-wider w-24 shrink-0">
                    Factual Citation
                  </span>
                  <p className="text-[#2C1322] font-mono text-[11px] leading-relaxed italic">
                    {activeComp.factual_evidence?.[0] || "No verbatim evidence captured."}
                  </p>
                </div>

                {activeComp.ad_hooks && activeComp.ad_hooks.length > 0 && (
                  <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4 pt-0.5">
                    <span className="text-[11px] font-bold text-[#5C2341] uppercase tracking-wider w-24 shrink-0 flex items-center gap-1">
                      <Megaphone className="w-3 h-3" />
                      Ad Angle
                    </span>
                    <span className="font-medium text-[#2C1322]">
                      "{activeComp.ad_hooks[0]}"
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Source Link */}
            {safeHref(activeComp.sources?.[0]) && (
              <div className="pt-2 flex items-center justify-between text-xs">
                <span className="text-[11px] font-medium text-[#5C2341] flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
                  Sources checked against crawl results
                </span>
                <a
                  href={safeHref(activeComp.sources[0])}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-bold text-[#2C1322] hover:underline"
                >
                  <span>Open Raw Web Dossier</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            )}
          </>
        ) : (
          <div className="py-24 flex flex-col items-center justify-center text-center space-y-2.5">
            <div className="w-10 h-10 rounded-full bg-white/40 flex items-center justify-center text-[#5C2341]">
              <FileText className="w-5 h-5 opacity-70" />
            </div>
            <p className="text-xs font-semibold text-[#5C2341] max-w-xs leading-relaxed">
              {competitors.length === 0
                ? "Competitor dossier and verified claims will populate here once discovered."
                : "Select a competitor from the list to inspect their full dossier."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
