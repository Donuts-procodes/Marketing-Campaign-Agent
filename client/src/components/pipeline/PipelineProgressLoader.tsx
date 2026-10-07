import { useEffect, useMemo, useState } from "react";
import { TelemetryLogItem } from "@/types/campaign";
import {
  Compass,
  Search,
  FileText,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Activity,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface PipelineProgressLoaderProps {
  logs: TelemetryLogItem[];
  connectionStatus: string;
  error?: string | null;
  onViewLogs?: () => void;
  onRetry?: () => void;
}

interface StepInfo {
  id: string;
  label: string;
  icon: typeof Compass;
  matchPatterns: string[];
}

const STEPS: StepInfo[] = [
  {
    id: "taxonomy",
    label: "Analyzing Goals & Taxonomy Parameters",
    icon: Compass,
    matchPatterns: ["DYNAMIC_PARAMS", "INTENT_UNDERSTOOD", "CAMPAIGN_CLASSIFIED", "CONFIG"],
  },
  {
    id: "search",
    label: "Autonomous Multi-Vector Discovery & Crawling",
    icon: Search,
    matchPatterns: ["TAVILY_SEARCH", "DEEP_SEARCH", "AD_INTELLIGENCE"],
  },
  {
    id: "grounding",
    label: "Evidence Validation & Factual Grounding",
    icon: ShieldCheck,
    matchPatterns: ["DATA_VALIDATION", "DQS_EVAL"],
  },
  {
    id: "synthesis",
    label: "Synthesizing Strategic Intelligence & SWOT",
    icon: FileText,
    matchPatterns: ["LLM_SYNTH", "NODE_COMPLETE"],
  },
];

export function PipelineProgressLoader({
  logs,
  connectionStatus,
  error,
  onViewLogs,
  onRetry,
}: PipelineProgressLoaderProps) {
  const latestLog = logs[logs.length - 1];

  // Derive active steps and smooth progress from telemetry logs
  const { currentStepIndex, percent } = useMemo(() => {
    if (connectionStatus === "COMPLETED") return { currentStepIndex: 4, percent: 100 };
    if (logs.length === 0) return { currentStepIndex: 0, percent: 8 };

    let highestStep = 0;
    let weight = 10;

    for (const log of logs) {
      const msg = log.message || "";
      if (msg.includes("[LLM_SYNTH]") || msg.includes("Synthesizing")) {
        highestStep = Math.max(highestStep, 3);
        weight = Math.max(weight, 85);
      } else if (msg.includes("[DQS_EVAL]") || msg.includes("[DATA_VALIDATION]")) {
        highestStep = Math.max(highestStep, 2);
        weight = Math.max(weight, 65);
      } else if (msg.includes("[TAVILY_SEARCH]") || msg.includes("[DEEP_SEARCH]") || msg.includes("[AD_INTELLIGENCE]")) {
        highestStep = Math.max(highestStep, 1);
        weight = Math.max(weight, 35);
      } else if (msg.includes("[DYNAMIC_PARAMS]") || msg.includes("[INTENT_UNDERSTOOD]")) {
        highestStep = Math.max(highestStep, 0);
        weight = Math.max(weight, 18);
      }
    }

    // Smooth based on total log count
    const logBonus = Math.min(logs.length * 1.5, 12);
    const calculated = Math.min(Math.round(weight + logBonus), 95);

    return {
      currentStepIndex: highestStep,
      percent: calculated,
    };
  }, [logs, connectionStatus]);

  // Animated visual display of percentage
  const [displayPercent, setDisplayPercent] = useState(8);
  useEffect(() => {
    const timer = setTimeout(() => {
      setDisplayPercent((prev) => {
        if (prev < percent) return Math.min(prev + 2, percent);
        return percent;
      });
    }, 40);
    return () => clearTimeout(timer);
  }, [percent, displayPercent]);

  return (
    <div className="w-full max-w-3xl mx-auto my-12 p-8 sm:p-10 rounded-[32px] bg-[#FFFDF9] border border-[#EDE7D8] shadow-sm flex flex-col items-center text-center space-y-8 animate-in fade-in zoom-in-95 duration-300">
      {/* Header Badge */}
      <div className="flex flex-col items-center space-y-3">
        <div className="relative flex items-center justify-center">
          <div className="w-16 h-16 rounded-2xl bg-[#F4E8D3] flex items-center justify-center text-[#19191B]">
            <Activity className="w-8 h-8 animate-pulse text-[#19191B]" />
          </div>
          <span className="absolute -top-1 -right-1 flex h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E5833A] opacity-75"></span>
            <span className="relative inline-flex rounded-full h-4 w-4 bg-[#E5833A]"></span>
          </span>
        </div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-[#19191B]">
          Gathering Competitive Intelligence
        </h2>
        <p className="text-xs sm:text-sm text-zinc-500 max-w-md">
          Autonomous agents are conducting multi-vector web queries, deep page extraction, dynamic attribute mining, and factual grounding.
        </p>
      </div>

      {/* Radial / Linear Progress Bar */}
      <div className="w-full space-y-3">
        <div className="flex items-center justify-between text-xs font-bold text-zinc-700 px-1">
          <span className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            {connectionStatus === "RECONNECTING" ? "Reconnecting stream..." : "Autonomous Run in Progress"}
          </span>
          <span className="font-mono text-sm text-[#19191B]">{displayPercent}%</span>
        </div>

        <div className="w-full h-3.5 bg-[#F1ECE1] rounded-full overflow-hidden p-0.5 border border-[#EDE7D8]">
          <div
            className="h-full bg-linear-to-r from-[#F8B4D9] via-[#96BFE6] to-[#96C87C] rounded-full transition-all duration-500 ease-out shadow-xs"
            style={{ width: `${displayPercent}%` }}
          />
        </div>
      </div>

      {/* 4 Step Milestones */}
      <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
        {STEPS.map((step, idx) => {
          const isDone = currentStepIndex > idx || connectionStatus === "COMPLETED";
          const isCurrent = currentStepIndex === idx && connectionStatus !== "COMPLETED";
          const StepIcon = step.icon;

          return (
            <div
              key={step.id}
              className={cn(
                "flex items-center gap-3.5 p-3.5 rounded-2xl border transition-all duration-300",
                isDone
                  ? "bg-[#FAF7EE] border-[#96C87C]/60 text-zinc-800"
                  : isCurrent
                    ? "bg-white border-[#19191B] shadow-sm text-zinc-900"
                    : "bg-[#FFFDF9]/60 border-[#EDE7D8] text-zinc-400 opacity-60"
              )}
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-xs font-bold",
                  isDone
                    ? "bg-[#96C87C]/30 text-emerald-800"
                    : isCurrent
                      ? "bg-[#19191B] text-white"
                      : "bg-[#F1ECE1] text-zinc-400"
                )}
              >
                {isDone ? <CheckCircle2 className="w-4 h-4" /> : <StepIcon className="w-4 h-4" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold truncate">{step.label}</p>
                <p className="text-[10px] text-zinc-500">
                  {isDone ? "Completed" : isCurrent ? "Processing in real-time..." : "Pending"}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Live Terminal Log Preview */}
      {latestLog && (
        <div className="w-full bg-[#1A1817] rounded-2xl p-4 text-left font-mono border border-zinc-800 shadow-inner flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1 flex items-center gap-2">
            <span className="text-[10px] uppercase font-bold text-amber-400 px-1.5 py-0.5 rounded bg-amber-400/10 shrink-0">
              Live Trace
            </span>
            <p className="text-xs text-zinc-300 truncate">{latestLog.message}</p>
          </div>
          {onViewLogs && (
            <button
              type="button"
              onClick={onViewLogs}
              className="text-xs text-sky-400 hover:text-sky-300 whitespace-nowrap font-medium flex items-center gap-1 cursor-pointer transition shrink-0"
            >
              Full log <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}

      {/* Error state if occurred */}
      {error && (
        <div className="w-full p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 flex items-center justify-between text-xs font-medium">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="px-3 py-1.5 rounded-lg bg-rose-600 text-white font-bold hover:bg-rose-700 transition flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
