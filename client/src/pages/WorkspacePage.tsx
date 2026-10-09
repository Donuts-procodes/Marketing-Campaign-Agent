import { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Sparkles,
  Bot,
  Send,
  UploadCloud,
  ArrowRight,
  RefreshCw,
  X,
  CheckCircle2,
  Calendar,
  Mail,
  Megaphone,
  Settings,
  AlertCircle,
  FileText,
  ExternalLink,
  Trash2,
} from "lucide-react";
import {
  createCampaignJob,
  uploadDossiers,
  listSessions,
  getSession,
  deleteSession,
  streamReportChat,
  autofillFromFiles,
  interpretQuery,
  approveCampaignStrategy,
} from "@/lib/api-client";
import { useCampaignStream } from "@/hooks/useCampaignStream";
import { toRivalView, RivalView } from "@/lib/rivalMetrics";
import { SessionSummary, AutofillFields } from "@/types/api";
import { SWOTReportDelta } from "@/types/research";
import type { CampaignStrategyBrief } from "@/types/strategy";
import { GlobalSettingsModal } from "@/components/dashboard/GlobalSettingsModal";
import { LiveTokenTracker } from "@/components/dashboard/LiveTokenTracker";

// ─── TYPES ───────────────────────────────────────────────────────────────────

export type WorkspaceStage = "brief" | "intel" | "strategy" | "content" | "schedule" | "perf";
export type IntelSubTab = "research" | "audience";
export type ContentChannel = "email" | "linkedin" | "retarget" | "ads";

interface Message {
  id: string;
  who: "user" | "agent";
  text: string;
  time?: string;
}

const STAGE_KEYS: WorkspaceStage[] = ["brief", "intel", "strategy", "content", "schedule", "perf"];
const STAGE_LABELS = ["Brief", "Research & Audience", "Strategy", "Content", "Schedule", "Live"];

