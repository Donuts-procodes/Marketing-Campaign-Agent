import { useState } from "react";
import { MarketPositioningGap, SWOTAnalysis } from "@/types/research";
import {
  TrendingUp,
  AlertTriangle,
  Target,
  ShieldAlert,
  Compass,
  Copy,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SWOTGridProps {
  swot?: SWOTAnalysis;
  positioningGap?: MarketPositioningGap | null;
}

export function SWOTGrid({ swot, positioningGap }: SWOTGridProps) {
  const [copiedHook, setCopiedHook] = useState(false);

  const handleCopyHook = () => {
    if (!positioningGap?.hook_angle) return;
    navigator.clipboard.writeText(positioningGap.hook_angle);
    setCopiedHook(true);
    setTimeout(() => setCopiedHook(false), 2000);
  };

  const hasAnyItems = Boolean(
    (swot?.strengths && swot.strengths.length > 0) ||
    (swot?.weaknesses && swot.weaknesses.length > 0) ||
    (swot?.opportunities && swot.opportunities.length > 0) ||
    (swot?.threats && swot.threats.length > 0)
  );

  return (
    <div className="space-y-4">
      {/* Strategic Positioning Gap Card */}
      {positioningGap && positioningGap.hook_angle && (
        <div className="rounded-2xl p-5 bg-[#1F1A17] text-white border border-[#38312B] shadow-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Compass className="w-4 h-4 text-[#E27D60]" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#A89F91]">
                Uncontested Market Positioning Gap
              </span>
              {positioningGap.quadrant && (
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#2C2521] text-[#E27D60] border border-[#4A3F38]">
                  Quadrant: {positioningGap.quadrant}
                </span>
              )}
            </div>
            <p className="text-sm font-medium text-zinc-100 italic border-l-2 border-[#C7431F] pl-3 leading-relaxed">
              "{positioningGap.hook_angle}"
            </p>
          </div>

          <button
            type="button"
            onClick={handleCopyHook}
            className={cn(
              "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer shrink-0",
              copiedHook
                ? "bg-[#256545] text-white"
                : "bg-[#2D2723] hover:bg-[#3D352F] text-zinc-100 border border-[#4A3F38]"
            )}
          >
            {copiedHook ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Copied Hook
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                Copy Hook
              </>
            )}
          </button>
        </div>
      )}

      {/* 2x2 Structured SWOT Matrix */}
      {swot && hasAnyItems ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Strengths */}
          <div className="rounded-2xl p-5 bg-white border border-[#E1D7C8] shadow-xs space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-[#EFE7DB] text-[#1F1A17] font-bold text-xs uppercase tracking-wider">
              <TrendingUp className="w-4 h-4 text-[#256545]" />
              <span className="font-['Bricolage_Grotesque'] text-sm tracking-normal">Strengths</span>
              <span className="ml-auto px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#E4F2EA] text-[#256545] border border-[#256545]/20">
                {swot.strengths?.length || 0}
              </span>
            </div>
            <ul className="space-y-2 pt-1">
              {(swot.strengths && swot.strengths.length > 0
                ? swot.strengths
                : ["No explicit strengths recorded."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-[#3D352F] flex items-start gap-2.5 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#256545] mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Weaknesses */}
          <div className="rounded-2xl p-5 bg-white border border-[#E1D7C8] shadow-xs space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-[#EFE7DB] text-[#1F1A17] font-bold text-xs uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4 text-[#C7431F]" />
              <span className="font-['Bricolage_Grotesque'] text-sm tracking-normal">Weaknesses</span>
              <span className="ml-auto px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#FDF1EB] text-[#C7431F] border border-[#C7431F]/20">
                {swot.weaknesses?.length || 0}
              </span>
            </div>
            <ul className="space-y-2 pt-1">
              {(swot.weaknesses && swot.weaknesses.length > 0
                ? swot.weaknesses
                : ["No explicit weaknesses recorded."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-[#3D352F] flex items-start gap-2.5 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#C7431F] mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Opportunities */}
          <div className="rounded-2xl p-5 bg-white border border-[#E1D7C8] shadow-xs space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-[#EFE7DB] text-[#1F1A17] font-bold text-xs uppercase tracking-wider">
              <Target className="w-4 h-4 text-[#2B59C3]" />
              <span className="font-['Bricolage_Grotesque'] text-sm tracking-normal">Opportunities</span>
              <span className="ml-auto px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#EBF1FD] text-[#2B59C3] border border-[#2B59C3]/20">
                {swot.opportunities?.length || 0}
              </span>
            </div>
            <ul className="space-y-2 pt-1">
              {(swot.opportunities && swot.opportunities.length > 0
                ? swot.opportunities
                : ["No explicit opportunities recorded."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-[#3D352F] flex items-start gap-2.5 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#2B59C3] mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Threats */}
          <div className="rounded-2xl p-5 bg-white border border-[#E1D7C8] shadow-xs space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-[#EFE7DB] text-[#1F1A17] font-bold text-xs uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4 text-[#8A3B14]" />
              <span className="font-['Bricolage_Grotesque'] text-sm tracking-normal">Threats</span>
              <span className="ml-auto px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#FBF0EA] text-[#8A3B14] border border-[#8A3B14]/20">
                {swot.threats?.length || 0}
              </span>
            </div>
            <ul className="space-y-2 pt-1">
              {(swot.threats && swot.threats.length > 0
                ? swot.threats
                : ["No explicit threats recorded."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-[#3D352F] flex items-start gap-2.5 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#8A3B14] mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="p-8 text-center text-xs text-[#8A8176] border border-[#E1D7C8] rounded-2xl bg-white shadow-xs">
          Awaiting agent synthesis to generate complete 4-quadrant SWOT matrix...
        </div>
      )}
    </div>
  );
}
