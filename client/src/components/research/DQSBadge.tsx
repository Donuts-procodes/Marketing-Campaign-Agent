import { useState } from "react";
import { formatScore } from "@/lib/utils";
import { Award, ChevronDown, ChevronUp, AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface DQSBadgeProps {
  score: number;
  assumptionsTagged?: boolean;
  diagnostics?: string[];
  sourceUrlsCount?: number;
  threshold?: number;
}

export function DQSBadge({
  score,
  assumptionsTagged = false,
  diagnostics = [],
  sourceUrlsCount = 0,
  threshold = 0.8,
}: DQSBadgeProps) {
  const [isOpen, setIsOpen] = useState(false);
  const percentage = Math.round(score * 100);

  const isHigh = score >= threshold;
  const isMedium = score >= 0.5 && score < threshold;

  const colorConfig = isHigh
    ? {
        badgeBg: "bg-emerald-50 border-emerald-300 text-emerald-800",
        gaugeBg: "bg-emerald-600",
        label: "High Confidence (Gate Passed)",
      }
    : isMedium
    ? {
        badgeBg: "bg-amber-50 border-amber-300 text-amber-800",
        gaugeBg: "bg-amber-500",
        label: "Moderate Confidence (Assumptions Tagged)",
      }
    : {
        badgeBg: "bg-rose-50 border-rose-300 text-rose-800",
        gaugeBg: "bg-rose-500",
        label: "Low Data Density",
      };

  return (
    <div className="relative inline-block select-none">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs font-semibold transition cursor-pointer",
          colorConfig.badgeBg
        )}
      >
        <Award className="w-3.5 h-3.5" />
        <span className="font-mono">DQS: {formatScore(score)} ({percentage}%)</span>

        {assumptionsTagged && (
          <span className="px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 text-[10px] font-mono border border-amber-200">
            Assumptions
          </span>
        )}

        {isOpen ? (
          <ChevronUp className="w-3.5 h-3.5 opacity-70" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 opacity-70" />
        )}
      </button>

      {/* Dropdown Diagnostic Breakdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 rounded-lg bg-white border border-zinc-200 p-3.5 shadow-lg z-30 space-y-3 text-zinc-900">
          <div className="flex items-center justify-between border-b border-zinc-100 pb-2">
            <span className="text-xs font-bold text-zinc-900">
              Data Quality Score Diagnostics
            </span>
            <span className="text-[11px] font-mono text-zinc-500">
              Target: &ge; {threshold * 100}%
            </span>
          </div>

          {/* Progress Bar Gauge */}
          <div className="space-y-1">
            <div className="w-full bg-zinc-100 h-2 rounded-full overflow-hidden border border-zinc-200">
              <div
                className={cn("h-full transition-all duration-500", colorConfig.gaugeBg)}
                style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-zinc-500 font-mono">
              <span>0%</span>
              <span className="font-bold text-zinc-800">{colorConfig.label}</span>
              <span>100%</span>
            </div>
          </div>

          {/* Core Metric Checks */}
          <div className="space-y-1 text-xs">
            <div className="flex items-center justify-between py-1 border-b border-zinc-50">
              <span className="text-zinc-600">Verified Web Sources</span>
              <span className="font-mono font-semibold text-zinc-900">
                {sourceUrlsCount} domains
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-zinc-50">
              <span className="text-zinc-600">Assumptions Isolated</span>
              <span className="font-mono font-semibold text-zinc-900">
                {assumptionsTagged ? "Yes (flagged)" : "Strictly Source-Backed"}
              </span>
            </div>
          </div>

          {/* Diagnostics Messages / Gaps */}
          {diagnostics.length > 0 ? (
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                Verification Details:
              </span>
              <ul className="space-y-1 text-[11px]">
                {diagnostics.map((diag, idx) => (
                  <li key={idx} className="flex items-start gap-1.5 text-zinc-600">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                    <span>{diag}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="p-2 rounded bg-zinc-50 border border-zinc-200 text-[11px] text-zinc-500 flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0 text-zinc-400" />
              <span>Full audit passed across all competitor web targets.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
