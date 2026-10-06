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

  return (
    <div className="space-y-4">
      {/* Strategic Positioning Gap Card */}
      {positioningGap && (
        <div className="rounded-lg p-4 bg-zinc-900 text-white border border-zinc-800 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
          <div className="space-y-1 max-w-3xl">
            <div className="flex items-center gap-2">
              <Compass className="w-4 h-4 text-emerald-400" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                Market Positioning Gap Analysis
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-zinc-800 text-emerald-300 border border-zinc-700">
                Quadrant: {positioningGap.quadrant}
              </span>
            </div>
            <p className="text-sm font-medium text-zinc-100 italic border-l-2 border-emerald-500 pl-3 leading-relaxed">
              "{positioningGap.hook_angle}"
            </p>
          </div>

          <button
            type="button"
            onClick={handleCopyHook}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold transition cursor-pointer shrink-0",
              copiedHook
                ? "bg-emerald-600 text-white"
                : "bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
            )}
          >
            {copiedHook ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Copied
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
      {swot ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Strengths */}
          <div className="rounded-lg p-4 bg-white border border-zinc-200 shadow-xs space-y-2">
            <div className="flex items-center gap-2 pb-2 border-b border-zinc-100 text-zinc-900 font-bold text-xs uppercase tracking-wider">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
              <span>Strengths</span>
              <span className="ml-auto text-[10px] font-mono text-zinc-400">
                ({swot.strengths?.length || 0})
              </span>
            </div>
            <ul className="space-y-1.5 pt-1">
              {(swot.strengths?.length > 0
                ? swot.strengths
                : ["No explicit strengths identified."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-zinc-800 flex items-start gap-2 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Weaknesses */}
          <div className="rounded-lg p-4 bg-white border border-zinc-200 shadow-xs space-y-2">
            <div className="flex items-center gap-2 pb-2 border-b border-zinc-100 text-zinc-900 font-bold text-xs uppercase tracking-wider">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>Weaknesses</span>
              <span className="ml-auto text-[10px] font-mono text-zinc-400">
                ({swot.weaknesses?.length || 0})
              </span>
            </div>
            <ul className="space-y-1.5 pt-1">
              {(swot.weaknesses?.length > 0
                ? swot.weaknesses
                : ["No explicit weaknesses identified."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-zinc-800 flex items-start gap-2 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Opportunities */}
          <div className="rounded-lg p-4 bg-white border border-zinc-200 shadow-xs space-y-2">
            <div className="flex items-center gap-2 pb-2 border-b border-zinc-100 text-zinc-900 font-bold text-xs uppercase tracking-wider">
              <Target className="w-3.5 h-3.5 text-blue-600" />
              <span>Opportunities</span>
              <span className="ml-auto text-[10px] font-mono text-zinc-400">
                ({swot.opportunities?.length || 0})
              </span>
            </div>
            <ul className="space-y-1.5 pt-1">
              {(swot.opportunities?.length > 0
                ? swot.opportunities
                : ["No explicit opportunities identified."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-zinc-800 flex items-start gap-2 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Threats */}
          <div className="rounded-lg p-4 bg-white border border-zinc-200 shadow-xs space-y-2">
            <div className="flex items-center gap-2 pb-2 border-b border-zinc-100 text-zinc-900 font-bold text-xs uppercase tracking-wider">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
              <span>Threats</span>
              <span className="ml-auto text-[10px] font-mono text-zinc-400">
                ({swot.threats?.length || 0})
              </span>
            </div>
            <ul className="space-y-1.5 pt-1">
              {(swot.threats?.length > 0
                ? swot.threats
                : ["No explicit threats identified."]
              ).map((item, idx) => (
                <li
                  key={idx}
                  className="text-xs text-zinc-800 flex items-start gap-2 leading-relaxed"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="p-8 text-center text-xs text-zinc-400 border border-zinc-200 rounded-lg bg-white">
          Awaiting agent synthesis to generate complete 4-quadrant SWOT matrix...
        </div>
      )}
    </div>
  );
}
