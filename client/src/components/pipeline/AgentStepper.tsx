import { AgentPhase, PhaseStatus } from "@/types/campaign";
import {
  Search,
  Users,
  Target,
  Sparkles,
  Send,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AgentStepperProps {
  activePhase: AgentPhase | null;
  completedPhases: AgentPhase[];
  isInterrupted?: boolean;
}

interface StepConfig {
  phase: AgentPhase;
  title: string;
  subtitle: string;
  icon: typeof Search;
  isPluggableSlot?: boolean;
}

const PIPELINE_STEPS: StepConfig[] = [
  {
    phase: "MARKET_RESEARCH",
    title: "Market & Competitor Research",
    subtitle: "4-Vector Scrape & DQS Gating",
    icon: Search,
  },
  {
    phase: "AUDIENCE_PERSONA",
    title: "Audience & Persona Engine",
    subtitle: "ICP & Pain-Point Decomposition",
    icon: Users,
    isPluggableSlot: true,
  },
  {
    phase: "CAMPAIGN_STRATEGY",
    title: "Multi-Channel Strategy",
    subtitle: "Positioning & Funnel Architect",
    icon: Target,
    isPluggableSlot: true,
  },
  {
    phase: "MEDIA_GENERATION",
    title: "Creative & Copy Generator",
    subtitle: "Ad Variants & Social Assets",
    icon: Sparkles,
    isPluggableSlot: true,
  },
  {
    phase: "PUBLISHING",
    title: "Distribution Dispatcher",
    subtitle: "CMS & Ad Network Sync",
    icon: Send,
    isPluggableSlot: true,
  },
];

export function AgentStepper({
  activePhase,
  completedPhases,
  isInterrupted = false,
}: AgentStepperProps) {
  const getStepStatus = (phase: AgentPhase): PhaseStatus => {
    if (completedPhases.includes(phase)) return "COMPLETED";
    if (activePhase === phase) {
      return isInterrupted ? "WAITING_APPROVAL" : "RUNNING";
    }
    return "IDLE";
  };

  return (
    <div className="w-full bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 shadow-xl">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Pipeline Orchestration Graph
          </h3>
        </div>
        <span className="text-[11px] text-slate-500 font-mono">
          {completedPhases.length}/{PIPELINE_STEPS.length} Nodes Resolved
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
        {PIPELINE_STEPS.map((step, idx) => {
          const status = getStepStatus(step.phase);
          const Icon = step.icon;

          return (
            <div
              key={step.phase}
              className={cn(
                "relative rounded-xl p-3.5 border transition-all flex flex-col justify-between",
                status === "COMPLETED" &&
                  "bg-emerald-950/20 border-emerald-500/40 text-emerald-300",
                status === "RUNNING" &&
                  "bg-indigo-950/30 border-indigo-500/60 shadow-lg shadow-indigo-500/10 text-indigo-300 ring-1 ring-indigo-500/30",
                status === "WAITING_APPROVAL" &&
                  "bg-amber-950/30 border-amber-500/60 shadow-lg shadow-amber-500/10 text-amber-300 animate-pulse",
                status === "IDLE" &&
                  "bg-slate-900/40 border-slate-800/80 text-slate-400"
              )}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div
                    className={cn(
                      "p-2 rounded-lg transition-colors",
                      status === "COMPLETED" && "bg-emerald-500/20 text-emerald-400",
                      status === "RUNNING" && "bg-indigo-500/20 text-indigo-400",
                      status === "WAITING_APPROVAL" && "bg-amber-500/20 text-amber-400",
                      status === "IDLE" && "bg-slate-800 text-slate-500"
                    )}
                  >
                    <Icon className="w-4 h-4" />
                  </div>

                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-400">
                    Slot 0{idx + 1}
                  </span>
                </div>

                <div className="space-y-0.5">
                  <h4 className="text-xs font-semibold text-slate-200 truncate">
                    {step.title}
                  </h4>
                  <p className="text-[11px] text-slate-400 line-clamp-1">
                    {step.subtitle}
                  </p>
                </div>
              </div>

              {/* Status pill footer */}
              <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px]">
                {status === "COMPLETED" && (
                  <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                    <CheckCircle2 className="w-3 h-3" /> Done
                  </span>
                )}
                {status === "RUNNING" && (
                  <span className="inline-flex items-center gap-1 text-indigo-400 font-medium">
                    <Loader2 className="w-3 h-3 animate-spin" /> Executing...
                  </span>
                )}
                {status === "WAITING_APPROVAL" && (
                  <span className="inline-flex items-center gap-1 text-amber-400 font-medium">
                    <AlertCircle className="w-3 h-3" /> Needs Review
                  </span>
                )}
                {status === "IDLE" && (
                  <span className="inline-flex items-center gap-1 text-slate-500">
                    <Clock className="w-3 h-3" />
                    {step.isPluggableSlot ? "Pluggable Stub" : "Pending"}
                  </span>
                )}

                {step.isPluggableSlot && status === "IDLE" && (
                  <span className="text-[9px] text-slate-600 font-mono">
                    PASS-THROUGH
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
