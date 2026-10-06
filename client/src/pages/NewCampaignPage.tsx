import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CampaignForm } from "@/components/forms/CampaignForm";
import { CampaignInitPayload } from "@/types/api";
import { createCampaignJob, uploadDossiers } from "@/lib/api-client";
import { RecentSessions } from "@/components/dashboard/RecentSessions";
import { AppNavbar } from "@/components/dashboard/AppNavbar";
import { Bot, Terminal, ShieldAlert } from "lucide-react";

export function NewCampaignPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  const handleSubmit = async (
    payload: CampaignInitPayload,
    dossiers: File[]
  ) => {
    setIsLoading(true);
    setErrorNotice(null);

    let jobId: string;
    try {
      jobId = (await createCampaignJob(payload)).job_id;
    } catch (err: unknown) {
      setErrorNotice(
        `Could not start the research run: ${err instanceof Error ? err.message : "the orchestrator is unreachable"}.`
      );
      setIsLoading(false);
      return;
    }

    if (dossiers.length > 0) {
      try {
        await uploadDossiers(jobId, dossiers);
      } catch (uploadErr: unknown) {
        // Do not silently run without the merchant's own material.
        setErrorNotice(
          `Dossier upload failed: ${uploadErr instanceof Error ? uploadErr.message : "unknown error"}. ` +
            "Remove the failing file or try a different format, then launch again."
        );
        setIsLoading(false);
        return;
      }
    }

    setIsLoading(false);
    navigate(`/campaigns/${encodeURIComponent(jobId)}`);
  };

  return (
    <>
      <AppNavbar activeTab="dashboard" />
      <div className="w-full max-w-[1240px] mx-auto pt-16 pb-8 px-2 sm:px-4">
        <div className="bg-[#FAF6EE] rounded-[38px] border border-[#E3DCCB] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 select-none">
      {/* Header */}
      <div className="space-y-3 border-b border-[#EDE7D8] pb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[#19191B] text-white flex items-center justify-center shadow-xs">
            <Bot className="w-5 h-5 text-[#F8B4D9]" />
          </div>
          <div>
            <span className="text-[11px] font-mono tracking-widest uppercase text-zinc-500 font-bold block">
              Intelly Multi-Agent Orchestrator
            </span>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-[#19191B] tracking-tight font-['Outfit',sans-serif]">
              Launch New Strategy Sprint
            </h1>
          </div>
        </div>
        <p className="text-xs sm:text-sm text-zinc-600 max-w-2xl leading-relaxed">
          Initializes the autonomous market research and strategy pipeline. The agent deploys 4-vector
          Tavily, You.com and DuckDuckGo searches, Firecrawl page reading, and factual validation gates before rendering your dashboard.
        </p>
      </div>

      {errorNotice && (
        <div className="p-4 rounded-2xl bg-[#FDE583]/40 border border-[#FDE583] text-[#2D2306] text-xs flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 shrink-0 text-amber-700" />
          <span className="flex-1">{errorNotice}</span>
        </div>
      )}

      {/* Main Form Container */}
      <div className="p-6 sm:p-8 rounded-[28px] bg-[#FFFDF9] border border-[#EDE7D8] shadow-xs">
        <CampaignForm onSubmit={handleSubmit} isLoading={isLoading} />
      </div>

      {/* Return to a past run: open, rename, or delete */}
      <RecentSessions />

      {/* Pipeline Architecture Footer Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
        <div className="p-4 rounded-[22px] bg-[#FAF7EE] border border-[#EDE7D8] flex items-start gap-3">
          <div className="w-7 h-7 rounded-full bg-[#96BFE6] text-[#0F2D4A] flex items-center justify-center shrink-0">
            <Terminal className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="font-bold text-[#19191B] block">4-Vector Search</span>
            <p className="mt-0.5 text-zinc-500 text-[11px]">
              Alternative discovery, pricing scrape, gripe mining, and messaging claims.
            </p>
          </div>
        </div>

        <div className="p-4 rounded-[22px] bg-[#FAF7EE] border border-[#EDE7D8] flex items-start gap-3">
          <div className="w-7 h-7 rounded-full bg-[#96C87C] text-[#19350E] flex items-center justify-center shrink-0">
            <Terminal className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="font-bold text-[#19191B] block">Deterministic DQS</span>
            <p className="mt-0.5 text-zinc-500 text-[11px]">
              Automated quality score formula with autonomous query retry cycles.
            </p>
          </div>
        </div>

        <div className="p-4 rounded-[22px] bg-[#FAF7EE] border border-[#EDE7D8] flex items-start gap-3">
          <div className="w-7 h-7 rounded-full bg-[#F8B4D9] text-[#3D102A] flex items-center justify-center shrink-0">
            <Terminal className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="font-bold text-[#19191B] block">Autonomous Grounding Gate</span>
            <p className="mt-0.5 text-zinc-500 text-[11px]">
              Zero-human gating in research: self-correcting factual grounding against raw crawl text.
            </p>
          </div>
        </div>
      </div>
    </div>
    </div>
    </>
  );
}
