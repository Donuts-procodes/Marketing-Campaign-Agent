import { useState } from "react";
import { HitlState } from "@/hooks/useCampaignStream";
import {
  ShieldAlert,
  CheckCircle2,
  RotateCcw,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface InterruptModalProps {
  checkpoint: HitlState | null;
  onResolve: (action: "APPROVED" | "REVISED", feedback?: string) => Promise<void>;
}

export function InterruptModal({ checkpoint, onResolve }: InterruptModalProps) {
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!checkpoint) return null;

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await onResolve("APPROVED");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRequestRevisions = async () => {
    if (!showFeedbackInput) {
      setShowFeedbackInput(true);
      return;
    }
    if (!feedbackText.trim()) return;

    setIsSubmitting(true);
    try {
      await onResolve("REVISED", feedbackText.trim());
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl rounded-3xl bg-slate-900 border border-slate-700/80 p-6 sm:p-8 shadow-2xl space-y-6">
        {/* Header */}
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-amber-500/10 text-amber-400 border border-amber-500/20 flex-shrink-0">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold border border-amber-500/30">
                HITL GATE ACTIVE
              </span>
              <span className="text-xs text-slate-400 font-mono">
                {checkpoint.checkpoint_id}
              </span>
            </div>
            <h2 className="text-xl font-bold text-slate-100">
              Human-In-The-Loop Approval Checkpoint
            </h2>
          </div>
        </div>

        {/* Prompt */}
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 text-sm text-slate-300 space-y-2">
          <p className="font-semibold text-slate-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            Decision Prompt:
          </p>
          <p className="leading-relaxed text-xs text-slate-300">
            {checkpoint.prompt}
          </p>

          {checkpoint.data && Object.keys(checkpoint.data).length > 0 && (
            <div className="pt-2 border-t border-slate-800/80 grid grid-cols-3 gap-2 text-[11px] font-mono">
              {Object.entries(checkpoint.data).map(([k, v]) => (
                <div key={k} className="p-2 rounded bg-slate-900 border border-slate-800">
                  <span className="text-slate-500 block truncate">{k}</span>
                  <span className="text-slate-200 font-semibold">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Feedback Input if Revisions Requested */}
        {showFeedbackInput && (
          <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
            <label className="text-xs font-semibold text-amber-300 flex items-center gap-1.5">
              <MessageSquare className="w-3.5 h-3.5" />
              Specify Revision Guidance for Agent Re-Execution:
            </label>
            <textarea
              rows={3}
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="e.g. Expand competitor search to include Keychron ergonomic keyboards; tighten pricing comparison..."
              className="w-full p-3 rounded-xl bg-slate-950 border border-amber-500/40 text-slate-100 text-xs placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleApprove}
            className="flex-1 py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center justify-center gap-2 transition shadow-lg shadow-emerald-600/25 hover:shadow-emerald-600/40 disabled:opacity-50 cursor-pointer"
          >
            <CheckCircle2 className="w-4 h-4" />
            Approve & Synthesize Audience Persona
          </button>

          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleRequestRevisions}
            className={cn(
              "py-3 px-4 rounded-xl font-semibold text-xs flex items-center justify-center gap-2 border transition disabled:opacity-50 cursor-pointer",
              showFeedbackInput
                ? "bg-amber-600 hover:bg-amber-500 text-white border-amber-500 shadow-lg shadow-amber-600/25"
                : "bg-slate-800 hover:bg-slate-700 text-amber-300 border-amber-500/30"
            )}
          >
            <RotateCcw className="w-4 h-4" />
            {showFeedbackInput ? "Submit Guidance & Re-run" : "Request Revisions"}
          </button>
        </div>
      </div>
    </div>
  );
}
