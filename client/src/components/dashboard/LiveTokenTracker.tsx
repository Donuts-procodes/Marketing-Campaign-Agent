import type { FC } from "react";
import { Zap, TrendingUp, TrendingDown, Cpu } from "lucide-react";
import { useLiveTokenTracker } from "@/lib/tiktokenTracker";
import { cn } from "@/lib/utils";

interface LiveTokenTrackerProps {
  className?: string;
  onClick?: () => void;
}

export const LiveTokenTracker: FC<LiveTokenTrackerProps> = ({ className, onClick }) => {
  const { totalTokens, delta, direction, model, isByok, estimatedCostUsd } = useLiveTokenTracker();

  return (
    <div
      onClick={onClick}
      title={`Live TikToken Monitor: ${totalTokens.toLocaleString()} tokens processed | Est. cost: $${estimatedCostUsd} | Model: ${model}`}
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-all select-none border cursor-pointer shadow-xs",
        isByok
          ? "bg-[#FDF1EB] border-[#F3CFC0] text-[#8F2F14] hover:bg-[#FBE8DE]"
          : "bg-white border-[#E1D7C8] text-[#1F1A17] hover:bg-[#FDF9F3]",
        direction === "up" && "border-emerald-500/60 shadow-[0_0_12px_rgba(16,185,129,0.25)]",
        className
      )}
    >
      <div className="flex items-center gap-1.5">
        {isByok ? (
          <Zap className="w-3.5 h-3.5 text-[#C7431F]" />
        ) : (
          <Cpu className="w-3.5 h-3.5 text-[#8A8176]" />
        )}
        <span className="font-bold tabular-nums text-[#1F1A17] font-mono">
          {totalTokens > 0 ? totalTokens.toLocaleString() : "0"}
        </span>
        <span className="text-[10px] text-[#8A8176]">tokens</span>
      </div>

      {/* Up / Down Live Delta Badge */}
      {direction === "up" && (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#E4F2EA] text-[#256545] animate-in fade-in zoom-in-75 duration-150">
          <TrendingUp className="w-2.5 h-2.5" />
          +{delta > 0 ? delta.toLocaleString() : ""}
        </span>
      )}
      {direction === "down" && (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-[#FDE6E4] text-[#A63030] animate-in fade-in zoom-in-75 duration-150">
          <TrendingDown className="w-2.5 h-2.5" />
          -{delta > 0 ? delta.toLocaleString() : ""}
        </span>
      )}

      {/* BYOK Tag */}
      {isByok && (
        <span className="hidden sm:inline-block px-1.5 py-0.5 rounded-md bg-[#C7431F]/15 text-[#C7431F] text-[9px] font-mono uppercase tracking-wider font-bold">
          BYOK
        </span>
      )}
    </div>
  );
};