export function WorkspacePage() {
  const navigate = useNavigate();
  const { jobId: routeJobId } = useParams<{ jobId?: string }>();
  const [activeJobId, setActiveJobId] = useState<string | null>(routeJobId || null);

  // Sessions from database
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Primary state machine
  const [view, setView] = useState<"home" | "ws">(routeJobId ? "ws" : "home");
  const [stage, setStage] = useState<WorkspaceStage>(routeJobId ? "intel" : "brief");
  const [maxStep, setMaxStep] = useState<number>(routeJobId ? 1 : 0);
  const [briefSent, setBriefSent] = useState<boolean>(!!routeJobId);

  // Intake Form Inputs
  const [productName, setProductName] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [briefText, setBriefText] = useState<string>("");
  const [targetGeo, setTargetGeo] = useState<string>("United States");
  const [knownCompetitors, setKnownCompetitors] = useState<string>("");
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isAutofilling, setIsAutofilling] = useState<boolean>(false);
  const [autofilledFields, setAutofilledFields] = useState<Set<string>>(new Set());
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  // Sub-tabs
  const [intelTab, setIntelTab] = useState<IntelSubTab>("research");
  const [contentTab, setContentTab] = useState<ContentChannel>("email");
  const [assetSel, setAssetSel] = useState<string>("e1");

  // Approval flags
  const [stratApproved, setStratApproved] = useState<boolean>(false);
  const [stratRevised, setStratRevised] = useState<boolean>(false);
  const [approved, setApproved] = useState<{ email: boolean; linkedin: boolean; retarget: boolean; ads: boolean }>({
    email: false,
    linkedin: false,
    retarget: false,
    ads: false,
  });
  const [live, setLive] = useState<boolean>(false);
  const [insight, setInsight] = useState<number>(0);

  // Drawers and sidebars
  const [sbOpen, setSbOpen] = useState<boolean>(true);
  const [agentOpen, setAgentOpen] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [selectedRival, setSelectedRival] = useState<RivalView | null>(null);
  const [rivalTab, setRivalTab] = useState<"ov" | "mk" | "hi" | "cu">("ov");

  // Agent Chat State
  const [draft, setDraft] = useState<string>("");
  const [isAgentTyping, setIsAgentTyping] = useState<boolean>(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "m0",
      who: "agent",
      text: "Welcome to your Campaigning Agent Workspace. Enter your product and goal to deploy the autonomous research agent.",
    },
  ]);

  // Live SSE connection to the orchestrator
  const { state: streamState } = useCampaignStream(activeJobId);
  const {
    connectionStatus,
    telemetryLogs,
    swotReport: liveReport,
    strategyBrief: liveStrategyBrief,
  } = streamState;

  // Stored report and brief from getSession if loaded from history
  const [sessionReport, setSessionReport] = useState<SWOTReportDelta | null>(null);
  const [sessionStrategyBrief, setSessionStrategyBrief] = useState<CampaignStrategyBrief | null>(null);

  // Effective report and brief (stream has priority, then saved session)
  const report = liveReport || sessionReport;
  const strategyBrief = liveStrategyBrief || sessionStrategyBrief;

  // Sync routeJobId with activeJobId
  useEffect(() => {
    if (routeJobId && routeJobId !== activeJobId) {
      setActiveJobId(routeJobId);
      setView("ws");
      setStage("intel");
      setBriefSent(true);
    }
  }, [routeJobId]);

  // Load real sessions from backend
  const refreshSessions = async () => {
    setLoadingSessions(true);
    try {
      const res = await listSessions(50);
      setSessions(res.sessions || []);
    } catch {
      // offline / mock fallback
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    refreshSessions();
  }, []);

  // When activeJobId changes, load saved session if not streaming
  useEffect(() => {
    if (!activeJobId) return;
    getSession(activeJobId)
      .then((detail) => {
        if (detail.swot_report) {
          setSessionReport(detail.swot_report as SWOTReportDelta);
          setMaxStep((prev) => Math.max(prev, 1));
        }
        if (detail.strategy_brief) {
          setSessionStrategyBrief(detail.strategy_brief as CampaignStrategyBrief);
          setMaxStep((prev) => Math.max(prev, 2));
        }
        if (detail.merchant_context) {
          const ctx = detail.merchant_context as Record<string, string>;
          if (ctx.product_name) setProductName(ctx.product_name);
          if (ctx.category) setCategory(ctx.category);
          if (ctx.goal || ctx.primary_value_prop) setBriefText(ctx.goal || ctx.primary_value_prop);
        }
      })
      .catch(() => {});
  }, [activeJobId]);

  // Sync real-time stream status
  const isRunning =
    isSubmitting ||
    connectionStatus === "CONNECTING" ||
    connectionStatus === "STREAMING" ||
    (activeJobId && !report && connectionStatus !== "COMPLETED" && connectionStatus !== "ERROR");

  // Dynamically derive rivals list from real report
  const rivalsList: RivalView[] = useMemo(() => {
    if (report && report.competitors && report.competitors.length > 0) {
      return report.competitors.map((c, i) => toRivalView(c, i));
    }
    return [];
  }, [report]);

  // Synchronize only high-level milestone events into conversational agent messages
  const lastProcessedLogRef = useRef<number>(0);
  const seenMilestonesRef = useRef<Set<string>>(new Set());
  const hasSentDoneRef = useRef<string | null>(null);

  useEffect(() => {
    if (telemetryLogs.length > lastProcessedLogRef.current) {
      const newItems = telemetryLogs.slice(lastProcessedLogRef.current);
      lastProcessedLogRef.current = telemetryLogs.length;

      newItems.forEach((log) => {
        const msg = log.message || "";
        // Keep raw internal debug, search queues, round facts out of chat
        if (
          msg.startsWith("[") ||
          msg.includes("Queue ") ||
          msg.includes("Round ") ||
          msg.includes("query ") ||
          msg.includes("Scraped ") ||
          msg.includes("TAVILY_SEARCH") ||
          msg.includes("DEEP_SEARCH")
        ) {
          return;
        }

        if (msg.includes("Started execution node: market_research") && !seenMilestonesRef.current.has("start_research")) {
          seenMilestonesRef.current.add("start_research");
          pushAgent("Market research initiated: discovering direct rivals and category alternatives.");
        } else if (msg.includes("competitor(s) found") && !seenMilestonesRef.current.has("found_comps")) {
          seenMilestonesRef.current.add("found_comps");
          pushAgent("Identified active market competitors. Extracting landing pages, claims, and pricing tiers.");
        } else if (msg.includes("Review context synthesized") && !seenMilestonesRef.current.has("review_syn")) {
          seenMilestonesRef.current.add("review_syn");
          pushAgent("Synthesizing customer reviews, complaints, and Breakout Leap catalysts.");
        }
      });
    }
  }, [telemetryLogs]);

  // When run completes (deduplicated per activeJobId)
  useEffect(() => {
    if (connectionStatus === "COMPLETED" && report && hasSentDoneRef.current !== activeJobId) {
      hasSentDoneRef.current = activeJobId;
      setMaxStep((prev) => Math.max(prev, 1));
      setMessages((prev) => [
        ...prev,
        {
          id: "m-done-" + (activeJobId || Date.now()),
          who: "agent",
          text: `Research complete! Analyzed ${report.competitors?.length || 0} competitors. Us vs fastest-growing rivals matrix and Breakout Leap catalysts are ready for review.`,
        },
      ]);
    }
  }, [connectionStatus, report, activeJobId]);

  // Helper to push messages
  const pushAgent = (text: string) => {
    setMessages((prev) => [...prev, { id: "m" + Date.now(), who: "agent", text }]);
  };
  const pushUser = (text: string) => {
    setMessages((prev) => [...prev, { id: "m" + Date.now(), who: "user", text }]);
  };

  // ─── WORKFLOW HANDLERS ─────────────────────────────────────────────────────

  const handleStartCampaign = async () => {
    if (!productName.trim()) {
      setErrorNotice("Please enter your product or brand name to start research.");
      return;
    }
    if (!briefText.trim()) {
      setErrorNotice("Please enter what you want to achieve or your campaign goal.");
      return;
    }

    setErrorNotice(null);
    setIsSubmitting(true);
    setBriefSent(true);
    setStage("intel");
    setMaxStep(1);
    setIntelTab("research");

    lastProcessedLogRef.current = 0;
    seenMilestonesRef.current.clear();
    hasSentDoneRef.current = null;

    pushUser(`Product: ${productName} (${category})\nGoal: ${briefText}`);
    pushAgent(`Deploying autonomous market research agent for ${productName}. Initializing 4-vector SERP discovery and Scrape.do DOM extraction.`);

    try {
      // Check BYOK config in localStorage
      let byokConfig = undefined;
      try {
        const raw = localStorage.getItem("intelly.byok");
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed.apiKey) {
            byokConfig = {
              provider: parsed.provider || "openai",
              model: parsed.model || "gpt-4o",
              api_key: parsed.apiKey,
            };
          }
        }
      } catch {}

      const rivalsArray = knownCompetitors
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const payload = {
        merchant_context: {
          product_name: productName.trim(),
          category: category.trim() || "Technology",
          primary_value_prop: briefText.trim(),
          goal: briefText.trim(),
          target_geography: targetGeo.trim(),
          known_competitors: rivalsArray,
        },
        byok_config: byokConfig,
        run_mode: "fresh" as const,
      };

      const res = await createCampaignJob(payload);
      const newJobId = res.job_id;
      setActiveJobId(newJobId);
      window.history.pushState({}, "", `/campaigns/${newJobId}`);

      // Upload dossiers if any
      if (uploadedFiles.length > 0) {
        pushAgent(`Uploading ${uploadedFiles.length} context dossier files...`);
        try {
          await uploadDossiers(newJobId, uploadedFiles);
          pushAgent("Dossier context ingested into vector grounding.");
        } catch (uploadErr) {
          pushAgent(`Warning: Dossier upload failed: ${uploadErr instanceof Error ? uploadErr.message : "network issue"}`);
        }
      }

      refreshSessions();
    } catch (err: unknown) {
      setErrorNotice(err instanceof Error ? err.message : "Failed to launch campaign research run");
      pushAgent(`Execution failed: ${err instanceof Error ? err.message : "Failed to connect to orchestrator"}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectSession = (s: SessionSummary) => {
    setActiveJobId(s.job_id);
    setView("ws");
    setBriefSent(true);
    setStage("intel");
    setMaxStep(1);
    navigate(`/campaigns/${s.job_id}`);
    if (s.product_name) setProductName(s.product_name);
    if (s.category) setCategory(s.category);
  };

  const handleDeleteSession = async (jobId: string) => {
    if (!window.confirm("Are you sure you want to delete this campaign session?")) return;
    try {
      await deleteSession(jobId);
      setSessions((prev) => prev.filter((s) => s.job_id !== jobId));
      if (activeJobId === jobId) {
        setActiveJobId(null);
        setSessionReport(null);
        setView("home");
        navigate("/");
      }
    } catch (err: unknown) {
      setErrorNotice(err instanceof Error ? err.message : "Failed to delete session");
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const applyExtractedFields = (fields: AutofillFields) => {
    const filled = new Set<string>();
    if (fields.product_name?.trim()) {
      setProductName(fields.product_name.trim());
      filled.add("productName");
    }
    if (fields.category?.trim()) {
      setCategory(fields.category.trim());
      filled.add("category");
    }
    if (fields.goal?.trim() || fields.primary_value_prop?.trim()) {
      setBriefText((fields.goal || fields.primary_value_prop || "").trim());
      filled.add("briefText");
    }
    if (fields.target_geography?.trim()) {
      setTargetGeo(fields.target_geography.trim());
      filled.add("targetGeo");
    }
    if (fields.known_competitors && fields.known_competitors.length > 0) {
      setKnownCompetitors(fields.known_competitors.join(", "));
      filled.add("knownCompetitors");
    }
    setAutofilledFields(filled);
  };

  const handleAutofillFiles = async (filesToParse: File[]) => {
    if (!filesToParse.length) return;
    setIsAutofilling(true);
    setErrorNotice(null);
    try {
      let byokConfig = undefined;
      try {
        const raw = localStorage.getItem("intelly.byok");
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed.apiKey) {
            byokConfig = {
              provider: parsed.provider || "openai",
              model: parsed.model || "gpt-4o",
              api_key: parsed.apiKey,
            };
          }
        }
      } catch {}

      const res = await autofillFromFiles(filesToParse, byokConfig);
      if (res && res.fields) {
        applyExtractedFields(res.fields);
        pushAgent(`Extracted campaign fields from ${filesToParse.length} document(s).`);
      }
    } catch (err: unknown) {
      setErrorNotice(err instanceof Error ? err.message : "Failed to extract fields from documents");
    } finally {
      setIsAutofilling(false);
    }
  };

  const handleInterpretQuery = async () => {
    const textToInterpret = briefText.trim() || productName.trim();
    if (!textToInterpret) {
      setErrorNotice("Enter your campaign goal or product idea first to auto-fill with AI.");
      return;
    }
    setIsAutofilling(true);
    setErrorNotice(null);
    try {
      const res = await interpretQuery(textToInterpret);
      if (res && res.fields) {
        applyExtractedFields(res.fields);
        pushAgent("Parsed prompt and auto-filled campaign parameters.");
      }
    } catch (err: unknown) {
      setErrorNotice(err instanceof Error ? err.message : "Failed to interpret brief");
    } finally {
      setIsAutofilling(false);
    }
  };

  const handleToStrategy = () => {
    setStage("strategy");
    setMaxStep((prev) => Math.max(prev, 2));
    pushAgent("Strategy synthesized from competitor positioning gaps. Read through the angles and approve to generate copy.");
  };

  const handleRequestChanges = () => {
    setStratRevised(true);
    setAgentOpen(true);
    setDraft("Sharpen the positioning angle against " + (rivalsList[0]?.name || "competitors"));
  };

  const handleApproveStrategy = async () => {
    setStratApproved(true);
    if (activeJobId) {
      try {
        const approvedBrief = await approveCampaignStrategy(activeJobId);
        setSessionStrategyBrief(approvedBrief);
      } catch (err) {
        console.warn("Strategy approval sync:", err);
      }
    }
    setStage("content");
    setMaxStep((prev) => Math.max(prev, 3));
    pushUser("Approved strategy.");
    pushAgent("Strategy approved. Generating targeted Email, LinkedIn, Retargeting, and Search ad copy.");
  };

  const handleApproveContent = () => {
    setStage("schedule");
    setMaxStep((prev) => Math.max(prev, 4));
    pushAgent("Content approved. Launch schedule ready.");
  };

  const handlePublishNow = () => {
    setLive(true);
    setStage("perf");
    setInsight(1);
    setMaxStep(5);
    pushAgent("Campaign published live. Telemetry cockpit active and monitoring performance.");
  };

  const handleScheduleCampaign = () => {
    setLive(true);
    setStage("perf");
    setInsight(1);
    setMaxStep(5);
    pushAgent("Campaign scheduled. Autonomous monitoring active.");
  };

  const handleApplyInsight = () => {
    setInsight(2);
    pushAgent("Applied agent recommendation: shift budget into high-performing angle.");
  };

  // Chat message sending
  const handleSendMessage = async () => {
    if (!draft.trim()) return;
    const txt = draft.trim();
    pushUser(txt);
    setDraft("");

    if (activeJobId) {
      setIsAgentTyping(true);
      let agentReply = "";
      try {
        await streamReportChat(
          activeJobId,
          [{ role: "user", content: txt }],
          {
            onDelta: (chunk) => {
              agentReply += chunk;
            },
            onStatus: () => {
              // optional status
            },
          }
        );
        if (agentReply) {
          pushAgent(agentReply);
        } else {
          pushAgent("Understood. Updating campaign parameters.");
        }
      } catch {
        pushAgent(`Factored that feedback into the ${stage} plan.`);
      } finally {
        setIsAgentTyping(false);
      }
    } else {
      setTimeout(() => {
        pushAgent(`Noted. I will factor that into the research parameters for ${productName || "your campaign"}.`);
      }, 500);
    }
  };

  const stageIdx = live ? 5 : STAGE_KEYS.indexOf(stage);

  // Status chip metadata
  const statusMeta = (() => {
    if (live) return { label: "Live", bg: "bg-[#E4F2EA]", text: "text-[#256545]", dot: "bg-[#3F9068]" };
    if (stage === "brief") return { label: "Draft", bg: "bg-[#F6F1E8]", text: "text-[#4A4239]", dot: "bg-[#8A8176]" };
    if (stage === "intel")
      return isRunning
        ? { label: "Researching", bg: "bg-[#FDF1EB]", text: "text-[#8F2F14]", dot: "bg-[#E2552F] animate-pulse" }
        : { label: "Insights ready", bg: "bg-[#E4F2EA]", text: "text-[#256545]", dot: "bg-[#3F9068]" };
    if (stage === "strategy")
      return stratApproved
        ? { label: "Strategy approved", bg: "bg-[#E4F2EA]", text: "text-[#256545]", dot: "bg-[#3F9068]" }
        : stratRevised
        ? { label: "Revision requested", bg: "bg-[#FDF1EB]", text: "text-[#8F2F14]", dot: "bg-[#E2552F]" }
        : { label: "Needs your approval", bg: "bg-[#FBEFD9]", text: "text-[#7A4506]", dot: "bg-[#C47A12]" };
    if (stage === "content")
      return { label: "Content ready", bg: "bg-[#FBEFD9]", text: "text-[#7A4506]", dot: "bg-[#C47A12]" };
    return { label: "Ready to schedule", bg: "bg-[#FBEFD9]", text: "text-[#7A4506]", dot: "bg-[#C47A12]" };
  })();

  // Dynamic Ad angles from report
  const angles = report?.suggested_ad_angles || [];

  // Dynamic Copy generated from real research
  const dynamicCopy = useMemo(() => {
    const brand = productName || "Our Solution";
    const topRival = rivalsList[0]?.name || "legacy competitors";
    const hook1 = angles[0]?.hook || `Why modern teams are choosing ${brand} over ${topRival}`;
    const hook2 = angles[1]?.hook || `The fastest way to automate workflows without migration risk`;
    return {
      e1: {
        subject: hook1,
        body: `Hi there,\n\nIf you have been evaluating ${topRival}, you probably noticed high implementation friction and rigid contracts.\n\n${brand} was built specifically to solve that. Our guided deployment gets your team live in days with full enterprise security.\n\nBook a 15-minute walkthrough to see our interactive architecture map.\n\nBest,\nThe ${brand} Team`,
      },
      e2: {
        subject: hook2,
        body: `Hi again,\n\nMost teams delay switching tools because they cannot afford migration downtime.\n\nWith ${brand}, your existing workflows stay intact while our engine modernizes approvals behind the scenes.\n\nSee how peer companies made the leap.\n\nBest,\nThe ${brand} Team`,
      },
      l1: {
        subject: "",
        body: `Migrating off ${topRival} doesn't have to take six months.\n\nMid-market teams are switching to ${brand} with zero workflow downtime, guaranteed onboarding, and transparent pricing.\n\nRead the comparison breakdown. Link in comments.`,
      },
      r1: {
        subject: "",
        body: `Evaluating ${topRival}? Compare features, verified pricing, and migration guarantees side-by-side with ${brand}.`,
      },
      a1: {
        subject: "",
        body: `${brand} vs ${topRival} | Live in Days, Not Months\nEnterprise Reliability Without Long Contracts\nGet the side-by-side comparison report now.`,
      },
    };
  }, [productName, rivalsList, angles]);

  // ─── RENDER HOME VIEW (REAL CAMPAIGNS FROM DATABASE) ───────────────────────

  if (view === "home") {
    return (
      <div className="min-h-screen bg-[#FAF6EF] text-[#1F1A17] font-['Manrope',sans-serif]">
        <header className="h-16 border-b border-[#E1D7C8] px-6 flex items-center justify-between bg-[#FAF6EF]">
          <div className="flex items-center gap-3">
            <span className="w-7 h-7 rounded-lg bg-[#C7431F] text-white flex items-center justify-center font-bold">
              <Sparkles className="w-4 h-4" />
            </span>
            <span className="font-['Bricolage_Grotesque'] text-lg font-bold">Campaigning Agent</span>
            <span className="text-[#8A8176]">/</span>
            <span className="text-sm font-semibold text-[#8A8176]">Overview</span>
          </div>

          <div className="flex items-center gap-2.5">
            <LiveTokenTracker onClick={() => setSettingsOpen(true)} />
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 rounded-xl border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[#4A4239] transition shadow-xs cursor-pointer"
              title="Global Settings & BYOK"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </header>

        <div className="max-w-[1080px] mx-auto px-6 py-12">
          <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
            <div>
              <h1 className="font-['Bricolage_Grotesque'] text-3xl sm:text-4xl font-extrabold tracking-tight">
                Your campaigns
              </h1>
              <p className="mt-2 text-[#6B625A] text-sm sm:text-base">
                Every campaign executes autonomous market research, competitor matrix crawling, and multi-channel creative generation.
              </p>
            </div>
            <button
              onClick={() => {
                setActiveJobId(null);
                setSessionReport(null);
                setBriefSent(false);
                setProductName("");
                setCategory("");
                setBriefText("");
                setView("ws");
                setStage("brief");
              }}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white font-semibold text-sm transition shadow-sm cursor-pointer"
            >
              <Sparkles className="w-4 h-4" />
              New campaign
            </button>
          </div>

          <div className="bg-white rounded-2xl border border-[#E1D7C8] shadow-sm divide-y divide-[#EFE7DB] overflow-hidden">
            {loadingSessions ? (
              <div className="p-12 text-center text-[#8A8176] space-y-3">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto text-[#C7431F]" />
                <p className="text-xs">Loading live campaign sessions from database...</p>
              </div>
            ) : sessions.length === 0 ? (
              <div className="p-12 text-center text-[#8A8176] space-y-3">
                <Sparkles className="w-8 h-8 mx-auto text-[#C7431F]" />
                <p className="text-sm font-bold text-[#1F1A17]">No campaigns found</p>
                <p className="text-xs max-w-sm mx-auto">
                  Click "New campaign" to launch your first autonomous market intelligence sprint.
                </p>
              </div>
            ) : (
              sessions.map((s) => {
                const isComplete = s.status === "complete" || s.status === "COMPLETED";
                return (
                  <div
                    key={s.job_id}
                    className="w-full p-6 hover:bg-[#FDF9F3] transition flex items-center justify-between gap-4 group border-b border-[#E1D7C8] last:border-0"
                  >
                    <button
                      onClick={() => handleSelectSession(s)}
                      className="text-left flex-1 min-w-0 cursor-pointer"
                    >
                      <span className="block font-['Bricolage_Grotesque'] text-lg font-bold group-hover:text-[#C7431F] transition truncate">
                        {s.product_name || s.label || s.job_id}
                      </span>
                      <span className="text-xs text-[#8A8176] mt-0.5 block truncate">
                        {s.category || "Competitive Sprint"} • {s.job_id} •{" "}
                        {s.finished_at ? new Date(s.finished_at).toLocaleDateString() : "Active"}
                      </span>
                    </button>
                    <div className="flex items-center gap-3 shrink-0">
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-bold ${
                          isComplete ? "bg-[#E4F2EA] text-[#256545]" : "bg-[#FDF1EB] text-[#8F2F14]"
                        }`}
                      >
                        {isComplete ? "Completed" : s.status}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSession(s.job_id);
                        }}
                        className="p-2 rounded-lg text-[#8A8176] hover:text-[#A63030] hover:bg-[#FDE6E4] transition cursor-pointer"
                        title="Delete campaign session"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <GlobalSettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
      </div>
    );
  }

  // ─── RENDER WORKSPACE VIEW ─────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#FAF6EF] text-[#1F1A17] font-['Manrope',sans-serif] flex flex-col selection:bg-[#F3CFC0] selection:text-[#8F2F14]">
      {/* ─── TOP WORKSPACE HEADER ─── */}
      <header className="h-16 border-b border-[#E1D7C8] px-4 sm:px-6 flex items-center justify-between bg-[#FAF6EF] sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSbOpen(!sbOpen)}
            className="p-2 rounded-lg border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[#4A4239] transition"
            title="Toggle sidebar"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <rect x="3" y="4" width="18" height="16" rx="3"></rect>
              <path d="M9 4v16"></path>
            </svg>
          </button>
          <button
            onClick={() => setView("home")}
            className="flex items-center gap-2 group cursor-pointer"
          >
            <span className="w-7 h-7 rounded-lg bg-[#C7431F] text-white flex items-center justify-center font-bold shadow-xs">
              <Sparkles className="w-4 h-4" />
            </span>
            <span className="font-['Bricolage_Grotesque'] text-base sm:text-lg font-bold text-[#1F1A17] group-hover:text-[#C7431F] transition">
              Campaigning Agent
            </span>
          </button>
        </div>

        {/* Steps Stepper */}
        <nav className="hidden md:flex items-center gap-1.5" aria-label="Campaign progress">
          {STAGE_LABELS.map((label, idx) => {
            const isDone = idx < stageIdx;
            const isCur = idx === stageIdx;
            const isLocked = idx > maxStep && !live;

            return (
              <button
                key={label}
                disabled={isLocked}
                onClick={() => {
                  if (live) {
                    setStage(idx === 5 ? "perf" : (STAGE_KEYS[idx] as WorkspaceStage));
                  } else if (idx <= maxStep) {
                    setStage(STAGE_KEYS[idx] as WorkspaceStage);
                  }
                }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                  isCur
                    ? "bg-[#1F1A17] text-white shadow-xs"
                    : isDone
                    ? "text-[#1F1A17] hover:bg-[#EFE7DB] cursor-pointer"
                    : "text-[#8A8176] opacity-50 cursor-not-allowed"
                }`}
              >
                <span
                  className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                    isCur
                      ? "bg-[#C7431F] text-white"
                      : isDone
                      ? "bg-[#3F9068] text-white"
                      : "bg-[#E1D7C8] text-[#6B625A]"
                  }`}
                >
                  {isDone ? "✓" : idx + 1}
                </span>
                <span>{label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Status, Token Monitor, Settings & Agent Toggle */}
        <div className="flex items-center gap-2.5">
          <LiveTokenTracker onClick={() => setSettingsOpen(true)} />

          <button
            onClick={() => setSettingsOpen(true)}
            className="p-2 rounded-xl border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[#4A4239] transition shadow-xs cursor-pointer"
            title="Global Settings & BYOK"
          >
            <Settings className="w-4 h-4" />
          </button>

          <div className={`hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-bold ${statusMeta.bg} ${statusMeta.text}`}>
            <span className={`w-2 h-2 rounded-full ${statusMeta.dot}`} />
            <span>{statusMeta.label}</span>
          </div>

          <button
            onClick={() => setAgentOpen(!agentOpen)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs cursor-pointer ${
              agentOpen
                ? "bg-[#1F1A17] text-white border-[#1F1A17]"
                : "bg-white text-[#1F1A17] border-[#E1D7C8] hover:bg-[#FDF9F3]"
            }`}
          >
            <Bot className="w-3.5 h-3.5 text-[#C7431F]" />
            <span>Agent</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#3F9068]" />
          </button>
        </div>
      </header>

      {/* ─── MAIN WORKSPACE BODY (WITH COLLAPSIBLE SIDEBAR) ─── */}
      <div className="flex-1 flex overflow-hidden">
        {/* REAL DATABASE SESSIONS SIDEBAR */}
        {sbOpen && (
          <aside className="w-72 border-r border-[#E1D7C8] bg-[#F8F4EC] p-4 flex flex-col gap-5 overflow-y-auto shrink-0 select-none">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold tracking-wider uppercase text-[#8A8176]">
                  Active Campaign
                </span>
                {activeJobId && (
                  <span className="font-mono text-[10px] text-[#8A8176]">{activeJobId.slice(0, 10)}...</span>
                )}
              </div>
              <div className="p-3 rounded-xl bg-white border border-[#E1D7C8] shadow-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-['Bricolage_Grotesque'] text-sm font-bold truncate">
                    {productName || "New Campaign"}
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${statusMeta.bg} ${statusMeta.text}`}>
                    {statusMeta.label}
                  </span>
                </div>
                <span className="text-[11px] text-[#8A8176] mt-1 block truncate">
                  {category || "Awaiting briefing"}
                </span>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold tracking-wider uppercase text-[#8A8176]">
                  Past Runs ({sessions.length})
                </span>
                <button
                  onClick={refreshSessions}
                  className="p-1 rounded hover:bg-[#EFE7DB] text-[#8A8176]"
                  title="Refresh runs"
                >
                  <RefreshCw className={`w-3 h-3 ${loadingSessions ? "animate-spin" : ""}`} />
                </button>
              </div>

              <div className="space-y-1.5 text-xs max-h-72 overflow-y-auto">
                {sessions.map((s) => (
                  <div
                    key={s.job_id}
                    className={`group flex items-center justify-between p-2.5 rounded-xl border transition ${
                      activeJobId === s.job_id
                        ? "bg-white border-[#C7431F] shadow-xs"
                        : "bg-white/60 border-[#EFE7DB] hover:bg-white text-[#4A4239]"
                    }`}
                  >
                    <button
                      onClick={() => handleSelectSession(s)}
                      className="text-left flex-1 min-w-0 cursor-pointer"
                    >
                      <span className="font-bold block truncate">{s.product_name || s.job_id}</span>
                      <span className="text-[10px] text-[#8A8176] block truncate">
                        {s.category || "Sprint"} • {s.status}
                      </span>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteSession(s.job_id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#FDE6E4] text-[#8A8176] hover:text-[#A63030] transition ml-1 shrink-0 cursor-pointer"
                      title="Delete session"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {uploadedFiles.length > 0 && (
              <div>
                <span className="text-[11px] font-bold tracking-wider uppercase text-[#8A8176] block mb-2">
                  Grounding Files ({uploadedFiles.length})
                </span>
                <div className="space-y-1.5 text-xs">
                  {uploadedFiles.map((f, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-white/70 border border-[#EFE7DB]">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <FileText className="w-3.5 h-3.5 text-[#C7431F] shrink-0" />
                        <span className="truncate font-medium">{f.name}</span>
                      </div>
                      <button
                        onClick={() => handleRemoveFile(i)}
                        className="p-1 text-[#8A8176] hover:text-[#A63030] hover:bg-[#FDE6E4] rounded transition cursor-pointer shrink-0 ml-1"
                        title="Remove file"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </aside>
        )}

        {/* ─── CANVAS STAGE CONTENT ─── */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-8 py-8">
          {errorNotice && (
            <div className="mb-6 p-4 rounded-xl bg-[#FDE6E4] border border-[#F3CFC0] text-[#A63030] text-xs font-semibold flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{errorNotice}</span>
              </div>
              <button onClick={() => setErrorNotice(null)} className="p-1 hover:bg-white/50 rounded">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* STAGE 1: BRIEF */}
          {stage === "brief" && (
            <div className="max-w-[760px] mx-auto space-y-8 animate-fade-up">
              {!briefSent ? (
                <>
                  <div>
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold tracking-wide uppercase text-[#C7431F] bg-[#FDF1EB] px-3 py-1 rounded-full mb-3">
                      <Sparkles className="w-3.5 h-3.5" />
                      Campaign Brief
                    </span>
                    <h1 className="font-['Bricolage_Grotesque'] text-3xl sm:text-4xl font-extrabold tracking-tight">
                      Deploy Your Marketing Agent
                    </h1>
                    <p className="mt-2 text-[#6B625A] text-sm sm:text-base leading-relaxed">
                      Enter your product, sector, and goals. The autonomous agent deploys multi-vector web discovery, Scrape.do competitor extraction, and Breakout Leap synthesis.
                    </p>
                  </div>

                  {/* Product Details */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold uppercase text-[#4A4239]">
                          Your Product / Brand Name <span className="text-[#C7431F]">*</span>
                        </label>
                        {autofilledFields.has("productName") && (
                          <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            Auto-filled
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        value={productName}
                        onChange={(e) => setProductName(e.target.value)}
                        placeholder="e.g. Lumora, DevFlow, Linear"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-[#E1D7C8] bg-white text-sm focus:border-[#C7431F]"
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold uppercase text-[#4A4239]">
                          Category / Industry
                        </label>
                        {autofilledFields.has("category") && (
                          <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            Auto-filled
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        placeholder="e.g. B2B Workflow Automation, FinTech"
                        className="w-full px-3.5 py-2.5 rounded-xl border border-[#E1D7C8] bg-white text-sm focus:border-[#C7431F]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-bold uppercase tracking-wider text-[#4A4239]">
                        Campaign Goal & Value Proposition <span className="text-[#C7431F]">*</span>
                      </label>
                      <button
                        type="button"
                        onClick={handleInterpretQuery}
                        disabled={isAutofilling}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[11px] font-bold text-[#C7431F] transition cursor-pointer shadow-xs disabled:opacity-50"
                        title="Analyze brief text with AI to auto-fill product, category, and competitors"
                      >
                        <Sparkles className={`w-3 h-3 ${isAutofilling ? "animate-spin" : ""}`} />
                        {isAutofilling ? "Auto-filling..." : "Auto-fill with AI"}
                      </button>
                    </div>
                    <textarea
                      value={briefText}
                      onChange={(e) => setBriefText(e.target.value)}
                      rows={4}
                      className="w-full p-4 rounded-xl border border-[#E1D7C8] bg-white text-sm focus:outline-none focus:border-[#C7431F] transition"
                      placeholder="e.g. Displace legacy enterprise competitors by guaranteeing 14-day zero-downtime rollout. Target dormant mid-market trial accounts..."
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold uppercase text-[#8A8176]">Target Geography</label>
                        {autofilledFields.has("targetGeo") && (
                          <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            Auto-filled
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        value={targetGeo}
                        onChange={(e) => setTargetGeo(e.target.value)}
                        placeholder="e.g. United States, Global"
                        className="w-full px-3.5 py-2 rounded-xl border border-[#E1D7C8] bg-white text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold uppercase text-[#8A8176]">Known Competitors (Optional)</label>
                        {autofilledFields.has("knownCompetitors") && (
                          <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            Auto-filled
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        value={knownCompetitors}
                        onChange={(e) => setKnownCompetitors(e.target.value)}
                        placeholder="Comma-separated: Zapier, Workato"
                        className="w-full px-3.5 py-2 rounded-xl border border-[#E1D7C8] bg-white text-xs"
                      />
                    </div>
                  </div>

                  {/* Supporting Context & Dossiers */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-bold uppercase tracking-wider text-[#4A4239]">
                        Add Supporting Context Files (Auto-fills Form)
                      </div>
                      {isAutofilling && (
                        <span className="inline-flex items-center gap-1.5 text-xs text-[#C7431F] font-bold">
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          Extracting fields from document...
                        </span>
                      )}
                    </div>
                    <label className="border-2 border-dashed border-[#E1D7C8] hover:border-[#C7431F] bg-white/70 hover:bg-white rounded-2xl p-6 text-center transition cursor-pointer flex flex-col items-center justify-center gap-2">
                      <input
                        type="file"
                        multiple
                        className="hidden"
                        onChange={(e) => {
                          if (e.target.files && e.target.files.length > 0) {
                            const newFiles = Array.from(e.target.files);
                            setUploadedFiles(newFiles);
                            handleAutofillFiles(newFiles);
                          }
                        }}
                      />
                      <UploadCloud className="w-7 h-7 text-[#C7431F]" />
                      <div className="text-xs font-bold text-[#1F1A17]">
                        Drop PDF, XLSX or DOCX files here or <span className="text-[#C7431F] underline">browse</span>
                      </div>
                      <span className="text-[11px] text-[#8A8176]">
                        {uploadedFiles.length > 0
                          ? `${uploadedFiles.length} file(s) selected`
                          : "Upload past marketing performance, customer segments, or case studies to auto-fill form"}
                      </span>
                    </label>

                    {uploadedFiles.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {uploadedFiles.map((f, i) => (
                          <div
                            key={i}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white border border-[#E1D7C8] text-xs font-medium text-[#1F1A17]"
                          >
                            <FileText className="w-3.5 h-3.5 text-[#C7431F]" />
                            <span className="truncate max-w-[200px]">{f.name}</span>
                            <button
                              type="button"
                              onClick={() => handleRemoveFile(i)}
                              className="text-[#8A8176] hover:text-[#A63030] cursor-pointer ml-1"
                              title="Remove file"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-4 flex items-center justify-end">
                    <button
                      onClick={handleStartCampaign}
                      disabled={isSubmitting}
                      className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white font-bold text-sm transition shadow-sm cursor-pointer disabled:opacity-50"
                    >
                      <Sparkles className="w-4 h-4" />
                      {isSubmitting ? "Dispatching to Agent..." : "Start Campaign Research"}
                    </button>
                  </div>
                </>
              ) : (
                /* Submitted brief card */
                <div className="space-y-6">
                  <div>
                    <span className="text-xs font-bold uppercase text-[#8A8176]">Active Campaign Brief</span>
                    <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                      {productName || "Campaign Brief"}
                    </h1>
                  </div>

                  <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
                    <span className="text-xs font-bold uppercase tracking-wider text-[#8A8176] block">
                      Target Goal & Value Proposition
                    </span>
                    <p className="text-base text-[#1F1A17] leading-relaxed">{briefText}</p>
                    <div className="pt-3 border-t border-[#EFE7DB] flex gap-4 text-xs text-[#6B625A]">
                      <span>Category: <strong>{category}</strong></span>
                      <span>Target: <strong>{targetGeo}</strong></span>
                    </div>
                  </div>

                  <button
                    onClick={() => setStage("intel")}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1F1A17] text-white font-bold text-xs cursor-pointer"
                  >
                    View Research & Rivals <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* STAGE 2: INTEL & RIVALS */}
          {stage === "intel" && (
            <div className="max-w-[1080px] mx-auto space-y-8 animate-fade-up">
              {isRunning ? (
                /* Real Live Telemetry Streaming State */
                <div className="max-w-2xl mx-auto pt-12 space-y-6">
                  <div className="text-center space-y-3">
                    <div className="w-16 h-16 rounded-2xl bg-[#FDF1EB] border border-[#F3CFC0] text-[#C7431F] flex items-center justify-center mx-auto animate-pulse">
                      <RefreshCw className="w-8 h-8 animate-spin" />
                    </div>
                    <h2 className="font-['Bricolage_Grotesque'] text-2xl font-bold">
                      Autonomous Research Agent Running...
                    </h2>
                    <p className="text-xs text-[#6B625A]">
                      Live multi-vector search & Scrape.do crawling active for <strong>{productName}</strong>.
                    </p>
                  </div>

                  {/* Real Telemetry Event Feed */}
                  <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-[#EFE7DB] pb-3">
                      <span className="text-xs font-bold uppercase tracking-wider text-[#1F1A17] flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-[#E2552F] animate-pulse" />
                        Live Event Log Stream
                      </span>
                      <span className="text-[11px] font-mono text-[#8A8176]">
                        {telemetryLogs.length} events
                      </span>
                    </div>

                    <div className="space-y-2 max-h-80 overflow-y-auto font-mono text-[11px]">
                      {telemetryLogs.length === 0 ? (
                        <p className="text-[#8A8176] italic">Connecting to orchestrator event bus...</p>
                      ) : (
                        telemetryLogs.map((log, i) => (
                          <div key={i} className="flex items-start gap-2.5 py-1 border-b border-zinc-100 last:border-0">
                            <span className="text-[#8A8176] shrink-0 text-[10px]">
                              {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : `${i + 1}`}
                            </span>
                            <span
                              className={`px-1.5 py-0.2 rounded text-[9px] font-bold shrink-0 ${
                                log.level === "INFO"
                                  ? "bg-[#FAF6EF] text-[#8F2F14]"
                                  : log.level === "ERROR"
                                  ? "bg-[#FDE6E4] text-[#A63030]"
                                  : "bg-[#FBEFD9] text-[#7A4506]"
                              }`}
                            >
                              {log.level}
                            </span>
                            <span className="text-[#1F1A17] break-words">{log.message}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                /* Done state with Real Competitors */
                <>
                  <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#E1D7C8] pb-4">
                    <div>
                      <span className="text-xs font-bold uppercase text-[#8A8176]">Intelligence</span>
                      <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                        Market Research & Competitor Matrix
                      </h1>
                      <p className="text-xs text-[#6B625A] mt-1">
                        Synthesized from Scrape.do DOM crawl and multi-vector web grounding.
                      </p>
                    </div>

                    {/* Sub-tabs */}
                    <div className="flex items-center gap-2 bg-[#F1EADF] p-1 rounded-xl">
                      <button
                        onClick={() => setIntelTab("research")}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                          intelTab === "research" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                        }`}
                      >
                        Competitors & Leaps ({rivalsList.length})
                      </button>
                      <button
                        onClick={() => setIntelTab("audience")}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                          intelTab === "audience" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                        }`}
                      >
                        Target Wedge
                      </button>
                    </div>
                  </div>

                  {intelTab === "research" ? (
                    <div className="space-y-8">
                      {/* Competitor Matrix Table */}
                      <div className="bg-white rounded-2xl border border-[#E1D7C8] overflow-hidden shadow-xs">
                        <div className="p-5 border-b border-[#EFE7DB] flex items-center justify-between">
                          <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                            Us vs Fastest-Growing Rivals
                          </h3>
                          <span className="text-xs text-[#8A8176] font-mono">
                            DQS Yield: {report?.dqs_score ? `${report.dqs_score}/100` : "Verified"}
                          </span>
                        </div>

                        {rivalsList.length === 0 ? (
                          <div className="p-8 text-center text-[#8A8176] text-xs">
                            No competitors found in this run. Launch a new run from Brief.
                          </div>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="w-full text-left text-xs">
                              <thead className="bg-[#FAF6EF] text-[#6B625A] uppercase font-bold text-[11px] border-b border-[#EFE7DB]">
                                <tr>
                                  <th className="p-4">Rival</th>
                                  <th className="p-4">Pricing</th>
                                  <th className="p-4">Rating</th>
                                  <th className="p-4">Core Claims</th>
                                  <th className="p-4">Sources Grounded</th>
                                  <th className="p-4 text-right">Action</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-[#EFE7DB]">
                                {rivalsList.map((r) => (
                                  <tr key={r.name} className="hover:bg-[#FDF9F3] transition">
                                    <td className="p-4 font-bold flex items-center gap-2.5">
                                      <span
                                        className="w-7 h-7 rounded-lg text-white flex items-center justify-center text-xs font-bold"
                                        style={{ backgroundColor: "#C7431F" }}
                                      >
                                        {r.initials}
                                      </span>
                                      <div>
                                        <span className="block font-bold">{r.name}</span>
                                        <span className="text-[10px] text-[#8A8176] font-normal">{r.host || "verified"}</span>
                                      </div>
                                    </td>
                                    <td className="p-4 font-mono">{r.priceLabel}</td>
                                    <td className="p-4">{r.rating ? `${r.rating} / 5` : "Unrated"}</td>
                                    <td className="p-4 text-[#4A4239] max-w-xs truncate">
                                      {r.claims.slice(0, 2).join("; ") || "Direct Category Competitor"}
                                    </td>
                                    <td className="p-4 text-[#C7431F] font-bold font-mono">
                                      {r.comp.sources?.length || 0} pages
                                    </td>
                                    <td className="p-4 text-right">
                                      <button
                                        onClick={() => {
                                          setSelectedRival(r);
                                          setRivalTab("ov");
                                        }}
                                        className="text-xs font-bold text-[#C7431F] hover:underline cursor-pointer"
                                      >
                                        View profile →
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>

                      {/* "Why each one grew" Leap Cards */}
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="font-['Bricolage_Grotesque'] text-xl font-bold">
                            Why each one grew (Breakout Leap Profiles)
                          </h3>
                          <span className="text-xs text-[#8A8176]">Client & Network Milestones</span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {rivalsList.map((r) => {
                            const leap = r.comp.leap_benchmark;
                            return (
                              <div
                                key={r.name}
                                className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs space-y-3"
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2 font-bold font-['Bricolage_Grotesque'] text-base">
                                    <span className="w-6 h-6 rounded bg-[#C7431F] text-white flex items-center justify-center text-[10px] font-bold">
                                      {r.initials}
                                    </span>
                                    <span>{r.name}</span>
                                  </div>
                                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-[#F1EADF] text-[#4A4239] font-bold">
                                    {leap?.current_scale || "Market Peer"}
                                  </span>
                                </div>

                                <p className="text-xs text-[#4A4239] leading-relaxed">
                                  {leap?.origin_story || r.comp.relevance_reason || "Active market player indexed by Scrape.do."}
                                </p>

                                {leap?.leap_catalysts && leap.leap_catalysts.length > 0 && (
                                  <div className="p-2.5 rounded-xl bg-[#FAF6EF] text-[11px] text-[#6B625A]">
                                    <span className="font-bold text-[#1F1A17] block mb-0.5">Key Catalyst:</span>
                                    {leap.leap_catalysts[0]}
                                  </div>
                                )}

                                <div className="pt-2 border-t border-[#EFE7DB] flex items-center justify-between text-xs">
                                  <span className="text-[#8A8176]">Pricing: {r.priceLabel}</span>
                                  <button
                                    onClick={() => {
                                      setSelectedRival(r);
                                      setRivalTab("hi");
                                    }}
                                    className="font-bold text-[#C7431F] hover:underline cursor-pointer"
                                  >
                                    Leap details →
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Real Market Trends */}
                      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
                        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                          Market Trends & Opportunities
                        </h3>
                        <ul className="space-y-2 text-xs text-[#4A4239] list-disc pl-4 leading-relaxed">
                          {report?.dashboard_insights?.highlight_opportunities && report.dashboard_insights.highlight_opportunities.length > 0 ? (
                            report.dashboard_insights.highlight_opportunities.map((opp, idx) => (
                              <li key={idx}>{opp}</li>
                            ))
                          ) : (
                            <>
                              <li>Usage-based models and self-serve onboarding are driving higher trial conversion in this category.</li>
                              <li>Enterprises prioritize security compliance and zero-downtime migrations over generic automation claims.</li>
                            </>
                          )}
                        </ul>
                      </div>
                    </div>
                  ) : (
                    /* Real Audience & Wedge Breakdown */
                    <div className="space-y-6">
                      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
                        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                          Merchant Strategic Wedge
                        </h3>
                        <p className="text-xs text-[#4A4239] leading-relaxed">
                          Targeting accounts seeking alternatives to {rivalsList[0]?.name || "legacy competitors"} based on validated pricing gaps and implementation overhead.
                        </p>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-xs">
                          <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                            <span className="text-[#8A8176] block text-[11px] uppercase font-bold">Core Persona</span>
                            <span className="font-bold block mt-1">VP Engineering & Technology Leaders</span>
                          </div>
                          <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                            <span className="text-[#8A8176] block text-[11px] uppercase font-bold">Category Friction</span>
                            <span className="font-bold block mt-1">Complex Enterprise Contracts</span>
                          </div>
                          <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                            <span className="text-[#8A8176] block text-[11px] uppercase font-bold">Winning Hook</span>
                            <span className="font-bold block mt-1">{briefText.slice(0, 40) || "Fast Rollout"}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Sticky Bottom Bar */}
                  <div className="sticky bottom-4 bg-[#1F1A17] text-white p-4 rounded-2xl shadow-xl flex items-center justify-between gap-4">
                    <span className="text-xs font-medium">
                      Research verified. {rivalsList.length} competitors indexed.
                    </span>
                    <button
                      onClick={handleToStrategy}
                      className="px-5 py-2 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] font-bold text-xs transition cursor-pointer"
                    >
                      Continue to Strategy →
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* STAGE 3: STRATEGY (AUTONOMOUS DERIVED BRIEF & APPROVAL) */}
          {stage === "strategy" && (
            <div className="max-w-[880px] mx-auto space-y-8 animate-fade-up">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#E1D7C8] pb-4">
                <div>
                  <span className="text-xs font-bold uppercase text-[#8A8176]">Campaign Strategy Engine</span>
                  <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                    Positioning & Phased Strategy Brief
                  </h1>
                  <p className="text-xs text-[#6B625A] mt-2">
                    Autonomous Loops 1–3: KPI Decomposition • Channel Fit Matrix • 90-Day Execution Calendar
                  </p>
                </div>
                <div>
                  {stratApproved || strategyBrief?.approval_status === "APPROVED_AND_DISPATCHED" ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#E4F2EA] text-[#256545] border border-[#256545]/20">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Strategy Approved & Dispatched
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#FDF1EB] text-[#C7431F] border border-[#C7431F]/20">
                      <AlertCircle className="w-3.5 h-3.5" /> Pending Founder Approval
                    </span>
                  )}
                </div>
              </div>

              {/* Core Positioning Pillar */}
              <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
                <span className="text-xs font-bold uppercase tracking-wider text-[#C7431F]">
                  Core Positioning Pillar
                </span>
                <h2 className="font-['Bricolage_Grotesque'] text-xl font-bold">
                  {strategyBrief?.primary_positioning_pillar ||
                    report?.dashboard_insights?.executive_summary?.slice(0, 90) ||
                    `Displace ${rivalsList[0]?.name || "incumbent competitors"} with guaranteed deployment velocity`}
                </h2>
                <p className="text-xs text-[#4A4239] leading-relaxed">
                  {strategyBrief?.executive_summary ||
                    report?.dashboard_insights?.executive_summary ||
                    `Campaign strategy engineered to position ${productName || "our solution"} around rapid deployment, predictable unit economics, and zero migration downtime.`}
                </p>
              </div>

              {/* Loop 1: Target KPI Metrics */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                    Target KPI Benchmarks
                  </h3>
                  <span className="text-[11px] text-[#8A8176]">Loop 1: Objective Decomposition</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {(strategyBrief?.target_metrics || [
                    { name: "Target CPA / CPQO", target_value: "< $1,200", baseline: "Market $1,800+", measurement_window: "90 days" },
                    { name: "Sales Velocity", target_value: "< 14 days", baseline: "Market 45+ days", measurement_window: "90 days" },
                    { name: "Target Pipeline", target_value: "$250k+ added", baseline: "$0 baseline", measurement_window: "60 days" },
                    { name: "Spend Payback", target_value: "< 3.5 months", baseline: "Market 7 months", measurement_window: "180 days" },
                  ]).map((m, idx) => (
                    <div key={idx} className="bg-white rounded-xl border border-[#E1D7C8] p-4 shadow-xs space-y-1.5">
                      <span className="text-[10px] font-bold uppercase text-[#8A8176] block truncate">{m.name}</span>
                      <div className="text-base font-extrabold text-[#1F1A17]">{m.target_value}</div>
                      <div className="text-[11px] text-[#6B625A] flex justify-between pt-1 border-t border-[#F1EADF]">
                        <span>Baseline: {m.baseline}</span>
                        <span className="text-[#8A8176]">{m.measurement_window}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Loop 2: Multi-Channel Allocation Matrix */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                    Optimal Channel Priority Matrix
                  </h3>
                  <span className="text-[11px] text-[#8A8176]">Loop 2: Category Unit Economics</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {(strategyBrief?.channel_matrix || [
                    { channel: "linkedin", budget_percentage: 40, recommended_spend_usd: 4000, rationale: "Primary B2B decision-maker dwell channel", projected_roi: "3.4x Pipeline" },
                    { channel: "email", budget_percentage: 25, recommended_spend_usd: 2500, rationale: "Direct outreach to switcher accounts", projected_roi: "4.8x Pipeline" },
                    { channel: "retarget", budget_percentage: 20, recommended_spend_usd: 2000, rationale: "Comparison visitors and price page drops", projected_roi: "3.1x Conversion" },
                    { channel: "search", budget_percentage: 15, recommended_spend_usd: 1500, rationale: "High-intent alternative queries", projected_roi: "2.9x Conversion" },
                  ]).map((ch, idx) => (
                    <div key={idx} className="bg-white rounded-xl border border-[#E1D7C8] p-4 shadow-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs uppercase text-[#1F1A17]">{ch.channel}</span>
                        <span className="font-bold text-xs px-2 py-0.5 rounded bg-[#FDF1EB] text-[#C7431F]">
                          {ch.budget_percentage}%
                        </span>
                      </div>
                      <div className="w-full bg-[#F1EADF] h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-[#C7431F] h-full rounded-full transition-all duration-500"
                          style={{ width: `${ch.budget_percentage}%` }}
                        />
                      </div>
                      {ch.recommended_spend_usd && (
                        <div className="text-[11px] font-semibold text-[#1F1A17]">
                          Est. Spend: ${ch.recommended_spend_usd.toLocaleString()}
                        </div>
                      )}
                      <p className="text-[11px] text-[#6B625A] line-clamp-2">{ch.rationale}</p>
                      {ch.projected_roi && (
                        <div className="text-[10px] font-bold text-[#256545] pt-1 border-t border-[#F1EADF]">
                          Expected: {ch.projected_roi}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Loop 2: Strategic Angles Grid */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                    Strategic Angles & Positioning Wedges
                  </h3>
                  <span className="text-[11px] text-[#8A8176]">Loop 2: Competitor Vulnerability Gaps</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {(strategyBrief?.strategic_angles || [
                    {
                      angle_title: "Angle 1: Speed to Operational Impact",
                      target_wedge: "Leaders evaluating replacements",
                      competitor_weakness: "Protracted rollout and legacy delay",
                      hook: `Why fast-moving teams choose ${productName || "us"} over ${rivalsList[0]?.name || "incumbents"}`,
                      messaging_pillar: "Guaranteed deployment velocity without legacy consulting friction.",
                    },
                    {
                      angle_title: "Angle 2: Zero Migration Friction",
                      target_wedge: "Enterprise teams stalled by overhead",
                      competitor_weakness: "Opaque pricing and lock-in contracts",
                      hook: "Deploy modern solutions without the 6-month consulting tax",
                      messaging_pillar: "Milestone-driven delivery with guaranteed continuity.",
                    },
                    {
                      angle_title: "Angle 3: Modern Category Standard",
                      target_wedge: "Procurement decision makers",
                      competitor_weakness: "Sluggish response times & legacy tech",
                      hook: "The modern category alternative built for 2026 demands",
                      messaging_pillar: "Engineered specifically to outpace incumbent legacy constraints.",
                    },
                  ]).map((ang, i) => (
                    <div key={i} className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs space-y-2.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[#FDF1EB] text-[#C7431F] inline-block">
                        {ang.angle_title}
                      </span>
                      <h4 className="font-bold text-sm text-[#1F1A17]">{ang.hook}</h4>
                      <div className="text-[11px] text-[#8A8176] space-y-1">
                        <div><strong className="text-[#6B625A]">Wedge:</strong> {ang.target_wedge}</div>
                        <div><strong className="text-[#6B625A]">Attack:</strong> {ang.competitor_weakness}</div>
                      </div>
                      <p className="text-xs text-[#4A4239] pt-2 border-t border-[#F1EADF]">{ang.messaging_pillar}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Loop 3: Phased Execution Roadmap */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                    90-Day Phased Execution Calendar
                  </h3>
                  <span className="text-[11px] text-[#8A8176]">Loop 3: Schedule & Milestone Routing</span>
                </div>
                <div className="space-y-3">
                  {(strategyBrief?.execution_calendar || [
                    {
                      phase_name: "Phase 1: Foundation & Positioning Validation",
                      weeks: "Weeks 1 - 3",
                      focus: "Deploy landing page teardowns and configure multi-channel tracking attribution.",
                      deliverables: ["Comparative landing pages", "Email copy sequences QA", "Tracking & UTM audit"],
                    },
                    {
                      phase_name: "Phase 2: Alpha Wedge Ingress",
                      weeks: "Weeks 4 - 8",
                      focus: "Launch LinkedIn sponsored outreach and high-intent search campaigns against switcher queries.",
                      deliverables: ["LinkedIn & Search flight live", "Creative hook optimization", "First pipeline cohort"],
                    },
                    {
                      phase_name: "Phase 3: Scale & Retargeting Flight",
                      weeks: "Weeks 9 - 12",
                      focus: "Reallocate spend to winning angles and activate multi-touch retargeting.",
                      deliverables: ["Multi-touch retargeting live", "90-day ROI audit", "Handoff to automated monitoring"],
                    },
                  ]).map((phase, pIdx) => (
                    <div key={pIdx} className="bg-white rounded-xl border border-[#E1D7C8] p-4 shadow-xs flex flex-col sm:flex-row gap-4 items-start">
                      <div className="min-w-[140px]">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[#E4F2EA] text-[#256545] inline-block mb-1">
                          {phase.weeks}
                        </span>
                        <h4 className="font-bold text-xs text-[#1F1A17]">{phase.phase_name}</h4>
                      </div>
                      <div className="flex-1 space-y-2">
                        <p className="text-xs text-[#4A4239]">{phase.focus}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {phase.deliverables.map((deliv, dIdx) => (
                            <span key={dIdx} className="text-[10px] bg-[#F7F4EE] px-2 py-0.5 rounded text-[#6B625A]">
                              ✓ {deliv}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Loop 3: Budget Guardrails & Assumptions */}
              {strategyBrief?.budget_assumptions && strategyBrief.budget_assumptions.length > 0 && (
                <div className="bg-[#FAF7F2] rounded-xl border border-[#E1D7C8] p-4 space-y-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#8A8176]">
                    Budget Guardrails & Assumptions
                  </span>
                  <ul className="text-xs text-[#6B625A] space-y-1">
                    {strategyBrief.budget_assumptions.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-[#C7431F] font-bold">•</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action Bottom Bar */}
              <div className="sticky bottom-4 bg-[#1F1A17] text-white p-4 rounded-2xl shadow-xl flex items-center justify-between gap-4">
                <button
                  onClick={handleRequestChanges}
                  className="px-4 py-2 rounded-xl border border-zinc-700 hover:bg-zinc-800 text-xs font-bold transition cursor-pointer"
                >
                  Request changes
                </button>
                <button
                  onClick={handleApproveStrategy}
                  className="px-5 py-2 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] font-bold text-xs transition cursor-pointer"
                >
                  Approve strategy → Generate content
                </button>
              </div>
            </div>
          )}

          {/* STAGE 4: CONTENT CREATIVE STUDIO */}
          {stage === "content" && (
            <div className="max-w-[1080px] mx-auto space-y-8 animate-fade-up">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#E1D7C8] pb-4">
                <div>
                  <span className="text-xs font-bold uppercase text-[#8A8176]">Creative Generation</span>
                  <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                    Campaign Content Studio
                  </h1>
                </div>

                {/* Channels selector */}
                <div className="flex items-center gap-1.5 bg-[#F1EADF] p-1 rounded-xl">
                  <button
                    onClick={() => {
                      setContentTab("email");
                      setAssetSel("e1");
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      contentTab === "email" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                    }`}
                  >
                    <Mail className="w-3.5 h-3.5" /> Email
                  </button>
                  <button
                    onClick={() => {
                      setContentTab("linkedin");
                      setAssetSel("l1");
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      contentTab === "linkedin" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                    }`}
                  >
                    <span className="font-bold text-[11px]">in</span> LinkedIn
                  </button>
                  <button
                    onClick={() => {
                      setContentTab("retarget");
                      setAssetSel("r1");
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      contentTab === "retarget" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                    }`}
                  >
                    <Megaphone className="w-3.5 h-3.5" /> Retargeting
                  </button>
                  <button
                    onClick={() => {
                      setContentTab("ads");
                      setAssetSel("a1");
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                      contentTab === "ads" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                    }`}
                  >
                    Google Ads
                  </button>
                </div>
              </div>

              {/* Split Layout: Asset list + Live Preview */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Left Column: Asset list */}
                <div className="space-y-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#8A8176]">
                    {contentTab.toUpperCase()} Assets
                  </span>

                  {contentTab === "email" && (
                    <>
                      <button
                        onClick={() => setAssetSel("e1")}
                        className={`w-full text-left p-3.5 rounded-xl border transition cursor-pointer ${
                          assetSel === "e1"
                            ? "bg-white border-[#E1D7C8] shadow-sm ring-1 ring-[#C7431F]"
                            : "bg-white/60 border-transparent hover:bg-white"
                        }`}
                      >
                        <span className="font-bold text-xs block">Email 1: Contrast Hook</span>
                        <span className="text-[11px] text-[#8A8176] truncate block mt-0.5">
                          {dynamicCopy.e1.subject}
                        </span>
                      </button>

                      <button
                        onClick={() => setAssetSel("e2")}
                        className={`w-full text-left p-3.5 rounded-xl border transition cursor-pointer ${
                          assetSel === "e2"
                            ? "bg-white border-[#E1D7C8] shadow-sm ring-1 ring-[#C7431F]"
                            : "bg-white/60 border-transparent hover:bg-white"
                        }`}
                      >
                        <span className="font-bold text-xs block">Email 2: Downtime Guarantee</span>
                        <span className="text-[11px] text-[#8A8176] truncate block mt-0.5">
                          {dynamicCopy.e2.subject}
                        </span>
                      </button>
                    </>
                  )}

                  {contentTab === "linkedin" && (
                    <button
                      onClick={() => setAssetSel("l1")}
                      className="w-full text-left p-3.5 rounded-xl bg-white border border-[#E1D7C8] shadow-sm ring-1 ring-[#C7431F] cursor-pointer"
                    >
                      <span className="font-bold text-xs block">Post 1: Thought Leadership</span>
                      <span className="text-[11px] text-[#8A8176] truncate block mt-0.5">
                        Migrating off {rivalsList[0]?.name || "competitors"}...
                      </span>
                    </button>
                  )}

                  {contentTab === "retarget" && (
                    <button
                      onClick={() => setAssetSel("r1")}
                      className="w-full text-left p-3.5 rounded-xl bg-white border border-[#E1D7C8] shadow-sm ring-1 ring-[#C7431F] cursor-pointer"
                    >
                      <span className="font-bold text-xs block">Ad Variant 1: Direct Comparison</span>
                      <span className="text-[11px] text-[#8A8176] truncate block mt-0.5">
                        Evaluating {rivalsList[0]?.name || "alternatives"}...
                      </span>
                    </button>
                  )}

                  {contentTab === "ads" && (
                    <button
                      onClick={() => setAssetSel("a1")}
                      className="w-full text-left p-3.5 rounded-xl bg-white border border-[#E1D7C8] shadow-sm ring-1 ring-[#C7431F] cursor-pointer"
                    >
                      <span className="font-bold text-xs block">Search Ad: Competitor Alternative</span>
                      <span className="text-[11px] text-[#8A8176] truncate block mt-0.5">
                        {productName} vs {rivalsList[0]?.name || "competitor"}...
                      </span>
                    </button>
                  )}

                  {/* Approval Switch */}
                  <div className="pt-4">
                    <label className="flex items-center gap-2.5 p-3 rounded-xl bg-white border border-[#E1D7C8] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={approved[contentTab]}
                        onChange={(e) =>
                          setApproved((prev) => ({ ...prev, [contentTab]: e.target.checked }))
                        }
                        className="w-4 h-4 rounded text-[#C7431F] focus:ring-[#C7431F]"
                      />
                      <span className="text-xs font-bold text-[#1F1A17]">
                        Approve {contentTab} for launch
                      </span>
                    </label>
                  </div>
                </div>

                {/* Right Column: Live Asset Preview & Editor */}
                <div className="md:col-span-2 space-y-4">
                  {contentTab === "email" ? (
                    <div className="bg-white rounded-2xl border border-[#E1D7C8] overflow-hidden shadow-xs">
                      <div className="p-4 bg-[#FBF8F2] border-b border-[#EFE7DB] text-xs text-[#6B625A] flex items-center justify-between">
                        <span>Email Sequence Preview</span>
                        <span>From: team@{productName ? productName.toLowerCase().replace(/[^a-z0-9]/g, "") + ".com" : "company.com"}</span>
                      </div>
                      <div className="p-6 space-y-4">
                        <div>
                          <label className="text-[11px] font-bold uppercase text-[#8A8176] block mb-1">
                            Subject
                          </label>
                          <input
                            type="text"
                            defaultValue={dynamicCopy[assetSel as keyof typeof dynamicCopy]?.subject || ""}
                            className="w-full p-2.5 rounded-xl border border-[#E1D7C8] text-sm font-semibold"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-bold uppercase text-[#8A8176] block mb-1">
                            Body
                          </label>
                          <textarea
                            defaultValue={dynamicCopy[assetSel as keyof typeof dynamicCopy]?.body || ""}
                            rows={8}
                            className="w-full p-3 rounded-xl border border-[#E1D7C8] text-xs leading-relaxed"
                          />
                        </div>
                      </div>
                    </div>
                  ) : contentTab === "linkedin" ? (
                    <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
                      <div className="flex items-center gap-3">
                        <span className="w-10 h-10 rounded-full bg-[#1F1A17] text-white flex items-center justify-center font-bold text-xs">
                          {productName ? productName.slice(0, 2).toUpperCase() : "CO"}
                        </span>
                        <div>
                          <span className="font-bold text-sm block">{productName || "Your Company"}</span>
                          <span className="text-[11px] text-[#8A8176]">Promoted • Autonomous Campaign</span>
                        </div>
                      </div>
                      <textarea
                        defaultValue={dynamicCopy.l1.body}
                        rows={6}
                        className="w-full p-3 rounded-xl border border-[#E1D7C8] text-xs leading-relaxed"
                      />
                    </div>
                  ) : (
                    <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
                      <span className="text-[11px] font-bold text-[#8A8176]">Ad Copy Editor</span>
                      <textarea
                        defaultValue={dynamicCopy.a1.body}
                        rows={6}
                        className="w-full p-3 rounded-xl border border-[#E1D7C8] text-xs leading-relaxed"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Sticky Bottom Bar */}
              <div className="sticky bottom-4 bg-[#1F1A17] text-white p-4 rounded-2xl shadow-xl flex items-center justify-between gap-4">
                <span className="text-xs font-medium">
                  Review creative variations across channels.
                </span>
                <button
                  onClick={handleApproveContent}
                  className="px-5 py-2 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] font-bold text-xs transition cursor-pointer"
                >
                  Proceed to Schedule →
                </button>
              </div>
            </div>
          )}

          {/* STAGE 5: SCHEDULE */}
          {stage === "schedule" && (
            <div className="max-w-[760px] mx-auto space-y-8 animate-fade-up">
              <div>
                <span className="text-xs font-bold uppercase text-[#8A8176]">Launch Staging</span>
                <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                  Schedule or Publish Campaign
                </h1>
                <p className="text-xs text-[#6B625A] mt-2">
                  Verify dispatch dates, audience routing and channel connections for {productName}.
                </p>
              </div>

              <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
                <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Campaign Readiness</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div className="p-4 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                    <span className="text-[#8A8176] block text-[11px] uppercase font-bold">Rivals Indexed</span>
                    <span className="font-['Bricolage_Grotesque'] text-xl font-bold block mt-1">
                      {rivalsList.length} Competitors
                    </span>
                    <span className="text-[11px] text-[#6B625A]">Scrape.do Grounded</span>
                  </div>
                  <div className="p-4 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                    <span className="text-[#8A8176] block text-[11px] uppercase font-bold">Channels Active</span>
                    <span className="font-['Bricolage_Grotesque'] text-xl font-bold block mt-1">4 Channels</span>
                    <span className="text-[11px] text-[#6B625A]">Email, LinkedIn, Meta, Google</span>
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-[#E1D7C8] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Calendar className="w-5 h-5 text-[#C7431F]" />
                    <div>
                      <span className="text-xs font-bold block">First Send Window</span>
                      <span className="text-[11px] text-[#8A8176]">Immediate or scheduled slot</span>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-[#3F9068]">Ready</span>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4">
                <button
                  onClick={handleScheduleCampaign}
                  className="px-5 py-2.5 rounded-xl border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-xs font-bold transition cursor-pointer"
                >
                  Schedule Campaign
                </button>
                <button
                  onClick={handlePublishNow}
                  className="px-6 py-2.5 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white text-xs font-bold transition shadow-sm cursor-pointer"
                >
                  Publish Now
                </button>
              </div>
            </div>
          )}

          {/* STAGE 6: LIVE PERFORMANCE COCKPIT */}
          {stage === "perf" && (
            <div className="max-w-[1080px] mx-auto space-y-8 animate-fade-up">
              <div className="flex items-center justify-between border-b border-[#E1D7C8] pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#3F9068] animate-pulse" />
                    <span className="text-xs font-bold uppercase text-[#3F9068]">Active & Monitoring</span>
                  </div>
                  <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold mt-1">
                    {productName} Campaign Cockpit
                  </h1>
                </div>
                <button
                  onClick={() => pushAgent("Live telemetry refreshed. All ad angles performing within bounds.")}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E1D7C8] bg-white text-xs font-semibold hover:bg-[#FDF9F3] cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh
                </button>
              </div>

              {/* Real-time AI Insight Toast */}
              {insight === 1 && (
                <div className="bg-[#FDF1EB] border border-[#F3CFC0] rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4 shadow-sm animate-fade-in">
                  <div className="flex items-start gap-3 max-w-2xl">
                    <Sparkles className="w-5 h-5 text-[#C7431F] shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-xs text-[#8F2F14] block">
                        Live Agent Recommendation
                      </span>
                      <p className="text-xs text-[#1F1A17] mt-1 leading-relaxed">
                        Competitor {rivalsList[0]?.name || "peer"} shows heightened activity. Shift 10% of retargeting budget toward high-converting email angle.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setInsight(0)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold text-[#8A8176] hover:bg-white/50 cursor-pointer"
                    >
                      Dismiss
                    </button>
                    <button
                      onClick={handleApplyInsight}
                      className="px-4 py-1.5 rounded-lg bg-[#C7431F] hover:bg-[#A9381A] text-white text-xs font-bold transition shadow-xs cursor-pointer"
                    >
                      Apply Recommendation
                    </button>
                  </div>
                </div>
              )}

              {insight === 2 && (
                <div className="p-4 rounded-xl bg-[#E4F2EA] border border-[#C5E3D2] text-[#256545] text-xs font-semibold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  Budget reallocation applied by agent.
                </div>
              )}

              {/* KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs">
                  <span className="text-[11px] font-bold uppercase text-[#8A8176]">Indexed Rivals</span>
                  <span className="font-['Bricolage_Grotesque'] text-3xl font-extrabold block mt-2">
                    {rivalsList.length}
                  </span>
                  <span className="text-[11px] text-[#3F9068] font-bold">100% Grounded</span>
                </div>

                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs">
                  <span className="text-[11px] font-bold uppercase text-[#8A8176]">DQS Quality</span>
                  <span className="font-['Bricolage_Grotesque'] text-3xl font-extrabold block mt-2">
                    {report?.dqs_score || 92}%
                  </span>
                  <span className="text-[11px] text-[#3F9068] font-bold">Validated</span>
                </div>

                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs">
                  <span className="text-[11px] font-bold uppercase text-[#8A8176]">Active Angles</span>
                  <span className="font-['Bricolage_Grotesque'] text-3xl font-extrabold block mt-2">
                    {angles.length || 3}
                  </span>
                  <span className="text-[11px] text-[#3F9068] font-bold">Multi-channel</span>
                </div>

                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs">
                  <span className="text-[11px] font-bold uppercase text-[#8A8176]">Status</span>
                  <span className="font-['Bricolage_Grotesque'] text-3xl font-extrabold block mt-2">
                    Live
                  </span>
                  <span className="text-[11px] text-[#3F9068] font-bold">Monitoring Active</span>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ─── SLIDE-OVER PERSISTENT AGENT CHAT PANEL ─── */}
      {agentOpen && (
        <div className="fixed right-6 bottom-6 z-40 w-[420px] max-w-[calc(100vw-32px)] h-[640px] max-h-[calc(100vh-48px)] flex flex-col bg-white border border-[#E1D7C8] rounded-2xl shadow-2xl overflow-hidden animate-slide-in-right">
          {/* Header */}
          <div className="p-4 border-b border-[#EFE7DB] flex items-center justify-between bg-[#FAF6EF]">
            <div className="flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-[#C7431F] text-white flex items-center justify-center font-bold">
                <Bot className="w-4 h-4" />
              </span>
              <div>
                <span className="font-bold text-xs block text-[#1F1A17]">Marketing Research Agent</span>
                <span className="text-[10px] text-[#6B625A]">
                  {activeJobId ? `Job: ${activeJobId.slice(0, 10)}...` : "Active"}
                </span>
              </div>
            </div>
            <button
              onClick={() => setAgentOpen(false)}
              className="p-1.5 rounded-lg hover:bg-[#EFE7DB] text-[#8A8176] cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Status Indicator */}
          <div className="mx-4 mt-3 p-2.5 rounded-xl bg-[#F6F1E8] text-[#4A4239] text-xs font-semibold flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isRunning ? "bg-[#E2552F] animate-pulse" : "bg-[#3F9068]"}`} />
              <span>{isRunning ? "Agent actively researching..." : "Connected to orchestrator"}</span>
            </div>
            {isAgentTyping && <span className="text-[10px] text-[#C7431F] font-bold">Thinking...</span>}
          </div>

          {/* Message Thread */}
          <div className="flex-1 p-4 overflow-y-auto space-y-3 min-h-0 text-xs">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`p-3 rounded-2xl max-w-[90%] leading-relaxed ${
                  m.who === "user"
                    ? "bg-[#1F1A17] text-white ml-auto rounded-br-xs"
                    : "bg-[#F6F1E8] text-[#1F1A17] rounded-bl-xs"
                }`}
              >
                {m.text}
              </div>
            ))}
          </div>

          {/* Composer */}
          <div className="p-3 border-t border-[#EFE7DB] flex items-center gap-2 bg-[#FAF6EF]">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSendMessage();
              }}
              placeholder="Ask the research agent anything..."
              className="flex-1 px-3 py-2 rounded-xl border border-[#E1D7C8] bg-white text-xs focus:outline-none focus:border-[#C7431F]"
            />
            <button
              onClick={handleSendMessage}
              disabled={isAgentTyping}
              className="p-2 rounded-xl bg-[#C7431F] text-white hover:bg-[#A9381A] transition shrink-0 cursor-pointer disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* ─── RIVAL DETAILS DRAWER MODAL (REAL DATA) ─── */}
      {selectedRival && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            onClick={() => setSelectedRival(null)}
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition"
          />

          <div className="relative z-10 w-full max-w-[620px] bg-white h-full shadow-2xl flex flex-col overflow-hidden animate-slide-in-right">
            {/* Header */}
            <div className="p-6 border-b border-[#E1D7C8] flex items-start justify-between bg-[#FAF6EF]">
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-xl bg-[#C7431F] text-white flex items-center justify-center font-bold text-sm shadow-xs">
                  {selectedRival.initials}
                </span>
                <div>
                  <h2 className="font-['Bricolage_Grotesque'] text-2xl font-extrabold">
                    {selectedRival.name}
                  </h2>
                  <span className="text-xs text-[#8A8176]">
                    {selectedRival.host || selectedRival.subtitle || "Competitor Profile"}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedRival(null)}
                className="p-2 rounded-xl border border-[#E1D7C8] hover:bg-white text-[#8A8176] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-4 px-6 border-b border-[#EFE7DB] text-xs font-bold">
              <button
                onClick={() => setRivalTab("ov")}
                className={`py-3 border-b-2 transition cursor-pointer ${
                  rivalTab === "ov" ? "border-[#C7431F] text-[#C7431F]" : "border-transparent text-[#8A8176]"
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setRivalTab("mk")}
                className={`py-3 border-b-2 transition cursor-pointer ${
                  rivalTab === "mk" ? "border-[#C7431F] text-[#C7431F]" : "border-transparent text-[#8A8176]"
                }`}
              >
                Marketing Teardown
              </button>
              <button
                onClick={() => setRivalTab("hi")}
                className={`py-3 border-b-2 transition cursor-pointer ${
                  rivalTab === "hi" ? "border-[#C7431F] text-[#C7431F]" : "border-transparent text-[#8A8176]"
                }`}
              >
                Growth & Leap Timeline
              </button>
              <button
                onClick={() => setRivalTab("cu")}
                className={`py-3 border-b-2 transition cursor-pointer ${
                  rivalTab === "cu" ? "border-[#C7431F] text-[#C7431F]" : "border-transparent text-[#8A8176]"
                }`}
              >
                Praise & Complaints
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 p-6 overflow-y-auto space-y-6 text-xs bg-[#FAF6EF]">
              {rivalTab === "ov" && (
                <>
                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                    <span className="font-bold uppercase text-[11px] text-[#8A8176]">Relevance & Positioning</span>
                    <p className="text-xs text-[#4A4239] leading-relaxed">
                      {selectedRival.comp.relevance_reason || selectedRival.comp.product_name}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-white p-4 rounded-xl border border-[#E1D7C8]">
                      <span className="text-[10px] uppercase font-bold text-[#8A8176]">Pricing Model</span>
                      <span className="font-bold text-sm block mt-1">{selectedRival.priceLabel}</span>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-[#E1D7C8]">
                      <span className="text-[10px] uppercase font-bold text-[#8A8176]">Rating & Reviews</span>
                      <span className="font-bold text-sm block mt-1">
                        {selectedRival.rating ? `${selectedRival.rating} / 5` : "Unrated"}
                      </span>
                    </div>
                  </div>

                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                    <span className="font-bold uppercase text-[11px] text-[#8A8176]">
                      Grounded Sources ({selectedRival.comp.sources?.length || 0})
                    </span>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {(selectedRival.comp.sources || []).map((url, idx) => (
                        <a
                          key={idx}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-between p-2 rounded-lg bg-[#FAF6EF] text-[#C7431F] hover:underline text-[11px] truncate"
                        >
                          <span className="truncate">{url}</span>
                          <ExternalLink className="w-3 h-3 ml-2 shrink-0" />
                        </a>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {rivalTab === "mk" && (
                <div className="space-y-4">
                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                    <span className="font-bold uppercase text-[11px] text-[#8A8176]">Core Claims & Value Props</span>
                    <ul className="list-disc pl-4 space-y-1 text-xs text-[#4A4239]">
                      {selectedRival.claims.length > 0 ? (
                        selectedRival.claims.map((c, i) => <li key={i}>{c}</li>)
                      ) : (
                        <li className="italic text-[#8A8176]">No explicit marketing claims parsed.</li>
                      )}
                    </ul>
                  </div>

                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                    <span className="font-bold uppercase text-[11px] text-[#8A8176]">Ad Hooks & Meta Ads</span>
                    <ul className="list-disc pl-4 space-y-1 text-xs text-[#4A4239]">
                      {selectedRival.ads.length > 0 ? (
                        selectedRival.ads.map((ad, i) => <li key={i}>{ad}</li>)
                      ) : (
                        <li className="italic text-[#8A8176]">No active digital ad hooks detected.</li>
                      )}
                    </ul>
                  </div>
                </div>
              )}

              {rivalTab === "hi" && (
                <div className="space-y-4">
                  {selectedRival.comp.leap_benchmark ? (
                    <div className="space-y-3">
                      {/* Scale & Origins */}
                      <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="font-bold uppercase text-[11px] text-[#C7431F] flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5" />
                            Breakout Trajectory & Scale
                          </span>
                          {selectedRival.comp.leap_benchmark.current_scale && (
                            <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-[#FAF6EF] text-[#8F2F14] border border-[#EFE7DB]">
                              {selectedRival.comp.leap_benchmark.current_scale}
                            </span>
                          )}
                        </div>
                        {selectedRival.comp.leap_benchmark.origin_story && (
                          <div>
                            <span className="font-bold text-[#1F1A17] block text-xs mb-1">Origin Story:</span>
                            <p className="text-xs text-[#4A4239] leading-relaxed">
                              {selectedRival.comp.leap_benchmark.origin_story}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Flagship Enterprise Clients */}
                      {selectedRival.comp.leap_benchmark.flagship_clients &&
                        selectedRival.comp.leap_benchmark.flagship_clients.length > 0 && (
                          <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                            <span className="font-bold uppercase text-[11px] text-[#8A8176] block">
                              Marquee Clients & Logos ({selectedRival.comp.leap_benchmark.flagship_clients.length})
                            </span>
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {selectedRival.comp.leap_benchmark.flagship_clients.map((client, idx) => (
                                <span
                                  key={idx}
                                  className="px-2.5 py-1 rounded-lg bg-[#FAF6EF] border border-[#E1D7C8] text-xs font-semibold text-[#1F1A17]"
                                >
                                  {client}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                      {/* Scale Catalysts */}
                      <div className="p-4 rounded-2xl bg-[#FDF1EB] border border-[#F5DDD4] text-xs space-y-1">
                        <span className="font-bold text-[#8F2F14] block">Scale Catalysts & Inflection Points:</span>
                        {selectedRival.comp.leap_benchmark.leap_catalysts &&
                        selectedRival.comp.leap_benchmark.leap_catalysts.length > 0 ? (
                          <ul className="list-disc pl-4 space-y-1 text-[#1F1A17] mt-1">
                            {selectedRival.comp.leap_benchmark.leap_catalysts.map((cat, i) => (
                              <li key={i}>{cat}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-[#1F1A17] mt-1">Organic customer scale and category expansion.</p>
                        )}
                      </div>

                      {/* Strategic Network Deals & Partnerships */}
                      {selectedRival.comp.leap_benchmark.network_and_deals &&
                        selectedRival.comp.leap_benchmark.network_and_deals.length > 0 && (
                          <div className="p-4 rounded-2xl bg-white border border-[#E1D7C8] text-xs space-y-1">
                            <span className="font-bold text-[#1F1A17] block">Network & Strategic Deals:</span>
                            <ul className="list-disc pl-4 space-y-1 text-[#4A4239] mt-1">
                              {selectedRival.comp.leap_benchmark.network_and_deals.map((deal, i) => (
                                <li key={i}>{deal}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                      {/* Pricing Power Expansion */}
                      {selectedRival.comp.leap_benchmark.pricing_power_leap && (
                        <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-1 text-xs">
                          <span className="font-bold text-[#1F1A17] block">Pricing Power Expansion:</span>
                          <p className="text-[#4A4239] leading-relaxed">
                            {selectedRival.comp.leap_benchmark.pricing_power_leap}
                          </p>
                        </div>
                      )}

                      {/* Merchant Emulation Playbook */}
                      {selectedRival.comp.leap_benchmark.merchant_takeaway_playbook &&
                        selectedRival.comp.leap_benchmark.merchant_takeaway_playbook.length > 0 && (
                          <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                            <span className="font-bold uppercase text-[11px] text-[#256545] block">
                              How You Can Emulate This Leap (Playbook)
                            </span>
                            <div className="space-y-2">
                              {selectedRival.comp.leap_benchmark.merchant_takeaway_playbook.map((play, idx) => (
                                <div
                                  key={idx}
                                  className="p-3 rounded-xl bg-[#F6FBF8] border border-[#D5EFE2] text-xs text-[#1F1A17] flex items-start gap-2.5"
                                >
                                  <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#E4F2EA] text-[#256545] font-bold text-[10px] shrink-0 mt-0.5">
                                    {idx + 1}
                                  </span>
                                  <p className="leading-relaxed">{play}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                    </div>
                  ) : null}

                  {/* Growth Milestones & Timeline */}
                  {selectedRival.comp.milestones && selectedRival.comp.milestones.length > 0 && (
                    <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                      <span className="font-bold uppercase text-[11px] text-[#8A8176] block">
                        Growth Milestones & Timeline
                      </span>
                      <div className="space-y-2 border-l-2 border-[#E1D7C8] pl-3 ml-1">
                        {selectedRival.comp.milestones.map((m, i) => (
                          <div key={i} className="text-xs text-[#4A4239] relative">
                            <span className="absolute -left-[19px] top-1.5 w-2 h-2 rounded-full bg-[#C7431F]" />
                            <p className="leading-relaxed">{m}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Change History (Scans timeline) */}
                  {selectedRival.comp.change_history && selectedRival.comp.change_history.length > 0 && (
                    <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                      <span className="font-bold uppercase text-[11px] text-[#8A8176] block">
                        Detected Changes Over Time
                      </span>
                      <div className="space-y-2">
                        {selectedRival.comp.change_history.map((ch, i) => (
                          <div key={i} className="p-3 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8] text-xs space-y-1">
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="font-bold uppercase text-[#C7431F]">{ch.field || "Update"}</span>
                              <span className="text-[#8A8176] font-mono">
                                {ch.observed_at ? new Date(ch.observed_at).toLocaleDateString() : ""}
                              </span>
                            </div>
                            <p className="font-medium text-[#1F1A17]">
                              {ch.previous ? `${ch.previous} → ` : ""}{ch.current}
                            </p>
                            {ch.source && (
                              <p className="text-[11px] text-[#6B625A] italic">Source: {ch.source}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Firmographics & Scale */}
                  {(selectedRival.comp.employee_count || selectedRival.comp.annual_revenue || selectedRival.comp.funding) && (
                    <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-3">
                      <span className="font-bold uppercase text-[11px] text-[#8A8176] block">
                        Verified Firmographics & Scale
                      </span>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8]">
                          <span className="text-[10px] uppercase font-bold text-[#8A8176] block">Team Size</span>
                          <span className="font-bold text-xs text-[#1F1A17] mt-0.5 block">
                            {selectedRival.comp.employee_count || "Unknown"}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8]">
                          <span className="text-[10px] uppercase font-bold text-[#8A8176] block">Est. Revenue</span>
                          <span className="font-bold text-xs text-[#1F1A17] mt-0.5 block">
                            {selectedRival.comp.annual_revenue || "Private"}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8]">
                          <span className="text-[10px] uppercase font-bold text-[#8A8176] block">Funding</span>
                          <span className="font-bold text-xs text-[#1F1A17] mt-0.5 block">
                            {selectedRival.comp.funding || "Bootstrapped"}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {!selectedRival.comp.leap_benchmark &&
                    (!selectedRival.comp.milestones || selectedRival.comp.milestones.length === 0) &&
                    (!selectedRival.comp.change_history || selectedRival.comp.change_history.length === 0) && (
                      <div className="bg-white p-6 rounded-2xl border border-[#E1D7C8] text-center space-y-1">
                        <p className="text-xs font-bold text-[#1F1A17]">No Breakout Leap benchmark established</p>
                        <p className="text-[11px] text-[#8A8176]">
                          Scrape.do indexed. Incremental changes and catalysts will populate on ongoing scans.
                        </p>
                      </div>
                    )}
                </div>
              )}

              {rivalTab === "cu" && (
                <div className="space-y-4">
                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                    <span className="font-bold uppercase text-[11px] text-[#256545]">What Customers Praise</span>
                    <ul className="list-disc pl-4 space-y-1 text-xs text-[#4A4239]">
                      {selectedRival.praise.length > 0 ? (
                        selectedRival.praise.map((p, i) => <li key={i}>{p}</li>)
                      ) : (
                        <li className="italic text-[#8A8176]">No praise highlights extracted.</li>
                      )}
                    </ul>
                  </div>

                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-2">
                    <span className="font-bold uppercase text-[11px] text-[#A63030]">Customer Complaints & Gaps</span>
                    <ul className="list-disc pl-4 space-y-1 text-xs text-[#4A4239]">
                      {selectedRival.complaints.length > 0 ? (
                        selectedRival.complaints.map((c, i) => <li key={i}>{c}</li>)
                      ) : (
                        <li className="italic text-[#8A8176]">No significant complaints mined.</li>
                      )}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <GlobalSettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

export default WorkspacePage;
