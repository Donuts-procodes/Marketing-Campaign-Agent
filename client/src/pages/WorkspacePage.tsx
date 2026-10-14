import { useState, useEffect, useRef, useMemo } from "react";
import { AudiencePanel } from "@/components/workspace/AudiencePanel";
import { ContentStudio } from "@/components/workspace/ContentStudio";
import { MarketOverviewPanel } from "@/components/workspace/MarketOverviewPanel";
import { DemandChart } from "@/components/workspace/DemandChart";
import { MessagingPanel } from "@/components/workspace/MessagingPanel";
import { PriceLadder } from "@/components/workspace/PriceLadder";
import { PriceMatrix } from "@/components/workspace/PriceMatrix";
import { LivePanel, SchedulePanel } from "@/components/workspace/SchedulePanel";
import { ChatWidget } from "@/components/intel/ChatWidget";
import { useLocation, useParams, useNavigate } from "react-router-dom";
import {
  Sparkles,
  Bot,
  UploadCloud,
  ArrowRight,
  RefreshCw,
  X,
  CheckCircle2,
  Settings,
  AlertCircle,
  FileText,
  ExternalLink,
  Trash2,
  Check,
  Loader2,
  ShieldAlert,
  Target,
  Compass,
  Clock,
  Users,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Plus,
  Pencil,
} from "lucide-react";
import {
  createCampaignJob,
  uploadDossiers,
  listSessions,
  getSession,
  deleteSession,
  fetchMoreCompetitors,
  autofillFromFiles,
  interpretQuery,
  approveCampaignStrategy,
  customizeCampaignStrategy,
  applyReportEdits,
  updateMerchantContext,
  reResearchCampaign,
  regenerateCampaignAsset,
  setChannelApproval,
  rescheduleCampaignContent,
  generateCampaignContent,
  type ChatAction,
} from "@/lib/api-client";
import type { ChannelKey } from "@/types/content";
import { useCampaignStream } from "@/hooks/useCampaignStream";
import { toRivalView, RivalView } from "@/lib/rivalMetrics";
import { SessionSummary, AutofillFields } from "@/types/api";
import { SWOTReportDelta } from "@/types/research";
import { StrategyPlanPanel } from "@/components/strategy/StrategyPlanPanel";

import type {
  CampaignStrategyBrief,
  CampaignStrategyOption,
} from "@/types/strategy";
import { GlobalSettingsModal } from "@/components/dashboard/GlobalSettingsModal";
import { LiveTokenTracker } from "@/components/dashboard/LiveTokenTracker";
import { SWOTGrid } from "@/components/research/SWOTGrid";

const CURRENCY_SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED ", SGD: "S$", AUD: "A$", CAD: "C$", JPY: "¥" };

/** Formats an amount in the brief's currency (brief amounts are never converted). */
function formatMoney(amount: number | null | undefined, currency?: string): string {
  if (amount == null) return "—";
  const code = (currency || "USD").toUpperCase();
  return `${CURRENCY_SYMBOLS[code] ?? code + " "}${Math.round(amount).toLocaleString()}`;
}

// ─── TYPES ───────────────────────────────────────────────────────────────────

export type WorkspaceStage = "brief" | "intel" | "strategy" | "content" | "schedule" | "perf";
export type IntelSubTab = "research" | "swot" | "audience";
export type ContentChannel = "email" | "linkedin" | "retarget" | "ads";

const STAGE_KEYS: WorkspaceStage[] = ["brief", "intel", "strategy", "content", "schedule", "perf"];
const STAGE_LABELS = ["Brief", "Research & Audience", "Strategy", "Content", "Schedule", "Live"];
// URL step slugs <-> stages: /campaigns/:jobId/research, /strategy, /content, /schedule, /live.
const STAGE_SLUG: Record<WorkspaceStage, string> = {
  brief: "brief", intel: "research", strategy: "strategy", content: "content", schedule: "schedule", perf: "live",
};
const SLUG_STAGE: Record<string, WorkspaceStage> = Object.fromEntries(
  Object.entries(STAGE_SLUG).map(([k, v]) => [v, k as WorkspaceStage])
) as Record<string, WorkspaceStage>;

export function WorkspacePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { jobId: routeJobId, step: routeStep } = useParams<{ jobId?: string; step?: string }>();
  const [activeJobId, setActiveJobId] = useState<string | null>(routeJobId || null);
  // Loading state of the saved campaign at /campaigns/:jobId, so no step renders as an empty shell.
  const [sessionState, setSessionState] = useState<"idle" | "loading" | "ready" | "missing" | "error">(
    routeJobId ? "loading" : "idle"
  );
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Sessions from database
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Primary state machine
  // View and stage come from the URL; changing them is a navigation, so the back button works.
  const view: "home" | "ws" = routeJobId || location.pathname === "/campaigns/new" ? "ws" : "home";
  const stage: WorkspaceStage = routeJobId ? SLUG_STAGE[routeStep ?? ""] ?? "intel" : "brief";
  const setView = (v: "home" | "ws") => navigate(v === "home" ? "/" : "/campaigns/new");
  const setStage = (s: WorkspaceStage, jobId: string | null = activeJobId) => {
    if (!jobId) return; // before a job exists the brief step stays on screen
    const to = `/campaigns/${jobId}/${STAGE_SLUG[s]}`;
    if (location.pathname !== to) navigate(to);
  };
  const [maxStep, setMaxStep] = useState<number>(routeJobId ? 1 : 0);
  const [briefSent, setBriefSent] = useState<boolean>(!!routeJobId);

  // Intake Form Inputs
  const [productName, setProductName] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [briefText, setBriefText] = useState<string>("");
  const [targetGeo, setTargetGeo] = useState<string>("");
  const [knownCompetitors, setKnownCompetitors] = useState<string>("");
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isAutofilling, setIsAutofilling] = useState<boolean>(false);
  const [autofilledFields, setAutofilledFields] = useState<Set<string>>(new Set());
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  // Sub-tabs
  const [intelTab, setIntelTab] = useState<IntelSubTab>("research");

  // Approval flags
  const [stratApproved, setStratApproved] = useState<boolean>(false);
  const [stratRevised, setStratRevised] = useState<boolean>(false);

  // Drawers and sidebars
  const [sbOpen, setSbOpen] = useState<boolean>(true);
  const [agentOpen, setAgentOpen] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [selectedRival, setSelectedRival] = useState<RivalView | null>(null);
  const [rivalTab, setRivalTab] = useState<"ov" | "mk" | "hi" | "cu">("ov");

  // Agent Chat & Content State
  const [draft, setDraft] = useState<string>("");
  const [focusedAssetId, setFocusedAssetId] = useState<string | null>(null);
  const [contentRefreshKey, setContentRefreshKey] = useState<number>(0);

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

  // Strategy Customization & Option Selection State
  const [customBudget, setCustomBudget] = useState<number>(10000);
  const [customDays, setCustomDays] = useState<number>(90);
  const [customSubGoals, setCustomSubGoals] = useState<string[]>([]);
  const [newSubGoalInput, setNewSubGoalInput] = useState<string>("");
  const [selectedOptionId, setSelectedOptionId] = useState<string>("opt_disrupter");
  const [isRecalculatingBudget, setIsRecalculatingBudget] = useState<boolean>(false);
  const [strategyViewMode, setStrategyViewMode] = useState<"compact" | "detailed">("compact");
  const [expandedOptionIds, setExpandedOptionIds] = useState<Set<string>>(new Set());

  // Step 1 Form vs Step 2 Options Flow State
  const [optionsGenerated, setOptionsGenerated] = useState<boolean>(false);
  const [isScopeExpanded, setIsScopeExpanded] = useState<boolean>(true);
  const [isCustomOptionModalOpen, setIsCustomOptionModalOpen] = useState<boolean>(false);

  // Custom option creation form states
  const [customOptTitle, setCustomOptTitle] = useState<string>("");
  const [customOptTheme, setCustomOptTheme] = useState<string>("");
  const [customOptTagline, setCustomOptTagline] = useState<string>("");
  const [customOptChannels, setCustomOptChannels] = useState<{ channel: string; budget_percentage: number; rationale: string }[]>([]);
  const [customOptAdvantages, setCustomOptAdvantages] = useState<string>("");
  const [customOptDisadvantages, setCustomOptDisadvantages] = useState<string>("");
  const [customOptCAC, setCustomOptCAC] = useState<string>("");
  const [customOptROI, setCustomOptROI] = useState<string>("");
  const [customOptRisk, setCustomOptRisk] = useState<"Low" | "Medium" | "High">("Medium");

  const toggleOptionDetails = (optionId: string) => {
    setExpandedOptionIds((prev) => {
      const next = new Set(prev);
      if (next.has(optionId)) next.delete(optionId);
      else next.add(optionId);
      return next;
    });
  };

  useEffect(() => {
    if (strategyBrief) {
      if (strategyBrief.user_budget && strategyBrief.user_budget > 0) {
        setCustomBudget(strategyBrief.user_budget);
        setOptionsGenerated(true);
        setIsScopeExpanded(false);
      }
      if (strategyBrief.selected_option_id) {
        setSelectedOptionId(strategyBrief.selected_option_id);
      }
      if (strategyBrief.campaign_days) {
        setCustomDays(strategyBrief.campaign_days);
      }
      if (strategyBrief.sub_goals && strategyBrief.sub_goals.length > 0) {
        setCustomSubGoals(strategyBrief.sub_goals);
      }
    }
  }, [strategyBrief]);

  // The campaign in the URL is the active one; switching campaigns clears the previous one's data.
  useEffect(() => {
    const next = routeJobId ?? null;
    if (next === activeJobId) return;
    setActiveJobId(next);
    setSessionReport(null);
    setSessionStrategyBrief(null);
    setStratApproved(false);
    setMaxStep(next ? 1 : 0);
    setBriefSent(!!next);
    setSessionState(next ? "loading" : "idle");
    setSessionError(null);
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
    let cancelled = false; // a slower response for a previous campaign must not land on this one
    setSessionState((s) => (s === "ready" ? s : "loading"));
    getSession(activeJobId)
      .then((detail) => {
        if (cancelled) return;
        setSessionState("ready");
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
        if (detail.strategy_brief && (detail.strategy_brief as CampaignStrategyBrief).approval_status !== "PENDING_APPROVAL") {
          setStratApproved(true);
          setMaxStep((prev) => Math.max(prev, 5));
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        // A run still starting has no saved record yet; the live stream fills it in.
        if (/404|not found/i.test(msg)) setSessionState(isSubmitting ? "ready" : "missing");
        else {
          setSessionState("error");
          setSessionError(msg);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeJobId]);

  // Sync real-time stream status
  const isRunning =
    isSubmitting ||
    connectionStatus === "CONNECTING" ||
    connectionStatus === "STREAMING" ||
    (activeJobId && !report && connectionStatus !== "COMPLETED" && connectionStatus !== "ERROR");

  // Dynamically derive rivals list from real report — strictly evicting out-of-category noise (<0.4 relevance)
  const rivalsList: RivalView[] = useMemo(() => {
    if (report && report.competitors && report.competitors.length > 0) {
      return report.competitors
        .filter((c) => c.named_by_merchant || c.relevance_score == null || c.relevance_score >= 0.4)
        .map((c, i) => toRivalView(c, i));
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
    }
  }, [connectionStatus, report, activeJobId]);

  // Helper to push messages
  const pushAgent = (_text: string) => {};
  const pushUser = (_text: string) => {};

  // ─── WORKFLOW HANDLERS ─────────────────────────────────────────────────────

  const handleStartCampaign = async () => {
    let effectiveProduct = productName.trim();
    let effectiveBrief = briefText.trim();

    // If product or brief is empty but user uploaded a dossier file, synthesize reasonable defaults
    if (!effectiveProduct && uploadedFiles.length > 0) {
      const baseName = uploadedFiles[0].name.replace(/\.[^/.]+$/, "").replace(/[_\-+]/g, " ").trim();
      effectiveProduct = baseName || "Brand Product";
      setProductName(effectiveProduct);
    }
    if (!effectiveBrief && uploadedFiles.length > 0) {
      effectiveBrief = `Market research, competitor benchmarking, and launch strategy for ${effectiveProduct || "our product"} based on uploaded dossier context.`;
      setBriefText(effectiveBrief);
    }

    if (!effectiveProduct) {
      setErrorNotice("Please enter your product or brand name to start research.");
      return;
    }
    if (!effectiveBrief) {
      setErrorNotice("Please enter what you want to achieve or your campaign goal.");
      return;
    }

    setErrorNotice(null);
    setIsSubmitting(true);
    setBriefSent(true);
    setMaxStep(1);
    setIntelTab("research");

    lastProcessedLogRef.current = 0;
    seenMilestonesRef.current.clear();
    hasSentDoneRef.current = null;

    pushUser(`Product: ${effectiveProduct} (${category || "Technology"})\nGoal: ${effectiveBrief}`);
    pushAgent(`Deploying autonomous market research agent for ${effectiveProduct}. Gathering facts on competitors, the market and buyers.`);

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
          product_name: effectiveProduct,
          category: category.trim() || "Technology",
          primary_value_prop: effectiveBrief,
          goal: effectiveBrief,
          target_geography: targetGeo.trim(),
          known_competitors: rivalsArray,
        },
        byok_config: byokConfig,
        run_mode: "fresh" as const,
      };

      const res = await createCampaignJob(payload);
      const newJobId = res.job_id;
      setActiveJobId(newJobId);
      setSessionState("ready"); // the live stream owns this run's data from here
      // replace: "back" from research returns to the campaign list, not to a half-sent brief.
      navigate(`/campaigns/${newJobId}/research`, { replace: true });

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
    navigate(`/campaigns/${s.job_id}/research`);
    if (s.product_name) setProductName(s.product_name);
    if (s.category) setCategory(s.category);
  };

  const handleDeleteSession = async (jobId: string) => {
    if (!window.confirm("Are you sure you want to delete this campaign session?")) return;
    try {
      await deleteSession(jobId);
      setSessions((prev) => prev.filter((s) => s.job_id !== jobId));
      if (activeJobId === jobId) {
        navigate("/", { replace: true }); // the deleted campaign's URL must not stay in history
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
      // Fallback: If AI autofill failed (e.g. no OpenAI API key configured or rate limit),
      // populate defaults from filename so user is never stuck
      if (!productName.trim() && filesToParse[0]) {
        const fallbackName = filesToParse[0].name.replace(/\.[^/.]+$/, "").replace(/[_\-+]/g, " ").trim();
        if (fallbackName) {
          setProductName(fallbackName);
        }
      }
      if (!briefText.trim()) {
        setBriefText(`Strategic marketing research and competitor benchmarking based on ${filesToParse[0]?.name || "attached dossier"}.`);
      }
      // Inform user gently without breaking the workflow
      const msg = err instanceof Error ? err.message : "Document attached. Form ready to submit.";
      pushAgent(`Document attached: ${filesToParse.map(f => f.name).join(", ")}. (${msg})`);
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
    setMaxStep((prev) => Math.max(prev, 2));
    setStage("strategy");
    pushAgent("Strategy synthesized from competitor positioning gaps. Read through the angles and approve to generate copy.");
  };

  const handleRequestChanges = () => {
    setStratRevised(true);
    setAgentOpen(true);
    setDraft("Sharpen the positioning angle against " + (rivalsList[0]?.name || "competitors"));
  };

  const handleRecalculateStrategy = async (
    newBudget?: number,
    newOptionId?: string,
    newDays?: number,
    updatedSubGoals?: string[],
  ) => {
    const b = newBudget !== undefined ? newBudget : customBudget;
    const d = newDays !== undefined ? newDays : customDays;
    const g = updatedSubGoals !== undefined ? updatedSubGoals : customSubGoals;
    const targetOption = newOptionId || selectedOptionId;

    if (newBudget !== undefined) setCustomBudget(newBudget);
    if (newDays !== undefined) setCustomDays(d);
    if (updatedSubGoals !== undefined) setCustomSubGoals(g);
    if (newOptionId) setSelectedOptionId(newOptionId);

    setOptionsGenerated(true);

    if (!activeJobId) return;
    setIsRecalculatingBudget(true);
    try {
      const updated = await customizeCampaignStrategy(activeJobId, {
        budget: b,
        campaign_days: d,
        sub_goals: g,
        selected_option_id: targetOption,
      });
      setSessionStrategyBrief(updated);
      pushAgent(`Recalculated strategy for $${b.toLocaleString()} budget over ${d} days with ${g.length} sub-goal(s).`);
    } catch (err) {
      console.warn("Strategy update error:", err);
    } finally {
      setIsRecalculatingBudget(false);
    }
  };

  const handleGenerateOptions = async () => {
    await handleRecalculateStrategy(customBudget, undefined, customDays, customSubGoals);
    setOptionsGenerated(true);
    setIsScopeExpanded(false);
  };

  const handleSaveCustomOption = async () => {
    const optionId = `opt_custom_${Date.now()}`;
    const newOption: CampaignStrategyOption = {
      option_id: optionId,
      title: customOptTitle.trim() || "Custom Strategy Option",
      theme: customOptTheme.trim() || "Tailored Strategic Execution",
      tagline: customOptTagline.trim() || "Custom tactical distribution strategy.",
      recommended: false,
      budget_allocation_summary: customOptChannels
        .map(
          (c) =>
            `$${Math.round((customBudget * c.budget_percentage) / 100).toLocaleString()} ${c.channel} (${c.budget_percentage}%)`
        )
        .join(" • "),
      channel_matrix: customOptChannels.map((c) => ({
        channel: c.channel,
        budget_percentage: c.budget_percentage,
        recommended_spend_usd: Math.round((customBudget * c.budget_percentage) / 100),
        rationale: c.rationale || `Allocated ${c.budget_percentage}% of total media budget`,
        spend_type: "ad_spend" as const,
      })),
      advantages: customOptAdvantages
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      disadvantages: customOptDisadvantages
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      constraints: [`Calibrated for $${customBudget.toLocaleString()} media budget over ${customDays} days.`],
      opportunities: ["Engineered around custom founder priorities and direct distribution."],
      suggested_channels: customOptChannels.map((c) => c.channel),
      promotion_means: ["Direct Switcher Incentive", "Founder Pilot Consultation", "Migration Guarantee"],
      prediction: {
        projected_cac: customOptCAC || null,
        projected_roi: customOptROI || null,
        conversion_velocity: null,
        risk_level: customOptRisk,
        break_even_timeline: null,
        basis: customOptCAC || customOptROI ? "Entered by you" : "Not projected; set from the first test",
      },
    };

    setSelectedOptionId(optionId);
    setOptionsGenerated(true);
    setIsCustomOptionModalOpen(false);

    if (activeJobId) {
      try {
        const updated = await customizeCampaignStrategy(activeJobId, {
          budget: customBudget,
          campaign_days: customDays,
          sub_goals: customSubGoals,
          selected_option_id: optionId,
          custom_option: newOption,
        });
        setSessionStrategyBrief(updated);
        pushAgent(`Activated custom strategy: "${newOption.title}". Channel allocations and execution blueprint updated.`);
      } catch (err) {
        console.warn("Custom option sync error:", err);
        if (sessionStrategyBrief) {
          const updatedOptions = [newOption, ...(sessionStrategyBrief.campaign_options || [])];
          setSessionStrategyBrief({
            ...sessionStrategyBrief,
            campaign_options: updatedOptions,
            selected_option_id: optionId,
            channel_matrix: newOption.channel_matrix,
          });
        }
      }
    }
  };

  const handleRecalculateBudget = (newBudget: number, newOptionId?: string) => {
    return handleRecalculateStrategy(newBudget, newOptionId);
  };

  const handleApproveStrategy = async () => {
    setStratApproved(true);
    if (activeJobId) {
      try {
        const approvedBrief = await approveCampaignStrategy(activeJobId, {
          budget: customBudget,
          campaign_days: customDays,
          sub_goals: customSubGoals,
          selected_option_id: selectedOptionId,
        });
        setSessionStrategyBrief(approvedBrief);
      } catch (err) {
        // Not approved on the server: stay here instead of opening a Content step that would refuse.
        setStratApproved(false);
        setErrorNotice(err instanceof Error ? `Approval failed: ${err.message}` : "Approval failed");
        return;
      }
    }
    setMaxStep((prev) => Math.max(prev, 5));
    setStage("content");
    pushUser("Approved strategy.");
    pushAgent(`Strategy approved. Handing off to copy generation engine with allocated budget.`);
  };

  // Runs an action the merchant confirmed in the chat and returns a one-line result for its card.
  const runChatAction = async (action: ChatAction): Promise<string> => {
    if (!activeJobId) throw new Error("No active campaign run.");
    if (action.kind === "customize_strategy") {
      const payload = action.payload;
      await customizeCampaignStrategy(activeJobId, {
        budget: payload.budget,
        campaign_days: payload.campaign_days,
        sub_goals: payload.sub_goals,
        campaign_type: payload.campaign_type,
        selected_option_id: payload.selected_option_id,
        custom_goal: payload.custom_goal,
      });
      await handleRecalculateStrategy(payload.budget, payload.selected_option_id, payload.campaign_days, payload.sub_goals);
      return "Campaign strategy parameters updated.";
    }
    if (action.kind === "rewrite_asset") {
      const payload = action.payload;
      if (!payload.asset_id) throw new Error("No asset specified for rewrite.");
      await regenerateCampaignAsset(activeJobId, payload.asset_id, payload.instruction);
      setContentRefreshKey((k) => k + 1);
      return `Asset ${payload.asset_id} updated with new copy.`;
    }
    if (action.kind === "channel_approval") {
      const payload = action.payload;
      if (!payload.channel) throw new Error("No channel specified for approval.");
      await setChannelApproval(activeJobId, payload.channel as ChannelKey, payload.approved ?? true);
      setContentRefreshKey((k) => k + 1);
      return `${payload.channel} ${payload.approved === false ? "unapproved" : "approved"}.`;
    }
    if (action.kind === "reschedule") {
      const payload = action.payload;
      await rescheduleCampaignContent(activeJobId, {
        shift_days: payload.shift_days,
        time_of_day: payload.time_of_day,
        channel: payload.channel,
        asset_ids: payload.asset_ids,
      });
      setContentRefreshKey((k) => k + 1);
      return `Publishing schedule updated${payload.shift_days ? ` by ${payload.shift_days} days` : ""}.`;
    }
    if (action.kind === "regenerate_content") {
      await generateCampaignContent(activeJobId);
      setContentRefreshKey((k) => k + 1);
      return "Content generation re-triggered.";
    }
    if (action.kind === "edit") {
      const res = await applyReportEdits(activeJobId, action.payload.edits ?? []);
      setSessionReport(res.swot_report);
      return res.applied.join(" · ") || "Report updated.";
    }
    if (action.kind === "update_context") {
      if (action.payload.field && action.payload.value !== undefined) {
        const res = await updateMerchantContext(activeJobId, action.payload.field, action.payload.value);
        return res.applied || "Campaign context updated.";
      }
      return "No field specified for context update.";
    }
    if (action.kind === "research") {
      const names = action.payload.names ?? [];
      const res = await fetchMoreCompetitors(activeJobId, names);
      setSessionReport(res.swot_report);
      return res.added_competitors.length
        ? `Added ${res.added_competitors.map((c) => c.brand_name).join(", ")} to the report.`
        : "No new competitors could be researched.";
    }
    if (action.kind === "refresh") {
      const res = await reResearchCampaign(activeJobId);
      setSessionReport(res.swot_report);
      return "The research was re-run and the report is up to date.";
    }
    return "Action completed.";
  };

  const stageIdx = STAGE_KEYS.indexOf(stage);

  // Status chip metadata
  const statusMeta = (() => {
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


  // Step guard: a URL step the campaign has not reached (or an unknown one) is replaced by the
  // furthest step it has, so no step renders as an empty shell and "back" never lands on one.
  useEffect(() => {
    if (!routeJobId || sessionState !== "ready") return;
    const known = routeStep != null && routeStep in SLUG_STAGE && routeStep !== "brief";
    const idx = known ? STAGE_KEYS.indexOf(SLUG_STAGE[routeStep!]) : -1;
    if (!known || idx > Math.max(1, maxStep)) {
      const allowed = STAGE_KEYS[Math.min(Math.max(1, maxStep), known ? idx : 1)];
      navigate(`/campaigns/${routeJobId}/${STAGE_SLUG[allowed]}`, { replace: true });
    }
  }, [routeJobId, routeStep, sessionState, maxStep]);

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
                setBriefSent(false);
                setProductName("");
                setCategory("");
                setBriefText("");
                navigate("/campaigns/new");
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

  // A saved campaign is loading: one clear loader instead of an empty step.
  if (routeJobId && sessionState === "loading" && !report) {
    return (
      <div className="min-h-screen bg-[#FAF6EF] flex flex-col items-center justify-center gap-3 text-[#4A4239]" role="status" aria-live="polite">
        <Loader2 className="w-7 h-7 animate-spin text-[#C7431F]" />
        <p className="text-sm font-semibold">Loading campaign…</p>
      </div>
    );
  }
  if (routeJobId && (sessionState === "missing" || sessionState === "error")) {
    return (
      <div className="min-h-screen bg-[#FAF6EF] flex flex-col items-center justify-center gap-4 px-4 text-center">
        <h1 className="font-['Bricolage_Grotesque'] text-2xl font-bold text-[#1F1A17]">
          {sessionState === "missing" ? "Campaign not found" : "Could not load this campaign"}
        </h1>
        <p className="text-sm text-[#4A4239] max-w-md">
          {sessionState === "missing"
            ? "It may have been deleted, or the link is wrong."
            : `The server did not answer (${sessionError}). Check that the orchestrator is running, then retry.`}
        </p>
        <div className="flex gap-2">
          {sessionState === "error" && (
            <button
              onClick={() => {
                setSessionState("loading");
                setActiveJobId(null);
                setTimeout(() => setActiveJobId(routeJobId), 0); // re-runs the load effect
              }}
              className="px-4 py-2 rounded-xl bg-[#1F1A17] text-white text-xs font-bold"
            >
              Retry
            </button>
          )}
          <button onClick={() => navigate("/")} className="px-4 py-2 rounded-xl border border-[#E1D7C8] bg-white text-xs font-bold">
            Back to campaigns
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAF6EF] text-[#1F1A17] font-['Manrope',sans-serif] flex flex-col selection:bg-[#F3CFC0] selection:text-[#8F2F14]">
      {/* ─── TOP WORKSPACE HEADER ─── */}
      <header className="h-16 border-b border-[#E1D7C8] px-3 sm:px-6 flex items-center justify-between bg-[#FAF6EF] sticky top-0 z-30 flex-nowrap gap-2 sm:gap-4 select-none">
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <button
            onClick={() => setSbOpen(!sbOpen)}
            className="p-2 rounded-lg border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[#4A4239] transition cursor-pointer"
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
        <nav className="hidden md:flex items-center gap-1 sm:gap-1.5 shrink min-w-0" aria-label="Campaign progress">
          {STAGE_LABELS.map((label, idx) => {
            const isDone = idx < stageIdx;
            const isCur = idx === stageIdx;
            const isLocked = idx > maxStep;

            return (
              <button
                key={label}
                disabled={isLocked}
                title={label}
                onClick={() => {
                  if (idx <= maxStep) {
                    setStage(STAGE_KEYS[idx] as WorkspaceStage);
                  }
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition shrink-0 ${
                  isCur
                    ? "bg-[#1F1A17] text-white shadow-xs"
                    : isDone
                    ? "text-[#1F1A17] hover:bg-[#EFE7DB] cursor-pointer"
                    : "text-[#8A8176] opacity-50 cursor-not-allowed"
                }`}
              >
                <span
                  className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
                    isCur
                      ? "bg-[#C7431F] text-white"
                      : isDone
                      ? "bg-[#3F9068] text-white"
                      : "bg-[#E1D7C8] text-[#6B625A]"
                  }`}
                >
                  {isDone ? "✓" : idx + 1}
                </span>
                <span className="hidden xl:inline">{label}</span>
                <span className="inline xl:hidden">{label.split(" ")[0]}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Status, Token Monitor, Settings & Agent Toggle */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
          <LiveTokenTracker onClick={() => setSettingsOpen(true)} />

          <button
            onClick={() => setSettingsOpen(true)}
            className="p-2 rounded-xl border border-[#E1D7C8] bg-white hover:bg-[#FDF9F3] text-[#4A4239] transition shadow-xs cursor-pointer"
            title="Global Settings & BYOK"
          >
            <Settings className="w-4 h-4" />
          </button>

          <div className={`hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-bold ${statusMeta.bg} ${statusMeta.text}`}>
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
                      Enter your product, sector, and goals. The agent researches your competitors, market and buyers, then builds the campaign strategy and content.
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
                      Researching <strong>{productName}</strong>.
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
                        Every fact links to the page it came from.
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
                        onClick={() => setIntelTab("swot")}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer ${
                          intelTab === "swot" ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"
                        }`}
                      >
                        SWOT Analysis
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
                      <DemandChart demand={report?.demand} />
                      <MarketOverviewPanel market={report?.market_overview} />
                      <PriceLadder
                        competitors={report?.competitors ?? []}
                        merchantPrice={strategyBrief?.economics?.price ?? null}
                        currency={strategyBrief?.currency ?? null}
                      />
                      <PriceMatrix
                        competitors={report?.competitors ?? []}
                        merchantName={productName}
                        merchantPrice={strategyBrief?.economics?.price ?? null}
                        currency={strategyBrief?.currency ?? null}
                      />
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
                                      {r.logoUrl ? (
                                        <div className="w-7 h-7 rounded-lg border border-[#E1D7C8] bg-white overflow-hidden flex items-center justify-center shrink-0">
                                          <img
                                            src={r.logoUrl}
                                            alt={r.name}
                                            className="w-full h-full object-contain p-0.5"
                                            onError={(e) => {
                                              (e.target as HTMLElement).style.display = "none";
                                              const parent = (e.target as HTMLElement).parentElement;
                                              if (parent) {
                                                parent.className = "w-7 h-7 rounded-lg text-white flex items-center justify-center text-xs font-bold shrink-0 bg-[#C7431F]";
                                                parent.innerText = r.initials;
                                              }
                                            }}
                                          />
                                        </div>
                                      ) : (
                                        <span
                                          className="w-7 h-7 rounded-lg text-white flex items-center justify-center text-xs font-bold shrink-0"
                                          style={{ backgroundColor: "#C7431F" }}
                                        >
                                          {r.initials}
                                        </span>
                                      )}
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

                      {/* Strategic SWOT Analysis Section */}
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="font-['Bricolage_Grotesque'] text-xl font-bold">
                              Strategic SWOT & Market Positioning
                            </h3>
                            <p className="text-xs text-[#8A8176]">
                              Merchant strengths, weaknesses, exploitable openings, and competitor threats.
                            </p>
                          </div>
                          <button
                            onClick={() => setIntelTab("swot")}
                            className="text-xs font-bold text-[#C7431F] hover:underline cursor-pointer"
                          >
                            Full SWOT view →
                          </button>
                        </div>

                        <SWOTGrid swot={report?.swot} positioningGap={report?.positioning_gap} />
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
                                  {leap?.origin_story || r.comp.relevance_reason}
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
                  ) : intelTab === "swot" ? (
                    /* Dedicated SWOT Analysis Tab */
                    <div className="space-y-6">
                      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-[#C7431F]">
                          Competitive Strategy Matrix
                        </span>
                        <h2 className="font-['Bricolage_Grotesque'] text-2xl font-bold">
                          Strategic SWOT Analysis & Positioning Gap
                        </h2>
                        <p className="text-xs text-[#6B625A]">
                          Evidence-grounded 4-quadrant strategic matrix benchmarking merchant advantages against discovered rivals, verified customer pain points, and category blindspots.
                        </p>
                      </div>

                      <SWOTGrid swot={report?.swot} positioningGap={report?.positioning_gap} />
                    </div>
                  ) : (
                    <AudiencePanel audience={report?.audience} personas={strategyBrief?.personas_used ?? []} />
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
          {stage === "strategy" && !strategyBrief && (
            <div className="max-w-[880px] mx-auto py-24 flex flex-col items-center gap-3 text-[#4A4239]" role="status" aria-live="polite">
              {isRunning || report ? (
                <>
                  <Loader2 className="w-7 h-7 animate-spin text-[#C7431F]" />
                  <p className="text-sm font-semibold">Building your strategy from the research…</p>
                  <p className="text-xs text-[#8A8176]">This step appears as soon as the plan, personas and messaging are ready.</p>
                </>
              ) : (
                <p className="text-sm">The strategy needs finished research first.</p>
              )}
            </div>
          )}
          {stage === "strategy" && strategyBrief && (
            <div className="max-w-[880px] mx-auto space-y-8 animate-fade-up">
              <MessagingPanel messaging={strategyBrief?.messaging} />
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

              {/* 1. Campaign Scope, Duration, Budget & Sub-Goals Customization Card */}
              {optionsGenerated && !isScopeExpanded ? (
                /* Compact Executive Scope Bar */
                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-6 flex-wrap">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#8A8176] block">
                        Media Capital
                      </span>
                      <span className="font-['Bricolage_Grotesque'] font-bold text-lg text-[#1F1A17]">
                        ${customBudget.toLocaleString()}{" "}
                        <span className="text-xs font-normal text-[#8A8176]">Working Capital</span>
                      </span>
                    </div>
                    <div className="h-8 w-px bg-[#E1D7C8] hidden sm:block" />
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#8A8176] block">
                        Flight Duration
                      </span>
                      <span className="font-['Bricolage_Grotesque'] font-bold text-lg text-[#1F1A17]">
                        {customDays} <span className="text-xs font-normal text-[#8A8176]">Days</span>
                      </span>
                    </div>
                    <div className="h-8 w-px bg-[#E1D7C8] hidden sm:block" />
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#8A8176] block">
                        Active Sub-Goals
                      </span>
                      <span className="font-['Bricolage_Grotesque'] font-bold text-lg text-[#1F1A17]">
                        {customSubGoals.length}{" "}
                        <span className="text-xs font-normal text-[#8A8176]">Milestones</span>
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsScopeExpanded(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#FAF6EE] hover:bg-[#F1EADF] border border-[#E1D7C8] text-xs font-bold text-[#1F1A17] transition shadow-xs cursor-pointer"
                    >
                      <Pencil className="w-3.5 h-3.5 text-[#C7431F]" />
                      <span>Adjust Scope & Budget</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setAgentOpen(true);
                        pushAgent(
                          "I'm ready to customize your strategy! Tell me what you'd like to adjust (e.g. 'Increase budget to $25k', 'Shorten to 60 days', or 'Add subgoal: 20 enterprise pilots')."
                        );
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#FAF6EE] hover:bg-[#F1EADF] text-[#C7431F] border border-[#E1D7C8] text-xs font-bold transition shadow-xs cursor-pointer"
                    >
                      <Bot className="w-3.5 h-3.5" />
                      <span>Customize via AI</span>
                    </button>
                  </div>
                </div>
              ) : (
                /* Full Interactive Scope, Budget & Sub-Goals Form */
                <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#FDF1EB] text-[#C7431F] border border-[#F3CFC0]">
                          {optionsGenerated ? "Reconfigure Campaign Parameters" : "Step 1 of 2: Define Scope & Working Capital"}
                        </span>
                      </div>
                      <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                        Target {customDays}-Day Media Budget & Sub-Goals Form
                      </h3>
                      <p className="text-xs text-[#6B625A]">
                        Enter your direct advertising network budget, duration, and custom milestones. The strategic agent autonomously calculates channel allocations, ROI predictions, and phased execution.
                      </p>
                    </div>
                    {strategyBrief?.core_goal && (
                      <div className="px-3 py-1.5 rounded-xl bg-[#FAF6EE] border border-[#E1D7C8] text-xs">
                        <span className="text-[10px] font-bold uppercase text-[#8A8176] block">Core Goal:</span>
                        <span className="font-bold text-[#1F1A17]">{strategyBrief.core_goal}</span>
                      </div>
                    )}
                  </div>

                  {/* Working Capital Guidance Callout */}
                  <div className="flex items-start gap-3 p-3.5 rounded-xl bg-[#FAF6EE] border border-[#E9DFC7] text-xs text-[#5C5346]">
                    <ShieldAlert className="w-4 h-4 text-[#C7431F] shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <span className="font-bold text-[#1F1A17] block">
                        Working Capital & Direct Media Spend (Strictly No Employee Payroll)
                      </span>
                      <p className="text-[11px] leading-relaxed">
                        Enter only direct advertising network capital (Google, LinkedIn, Meta) and specialized data enrichment/tooling credits.{" "}
                        <strong className="text-[#C7431F]">Do NOT factor in internal team salaries or marketing agency retainers.</strong> All campaign operations, copywriting, keyword bidding, outreach, and optimization are autonomously executed by the dedicated AI Subagents roster at $0 marginal labor cost.
                      </p>
                    </div>
                  </div>

                  {/* Controls Grid: Budget & Duration */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-[#F1EADF]">
                    {/* Budget Input & Presets */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-[#1F1A17]">Media Budget (USD):</label>
                        <div className="flex items-center gap-1.5">
                          {[5000, 10000, 25000, 50000].map((preset) => (
                            <button
                              key={preset}
                              type="button"
                              onClick={() => setCustomBudget(preset)}
                              className={`px-2 py-0.5 rounded-md text-[11px] font-bold border transition cursor-pointer ${
                                customBudget === preset
                                  ? "bg-[#C7431F] text-white border-[#C7431F]"
                                  : "bg-[#FAF6EF] text-[#4A4239] border-[#E1D7C8] hover:bg-white"
                              }`}
                            >
                              ${(preset / 1000).toFixed(0)}k
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="relative">
                        <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-sm font-bold text-[#8A8176]">$</span>
                        <input
                          type="number"
                          min={500}
                          step={500}
                          value={customBudget}
                          onChange={(e) => setCustomBudget(Number(e.target.value) || 0)}
                          className="w-full pl-8 pr-4 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-sm font-bold text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                          placeholder="Enter budget in USD..."
                        />
                      </div>
                    </div>

                    {/* Campaign Days Input & Presets */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-[#1F1A17]">Campaign Duration (Days):</label>
                        <div className="flex items-center gap-1.5">
                          {[14, 30, 60, 90, 180].map((preset) => (
                            <button
                              key={preset}
                              type="button"
                              onClick={() => setCustomDays(preset)}
                              className={`px-2 py-0.5 rounded-md text-[11px] font-bold border transition cursor-pointer ${
                                customDays === preset
                                  ? "bg-[#C7431F] text-white border-[#C7431F]"
                                  : "bg-[#FAF6EF] text-[#4A4239] border-[#E1D7C8] hover:bg-white"
                              }`}
                            >
                              {preset}d
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="relative">
                        <input
                          type="number"
                          min={7}
                          max={365}
                          step={1}
                          value={customDays}
                          onChange={(e) => setCustomDays(Number(e.target.value) || 7)}
                          className="w-full px-4 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-sm font-bold text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                          placeholder="Enter duration in days..."
                        />
                      </div>
                    </div>
                  </div>

                  {/* Sub-Goals Manager */}
                  <div className="space-y-2 pt-2 border-t border-[#F1EADF]">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#1F1A17]">Campaign Sub-Goals & Milestones:</label>
                      <span className="text-[11px] text-[#8A8176]">
                        {customSubGoals.length} custom goal(s) registered
                      </span>
                    </div>

                    {/* Current Sub-Goals Tags */}
                    <div className="flex flex-wrap gap-2 min-h-[32px] items-center">
                      {customSubGoals.length > 0 ? (
                        customSubGoals.map((sg, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#FAF6EE] border border-[#E1D7C8] text-xs text-[#1F1A17] font-medium"
                          >
                            <Target className="w-3 h-3 text-[#C7431F]" />
                            <span>{sg}</span>
                            <button
                              type="button"
                              onClick={() => {
                                const updated = customSubGoals.filter((_, i) => i !== idx);
                                setCustomSubGoals(updated);
                              }}
                              className="text-[#8A8176] hover:text-[#C7431F] ml-1 font-bold cursor-pointer"
                            >
                              ×
                            </button>
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-[#8A8176] italic">
                          No sub-goals added yet. Select a quick recommendation below or type your custom milestone.
                        </span>
                      )}
                    </div>

                    {/* Quick-Add Suggestion Chips */}
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-[10px] font-bold uppercase text-[#8A8176]">Quick-Add Suggestions:</span>
                      {(strategyBrief?.plan?.success_metrics ?? []).slice(0, 4).map((sug, sIdx) => (
                        <button
                          key={sIdx}
                          type="button"
                          onClick={() => {
                            if (!customSubGoals.includes(sug)) {
                              setCustomSubGoals([...customSubGoals, sug]);
                            }
                          }}
                          className="px-2 py-0.5 rounded-md bg-[#FAF6EF] hover:bg-[#F1EADF] border border-[#E1D7C8] text-[10px] font-medium text-[#4A4239] transition cursor-pointer"
                        >
                          + {sug}
                        </button>
                      ))}
                    </div>

                    {/* Add Sub-Goal Input */}
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="text"
                        value={newSubGoalInput}
                        onChange={(e) => setNewSubGoalInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && newSubGoalInput.trim()) {
                            e.preventDefault();
                            const val = newSubGoalInput.trim();
                            if (!customSubGoals.includes(val)) {
                              setCustomSubGoals([...customSubGoals, val]);
                            }
                            setNewSubGoalInput("");
                          }
                        }}
                        placeholder="Add a new custom sub-goal (e.g. 'Get 100 enterprise trial signups', 'Hit <$80 CPA')..."
                        className="flex-1 px-4 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                      />
                      <button
                        type="button"
                        disabled={!newSubGoalInput.trim()}
                        onClick={() => {
                          const val = newSubGoalInput.trim();
                          if (val && !customSubGoals.includes(val)) {
                            setCustomSubGoals([...customSubGoals, val]);
                          }
                          setNewSubGoalInput("");
                        }}
                        className="px-4 py-2 rounded-xl bg-[#FAF6EF] hover:bg-[#F1EADF] border border-[#E1D7C8] text-xs font-bold text-[#1F1A17] cursor-pointer disabled:opacity-40"
                      >
                        + Add
                      </button>
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div className="flex items-center justify-between flex-wrap gap-3 pt-3 border-t border-[#F1EADF]">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setIsCustomOptionModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#FAF6EE] hover:bg-[#F1EADF] border border-[#E1D7C8] text-xs font-bold text-[#1F1A17] transition shadow-xs cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5 text-[#C7431F]" />
                        <span>+ Build Custom Option</span>
                      </button>
                      {optionsGenerated && (
                        <button
                          type="button"
                          onClick={() => setIsScopeExpanded(false)}
                          className="px-3 py-2 rounded-xl text-xs font-bold text-[#8A8176] hover:text-[#1F1A17] transition cursor-pointer"
                        >
                          Minimize Form
                        </button>
                      )}
                    </div>

                    <button
                      type="button"
                      disabled={isRecalculatingBudget || customBudget < 100}
                      onClick={handleGenerateOptions}
                      className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white text-xs font-bold transition shadow-xs cursor-pointer disabled:opacity-50"
                    >
                      {isRecalculatingBudget ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Synthesizing Strategy Options...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>{optionsGenerated ? "Update & Recalculate Options" : "⚡ Generate Tailored Strategy Options"}</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* 2. Competitor Strategy & Market Footprint Intelligence */}
              <div className="space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">
                      Competitor Strategy & Ad Footprint Intelligence
                    </h3>
                    <p className="text-xs text-[#6B625A]">
                      Live competitor advertising channels, monthly spend estimates, active hooks, and exploitable blindspots discovered autonomously.
                    </p>
                  </div>
                  <span className="text-[11px] px-2.5 py-1 rounded-full bg-[#E4F2EA] text-[#256545] font-bold border border-[#256545]/20 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#256545] animate-pulse" />
                    Autonomous SERP & Ad Mining
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {(strategyBrief?.competitor_campaign_intel ?? []).map((intel, idx) => (
                    <div key={idx} className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs flex flex-col justify-between space-y-3">
                      <div className="space-y-3">
                        {/* Header: Name + Spend / Library Badge */}
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <span className="font-['Bricolage_Grotesque'] font-bold text-base text-[#1F1A17] block">
                              {intel.competitor_name}
                            </span>
                            {intel.campaign_themes && intel.campaign_themes.length > 0 && (
                              <span className="text-[11px] text-[#8A8176] font-medium block">
                                Strategy: {intel.campaign_themes[0]}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-md bg-[#FAF6EE] text-[#C7431F] border border-[#E1D7C8] shrink-0">
                            {intel.estimated_monthly_ad_spend || "Ad Active"}
                          </span>
                        </div>

                        {/* Distribution Channels */}
                        <div>
                          <span className="text-[10px] font-bold uppercase text-[#8A8176] block mb-1">
                            Distribution Channels:
                          </span>
                          <div className="flex flex-wrap gap-1">
                            {intel.detected_channels.map((ch, cIdx) => (
                              <span key={cIdx} className="text-[10px] bg-[#FAF6EF] border border-[#EFE7DB] px-2 py-0.5 rounded-md text-[#4A4239] font-medium">
                                {ch}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Flagship Clients / Target ICP if available */}
                        {(intel.competitor_flagship_clients?.length || intel.competitor_icp) ? (
                          <div className="p-2.5 rounded-xl bg-[#FAF6EE] border border-[#EFE7DB] text-[11px] space-y-1">
                            {intel.competitor_icp && (
                              <div className="text-[#5C5346]">
                                <strong className="text-[#1F1A17]">Target ICP:</strong> {intel.competitor_icp}
                              </div>
                            )}
                            {intel.competitor_flagship_clients && intel.competitor_flagship_clients.length > 0 && (
                              <div className="text-[#5C5346] flex flex-wrap items-center gap-1">
                                <strong className="text-[#1F1A17]">Clients:</strong>
                                {intel.competitor_flagship_clients.slice(0, 3).map((cl, clIdx) => (
                                  <span key={clIdx} className="px-1.5 py-0.2 rounded bg-white text-[10px] font-medium border border-[#E1D7C8]">
                                    {cl}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : null}

                        {/* Active Promo Hook */}
                        {intel.active_offers_and_hooks && intel.active_offers_and_hooks.length > 0 && (
                          <div className="text-xs">
                            <span className="text-[10px] font-bold uppercase text-[#8A8176] block mb-0.5">
                              Active Lead Hook:
                            </span>
                            <p className="text-[11px] text-[#4A4239] italic pl-2 border-l-2 border-[#C7431F]">
                              "{intel.active_offers_and_hooks[0]}"
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Exploitable Blindspot */}
                      <div className="p-2.5 rounded-xl bg-[#FDF1EB] border border-[#F3CFC0] text-xs mt-2">
                        <span className="font-bold text-[#8F2F14] block mb-0.5 flex items-center gap-1 text-[11px]">
                          <AlertCircle className="w-3 h-3 text-[#C7431F]" />
                          <span>Exploitable Blindspot:</span>
                        </span>
                        <span className="text-[#8F2F14] text-[11px] leading-relaxed block">
                          {intel.blindspots[0] || "Opaque enterprise pricing with high switching friction"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3. Comparative Campaign Strategy Options */}
              {!optionsGenerated ? (
                /* Awaiting Scope & Parameters Teaser Card */
                <div className="bg-[#FAF6EE] border-2 border-dashed border-[#E1D7C8] rounded-3xl p-8 text-center space-y-4">
                  <div className="w-12 h-12 rounded-2xl bg-white border border-[#E1D7C8] flex items-center justify-center mx-auto text-[#C7431F] shadow-xs">
                    <Compass className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h4 className="font-['Bricolage_Grotesque'] text-xl font-bold text-[#1F1A17]">
                      Strategic Campaign Options Awaiting Scope Input
                    </h4>
                    <p className="text-xs text-[#6B625A] max-w-lg mx-auto leading-relaxed">
                      Configure your media capital budget, duration, and milestones above, then click{" "}
                      <strong className="text-[#1F1A17]">⚡ Generate Tailored Strategy Options</strong>. The AI will synthesize 3 comparative options calibrated to your parameters, or you can build a custom option right away.
                    </p>
                  </div>
                  <div className="flex items-center justify-center gap-3 pt-2 flex-wrap">
                    <button
                      type="button"
                      disabled={isRecalculatingBudget || customBudget < 100}
                      onClick={handleGenerateOptions}
                      className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white text-xs font-bold transition shadow-xs cursor-pointer disabled:opacity-50"
                    >
                      {isRecalculatingBudget ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Synthesizing Options...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>⚡ Generate Tailored Strategy Options</span>
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsCustomOptionModalOpen(true)}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white hover:bg-[#F1EADF] border border-[#E1D7C8] text-xs font-bold text-[#1F1A17] transition shadow-xs cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5 text-[#C7431F]" />
                      <span>+ Build Custom Option First</span>
                    </button>
                  </div>
                </div>
              ) : (
                /* Generated Strategy Options & Downstream Blueprints */
                <>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between flex-wrap gap-3">
                      <div>
                        <h3 className="font-['Bricolage_Grotesque'] text-xl font-bold">
                          Comparative Campaign Strategy Options
                        </h3>
                        <p className="text-xs text-[#6B625A]">
                          Select your preferred execution strategy. Tailored to ${customBudget.toLocaleString()} over {customDays} days with {customSubGoals.length} sub-goals.
                        </p>
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* View Mode Toggle: Compact vs Detailed */}
                        <div className="flex items-center gap-1 p-1 rounded-xl bg-[#F1EADF] text-xs">
                          <button
                            type="button"
                            onClick={() => setStrategyViewMode("compact")}
                            className={`px-3 py-1 rounded-lg font-bold transition cursor-pointer ${
                              strategyViewMode === "compact"
                                ? "bg-white text-[#1F1A17] shadow-xs"
                                : "text-[#6B625A] hover:text-[#1F1A17]"
                            }`}
                          >
                            Compact View
                          </button>
                          <button
                            type="button"
                            onClick={() => setStrategyViewMode("detailed")}
                            className={`px-3 py-1 rounded-lg font-bold transition cursor-pointer ${
                              strategyViewMode === "detailed"
                                ? "bg-white text-[#1F1A17] shadow-xs"
                                : "text-[#6B625A] hover:text-[#1F1A17]"
                            }`}
                          >
                            Detailed Breakdown
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            setAgentOpen(true);
                            pushAgent(
                              "I'm ready to customize your strategy! Just tell me what you want to change (e.g. 'Set budget to $25k', 'Make it 45 days', 'Add sub-goal: sign 30 enterprise clients', or 'Switch to Option B'). No forms needed!"
                            );
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#FAF6EF] hover:bg-[#F1EADF] text-[#C7431F] border border-[#E1D7C8] text-xs font-bold transition shadow-xs cursor-pointer"
                        >
                          <Bot className="w-3.5 h-3.5" />
                          <span>Customize via AI</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setIsCustomOptionModalOpen(true)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#1F1A17] hover:bg-black text-white text-xs font-bold transition shadow-xs cursor-pointer"
                        >
                          <Plus className="w-3.5 h-3.5 text-[#E1D7C8]" />
                          <span>+ Make Custom Option</span>
                        </button>
                      </div>
                    </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {(strategyBrief?.campaign_options ?? []).map((opt) => {
                    const isSelected = selectedOptionId === opt.option_id;
                    const isExpanded = strategyViewMode === "detailed" || expandedOptionIds.has(opt.option_id);

                    return (
                      <div
                        key={opt.option_id}
                        onClick={() => handleRecalculateBudget(customBudget, opt.option_id)}
                        className={`rounded-2xl border p-5 transition-all cursor-pointer flex flex-col justify-between space-y-4 ${
                          isSelected
                            ? "bg-white border-[#C7431F] shadow-md ring-2 ring-[#C7431F]/15"
                            : "bg-white border-[#E1D7C8] hover:border-[#D3C6B3] shadow-xs"
                        }`}
                      >
                        <div className="space-y-3.5">
                          {/* Header row with badge & selector */}
                          <div className="flex items-center justify-between">
                            <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                              opt.option_id.startsWith("opt_custom")
                                ? "bg-[#EAE4F8] text-[#5B32A8] border border-[#D5C7F2]"
                                : opt.recommended
                                ? "bg-[#FDF1EB] text-[#C7431F] border border-[#F3CFC0]"
                                : "bg-[#FAF6EF] text-[#6B625A] border border-[#E1D7C8]"
                            }`}>
                              {opt.option_id.startsWith("opt_custom") ? "🛠️ Custom Option" : opt.recommended ? "★ Recommended" : opt.theme}
                            </span>
                            <div className={`w-5 h-5 rounded-full border flex items-center justify-center transition ${
                              isSelected
                                ? "border-[#C7431F] bg-[#C7431F] text-white"
                                : "border-[#D3C6B3] bg-white"
                            }`}>
                              {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                            </div>
                          </div>

                          {/* Title & Tagline */}
                          <div>
                            <h4 className="font-['Bricolage_Grotesque'] text-base font-bold text-[#1F1A17]">
                              {opt.title}
                            </h4>
                            <p className="text-xs text-[#6B625A] mt-0.5 leading-relaxed">
                              {opt.tagline}
                            </p>
                          </div>

                          {/* Outcome Metrics Bar (4 Micro-Pills) */}
                          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                            <div className="p-2 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                              <span className="text-[#8A8176] block text-[9px] uppercase font-bold">Projected ROI</span>
                              <span className="font-bold text-[#256545]" title={"basis" in opt.prediction ? opt.prediction.basis : undefined}>{opt.prediction.projected_roi ?? "Needs sales data"}</span>
                            </div>
                            <div className="p-2 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                              <span className="text-[#8A8176] block text-[9px] uppercase font-bold">Est. CAC</span>
                              <span className="font-bold text-[#1F1A17]" title={"basis" in opt.prediction ? opt.prediction.basis : undefined}>{opt.prediction.projected_cac ?? "Set by first test"}</span>
                            </div>
                            <div className="p-2 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                              <span className="text-[#8A8176] block text-[9px] uppercase font-bold">Velocity</span>
                              <span className="font-bold text-[#1F1A17]">{opt.prediction.conversion_velocity ?? "—"}</span>
                            </div>
                            <div className="p-2 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                              <span className="text-[#8A8176] block text-[9px] uppercase font-bold">Risk Level</span>
                              <span className={`font-bold ${
                                opt.prediction.risk_level === "Low"
                                  ? "text-[#256545]"
                                  : opt.prediction.risk_level === "High"
                                  ? "text-[#C7431F]"
                                  : "text-[#8A4F08]"
                              }`}>
                                {opt.prediction.risk_level} Risk
                              </span>
                            </div>
                          </div>

                          {/* Budget Allocation Summary */}
                          <div className="p-2 rounded-xl bg-[#FAF6EE] border border-[#EFE7DB] text-[11px]">
                            <span className="text-[10px] font-bold text-[#8A8176] uppercase block mb-0.5">Budget Split:</span>
                            <span className="text-[#4A4239] font-medium leading-snug">{opt.budget_allocation_summary}</span>
                          </div>

                          {/* Compact Strategy Highlights (The 3-Second Scan) */}
                          <div className="space-y-1.5 text-xs pt-1">
                            {opt.advantages[0] && (
                              <div className="flex items-start gap-1.5 text-[#2E2822]">
                                <span className="text-[#256545] font-bold shrink-0">✓</span>
                                <span className="text-[11px] font-medium leading-tight line-clamp-2">{opt.advantages[0]}</span>
                              </div>
                            )}
                            {opt.promotion_means?.[0] && (
                              <div className="flex items-start gap-1.5 text-[#2E2822]">
                                <span className="text-[#C7431F] font-bold shrink-0">⚡</span>
                                <span className="text-[11px] font-medium leading-tight line-clamp-2">{opt.promotion_means[0]}</span>
                              </div>
                            )}
                            {opt.disadvantages[0] && (
                              <div className="flex items-start gap-1.5 text-[#6B625A]">
                                <span className="text-[#C7431F] font-bold shrink-0">△</span>
                                <span className="text-[11px] leading-tight line-clamp-1">{opt.disadvantages[0]}</span>
                              </div>
                            )}
                          </div>

                          {/* Expandable Strategic Details Section */}
                          {isExpanded && (
                            <div className="space-y-3 pt-3 border-t border-[#EFE7DB] animate-fade-in text-xs">
                              {/* Full Advantages */}
                              <div className="space-y-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#256545] block">
                                  All Advantages (Pros):
                                </span>
                                <ul className="space-y-1 text-[#2E2822]">
                                  {opt.advantages.map((adv, aIdx) => (
                                    <li key={aIdx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                      <span className="text-[#256545] font-bold shrink-0">✓</span>
                                      <span>{adv}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Full Disadvantages */}
                              <div className="space-y-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#8F2F14] block">
                                  Trade-offs & Limitations:
                                </span>
                                <ul className="space-y-1 text-[#6B625A]">
                                  {opt.disadvantages.map((dis, dIdx) => (
                                    <li key={dIdx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                      <span className="text-[#C7431F] font-bold shrink-0">△</span>
                                      <span>{dis}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Constraints */}
                              <div className="space-y-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#8A8176] block">
                                  Campaign Constraints:
                                </span>
                                <ul className="space-y-1 text-[#6B625A]">
                                  {opt.constraints.map((con, cIdx) => (
                                    <li key={cIdx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                      <span className="text-[#8A8176] font-bold shrink-0">⏱</span>
                                      <span>{con}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Exploited Opportunities */}
                              <div className="space-y-1">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#A9381A] block">
                                  Exploited Openings:
                                </span>
                                <ul className="space-y-1 text-[#6B625A]">
                                  {opt.opportunities.map((opp, oIdx) => (
                                    <li key={oIdx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                      <span className="text-[#C7431F] font-bold shrink-0">★</span>
                                      <span>{opp}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              {/* Suggested Channels */}
                              {opt.suggested_channels && opt.suggested_channels.length > 0 && (
                                <div className="space-y-1 pt-1.5">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#1F1A17] block">
                                    Suggested Channels:
                                  </span>
                                  <div className="flex flex-wrap gap-1">
                                    {opt.suggested_channels.map((ch, chIdx) => (
                                      <span key={chIdx} className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-[#F1EADF] text-[#4A4239]">
                                        {ch}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Means of Promotion */}
                              {opt.promotion_means && opt.promotion_means.length > 0 && (
                                <div className="space-y-1 pt-1.5">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#C7431F] block">
                                    Promotion Offers & Collateral:
                                  </span>
                                  <ul className="space-y-1 text-[#2E2822]">
                                    {opt.promotion_means.map((pm, pmIdx) => (
                                      <li key={pmIdx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                        <span className="text-[#C7431F] font-bold shrink-0">⚡</span>
                                        <span>{pm}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Card Bottom: Expand Toggle & Selection CTA */}
                        <div className="space-y-2 pt-2 border-t border-[#EFE7DB]">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleOptionDetails(opt.option_id);
                            }}
                            className="w-full flex items-center justify-between py-1 text-xs font-bold text-[#C7431F] hover:text-[#A9381A] transition cursor-pointer"
                          >
                            <span className="flex items-center gap-1">
                              {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                              <span>{isExpanded ? "Collapse details" : "View full strategic breakdown"}</span>
                            </span>
                            <span className="text-[10px] text-[#8A8176] font-normal">
                              {isExpanded ? "Less" : "Pros, Cons & Constraints"}
                            </span>
                          </button>

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRecalculateBudget(customBudget, opt.option_id);
                            }}
                            className={`w-full py-2 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer ${
                              isSelected
                                ? "bg-[#C7431F] text-white"
                                : "bg-[#FAF6EF] hover:bg-[#F1EADF] text-[#1F1A17] border border-[#E1D7C8]"
                            }`}
                          >
                            {isSelected ? "✓ Active Strategy Selected" : "Select This Strategy"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Grounded plan: personas, readiness, tests, gates, listings, economics */}
              <StrategyPlanPanel brief={strategyBrief} />

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

                {/* Consolidated Active Channels & Means of Promotion */}
                {((strategyBrief?.suggested_channels && strategyBrief.suggested_channels.length > 0) ||
                  (strategyBrief?.promotion_means && strategyBrief.promotion_means.length > 0)) && (
                  <div className="pt-4 border-t border-[#F1EADF] grid grid-cols-1 md:grid-cols-2 gap-4">
                    {strategyBrief?.suggested_channels && strategyBrief.suggested_channels.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8A8176] block">
                          Suggested Distribution Channels
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {strategyBrief.suggested_channels.map((sc, scIdx) => (
                            <span
                              key={scIdx}
                              className="text-xs px-2.5 py-1 rounded-lg bg-[#FAF6EF] border border-[#EFE7DB] text-[#1F1A17] font-medium"
                            >
                              {sc}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {strategyBrief?.promotion_means && strategyBrief.promotion_means.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#C7431F] block">
                          Recommended Means of Promotion
                        </span>
                        <ul className="text-xs text-[#4A4239] space-y-1">
                          {strategyBrief.promotion_means.map((pm, pmIdx) => (
                            <li key={pmIdx} className="flex items-start gap-1.5">
                              <span className="text-[#C7431F] font-bold">⚡</span>
                              <span>{pm}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
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
                  {(strategyBrief?.target_metrics ?? []).map((m, idx) => (
                    <div
                      key={idx}
                      className={`bg-white rounded-xl border p-4 shadow-xs space-y-1.5 ${
                        m.is_sub_goal ? "border-[#C7431F]/40 bg-[#FFFDFB]" : "border-[#E1D7C8]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-[10px] font-bold uppercase text-[#8A8176] block truncate">{m.name}</span>
                        {m.is_sub_goal && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#FDF1EB] text-[#C7431F] shrink-0">
                            Sub-Goal
                          </span>
                        )}
                      </div>
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
                  {(strategyBrief?.channel_matrix ?? []).map((ch, idx) => (
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
                          Est. Spend: {formatMoney(ch.recommended_spend_usd, strategyBrief?.currency)}
                        </div>
                      )}
                      <p className="text-[11px] text-[#6B625A] line-clamp-2">{ch.rationale}</p>

                      {/* Payee Platform & Purchased Deliverables */}
                      {(ch.payee_platform || ch.purchased_inventory) && (
                        <div className="pt-2 border-t border-[#F1EADF] space-y-1">
                          {ch.payee_platform && (
                            <div className="text-[10px] text-[#4A4239]">
                              <strong className="text-[#1F1A17]">Recipient / Payee:</strong> {ch.payee_platform}
                            </div>
                          )}
                          {ch.purchased_inventory && (
                            <div className="text-[10px] text-[#6B625A] leading-snug">
                              <strong className="text-[#1F1A17]">What You Buy:</strong> {ch.purchased_inventory}
                            </div>
                          )}
                        </div>
                      )}

                      {ch.promotion_tactics && ch.promotion_tactics.length > 0 && (
                        <div className="pt-2 border-t border-[#F1EADF] space-y-1">
                          <span className="text-[9px] font-bold uppercase text-[#8A8176] block">
                            Promotion Tactics:
                          </span>
                          <ul className="text-[10px] text-[#4A4239] space-y-0.5">
                            {ch.promotion_tactics.map((tac, tIdx) => (
                              <li key={tIdx} className="flex items-start gap-1">
                                <span className="text-[#C7431F]">•</span>
                                <span className="leading-tight">{tac}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
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

              {/* Loop 2 & 3: Tactical Outreach & Dispatch Matrix (Who, Where, How, Budget & Duration) */}
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-[#C7431F]">
                      Merchant Go-To-Market Execution Blueprint
                    </span>
                    <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold mt-0.5">
                      Tactical Outreach Matrix: Who, Where, How, Budget & Duration
                    </h3>
                    <p className="text-xs text-[#6B625A]">
                      Actionable operational playbook mapping exact buyer ICPs, platforms, conversion hooks, allocated capital, and flight cadences.
                    </p>
                  </div>
                  <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-[#E4F2EA] text-[#256545] border border-[#256545]/20 flex items-center gap-1">
                    <Target className="w-3.5 h-3.5" /> 5-Dimension Dispatch Matrix
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(strategyBrief?.outreach_blueprint ?? []).map((play, pIdx) => (
                    <div
                      key={play.playbook_id || pIdx}
                      className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs flex flex-col justify-between space-y-4 hover:border-[#C7431F]/40 transition"
                    >
                      <div className="space-y-3">
                        {/* Header */}
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-sm text-[#1F1A17] flex items-center gap-1.5">
                            <Compass className="w-4 h-4 text-[#C7431F]" />
                            {play.channel_name}
                          </span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-[#FDF1EB] text-[#C7431F]">
                              {formatMoney(play.budget_allocation_usd, strategyBrief?.currency)} ({play.budget_share_pct}%)
                            </span>
                          </div>
                        </div>

                        {/* 1. WHO */}
                        <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] space-y-1">
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-[#1F1A17] flex items-center gap-1">
                            <Users className="w-3.5 h-3.5 text-[#C7431F]" />
                            1. WHO TO REACH OUT TO (Target ICP Profile)
                          </span>
                          <p className="text-xs text-[#3E362E] font-medium leading-relaxed">
                            {play.who_target_profile}
                          </p>
                        </div>

                        {/* 2. WHERE */}
                        <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] space-y-1">
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-[#1F1A17] flex items-center gap-1">
                            <Target className="w-3.5 h-3.5 text-[#256545]" />
                            2. WHERE TO REACH OUT (Platform & Placement)
                          </span>
                          <p className="text-xs text-[#3E362E] font-medium leading-relaxed">
                            {play.where_platform}
                          </p>
                        </div>

                        {/* 3. HOW */}
                        <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] space-y-1">
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-[#1F1A17] flex items-center gap-1">
                            <Sparkles className="w-3.5 h-3.5 text-[#C7431F]" />
                            3. HOW TO REACH OUT (Mechanism, Hook & Offer)
                          </span>
                          <p className="text-xs text-[#3E362E] font-medium leading-relaxed">
                            {play.how_mechanism}
                          </p>
                        </div>

                        {/* 4. DURATION & CADENCE */}
                        <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] space-y-1">
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-[#1F1A17] flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-[#6B625A]" />
                            4. FOR HOW LONG & CADENCE (Flight & Frequency)
                          </span>
                          <p className="text-xs text-[#3E362E] font-medium leading-relaxed">
                            {play.duration_and_cadence}
                          </p>
                        </div>
                      </div>

                      {/* Footer: Budget CPA + Assigned Subagent */}
                      <div className="pt-3 border-t border-[#F1EADF] flex flex-wrap items-center justify-between gap-2 text-[11px]">
                        <div className="flex items-center gap-1.5 text-[#256545] font-semibold">
                          <span>Target Benchmark:</span>
                          <span className="font-bold">{play.expected_cpa}</span>
                        </div>
                        <div className="flex items-center gap-1 text-[#8A8176]">
                          <Bot className="w-3.5 h-3.5 text-[#C7431F]" />
                          <span className="font-bold text-[#1F1A17]">{play.assigned_subagent}</span>
                        </div>
                      </div>
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

              {/* Loop 3: Autonomous Subagents Deployment Roster */}
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-[#C7431F]">
                      Autonomous Execution Workforce
                    </span>
                    <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold mt-0.5">
                      Specialized AI Subagents Roster
                    </h3>
                    <p className="text-xs text-[#6B625A]">
                      These autonomous agents substitute human agency retainers, media buyers, and copywriters—freeing internal team bandwidth without requiring employee payroll allocation.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-[#E4F2EA] text-[#256545] border border-[#256545]/20 flex items-center gap-1">
                      <Bot className="w-3.5 h-3.5" /> 6 Autonomous Agents Deployed
                    </span>
                    <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-[#FDF1EB] text-[#C7431F] border border-[#C7431F]/20">
                      ~90 hrs/wk Manual Labor Saved
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {(strategyBrief?.subagents_roster ?? []).map((agent, aIdx) => (
                    <div
                      key={agent.agent_id || aIdx}
                      className="bg-white rounded-2xl border border-[#E1D7C8] p-4 shadow-xs flex flex-col justify-between space-y-3"
                    >
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-[#FAF6EF] text-[#6B625A] font-mono">
                            {agent.agent_id}
                          </span>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#E4F2EA] text-[#256545] flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#256545] animate-pulse" />
                            {agent.status}
                          </span>
                        </div>

                        <h4 className="font-bold text-sm text-[#1F1A17] flex items-center gap-1.5">
                          <Bot className="w-4 h-4 text-[#C7431F]" />
                          {agent.name}
                        </h4>
                        <p className="text-xs text-[#4A4239] leading-snug">
                          {agent.role}
                        </p>

                        {/* Target Channels */}
                        {agent.target_channels && agent.target_channels.length > 0 && (
                          <div className="space-y-1 pt-1.5 border-t border-[#F1EADF]">
                            <span className="text-[9px] font-bold uppercase text-[#8A8176] block">
                              Assigned Channels:
                            </span>
                            <div className="flex flex-wrap gap-1">
                              {agent.target_channels.map((ch, chIdx) => (
                                <span key={chIdx} className="text-[10px] px-2 py-0.5 rounded bg-[#F7F4EE] text-[#4A4239]">
                                  {ch}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Deliverables */}
                        {agent.deliverables && agent.deliverables.length > 0 && (
                          <div className="space-y-1 pt-1.5 border-t border-[#F1EADF]">
                            <span className="text-[9px] font-bold uppercase text-[#8A8176] block">
                              Autonomous Deliverables:
                            </span>
                            <ul className="text-[11px] text-[#4A4239] space-y-0.5">
                              {agent.deliverables.map((deliv, dIdx) => (
                                <li key={deliv + dIdx} className="flex items-start gap-1">
                                  <span className="text-[#256545] font-bold">✓</span>
                                  <span>{deliv}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Hours saved footer */}
                      {agent.estimated_hours_saved && (
                        <div className="pt-2 border-t border-[#F1EADF] flex items-center justify-between text-[11px] text-[#8A8176]">
                          <span className="font-medium">Time Replaced:</span>
                          <span className="font-bold text-[#C7431F] text-right">{agent.estimated_hours_saved}</span>
                        </div>
                      )}
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
            </>
          )}

          {/* Custom Option Builder Modal */}
          {isCustomOptionModalOpen && (
            <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
              <div className="bg-white rounded-3xl border border-[#E1D7C8] max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 shadow-2xl space-y-5 animate-fade-up">
                {/* Header */}
                <div className="flex items-start justify-between gap-4 border-b border-[#F1EADF] pb-4">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#C7431F]">
                      Custom Strategy Architecture
                    </span>
                    <h3 className="font-['Bricolage_Grotesque'] text-xl font-bold text-[#1F1A17] mt-0.5">
                      Build Custom Campaign Strategy Option
                    </h3>
                    <p className="text-xs text-[#6B625A] mt-1">
                      Configure your bespoke tactical wedge, custom channel spend splits, and operational proof points.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsCustomOptionModalOpen(false)}
                    className="w-8 h-8 rounded-full border border-[#E1D7C8] flex items-center justify-center text-[#8A8176] hover:text-[#1F1A17] hover:bg-[#FAF6EF] transition cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Form Fields */}
                <div className="space-y-4">
                  {/* Title & Theme */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-[#1F1A17]">Option Title *</label>
                      <input
                        type="text"
                        value={customOptTitle}
                        onChange={(e) => setCustomOptTitle(e.target.value)}
                        placeholder="e.g. Option D: Founder-Led Direct Wedge"
                        className="w-full px-3.5 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs font-bold text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-[#1F1A17]">Strategic Theme *</label>
                      <input
                        type="text"
                        value={customOptTheme}
                        onChange={(e) => setCustomOptTheme(e.target.value)}
                        placeholder="e.g. Founder-Led Migration Concierge"
                        className="w-full px-3.5 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs font-bold text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                      />
                    </div>
                  </div>

                  {/* Tagline */}
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-[#1F1A17]">One-Line Pitch / Tagline *</label>
                    <input
                      type="text"
                      value={customOptTagline}
                      onChange={(e) => setCustomOptTagline(e.target.value)}
                      placeholder="e.g. Engage competitor switchers with zero-friction migration and guaranteed SLA."
                      className="w-full px-3.5 py-2 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                    />
                  </div>

                  {/* Channel Allocations Breakdown */}
                  <div className="space-y-2 pt-2 border-t border-[#F1EADF]">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#1F1A17]">
                        Channel Allocations & Budget Split (% of ${customBudget.toLocaleString()}):
                      </label>
                      <span
                        className={`text-[11px] font-bold ${
                          customOptChannels.reduce((sum, c) => sum + c.budget_percentage, 0) === 100
                            ? "text-[#256545]"
                            : "text-[#C7431F]"
                        }`}
                      >
                        Total: {customOptChannels.reduce((sum, c) => sum + c.budget_percentage, 0)}%
                        {customOptChannels.reduce((sum, c) => sum + c.budget_percentage, 0) === 100
                          ? " ✓"
                          : " (Must equal 100%)"}
                      </span>
                    </div>

                    <div className="space-y-2">
                      {customOptChannels.map((c, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-2 p-2.5 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]"
                        >
                          <input
                            type="text"
                            value={c.channel}
                            onChange={(e) => {
                              const next = [...customOptChannels];
                              next[idx].channel = e.target.value;
                              setCustomOptChannels(next);
                            }}
                            className="flex-1 px-2.5 py-1 rounded-lg border border-[#E1D7C8] bg-white text-xs font-semibold text-[#1F1A17]"
                            placeholder="Channel name..."
                          />
                          <div className="flex items-center gap-1 shrink-0">
                            <input
                              type="number"
                              min={0}
                              max={100}
                              value={c.budget_percentage}
                              onChange={(e) => {
                                const next = [...customOptChannels];
                                next[idx].budget_percentage = Number(e.target.value) || 0;
                                setCustomOptChannels(next);
                              }}
                              className="w-16 px-2 py-1 rounded-lg border border-[#E1D7C8] bg-white text-xs font-bold text-center text-[#1F1A17]"
                            />
                            <span className="text-xs font-bold text-[#8A8176]">%</span>
                          </div>
                          <span className="text-[11px] font-medium text-[#256545] w-24 text-right shrink-0">
                            ${Math.round((customBudget * c.budget_percentage) / 100).toLocaleString()}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              if (customOptChannels.length > 1) {
                                setCustomOptChannels(customOptChannels.filter((_, i) => i !== idx));
                              }
                            }}
                            className="text-[#8A8176] hover:text-[#C7431F] p-1 font-bold cursor-pointer"
                            title="Remove channel"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setCustomOptChannels([
                          ...customOptChannels,
                          { channel: "New Distribution Channel", budget_percentage: 10, rationale: "Custom tactical allocation" },
                        ]);
                      }}
                      className="text-[11px] font-bold text-[#C7431F] hover:underline pt-1 cursor-pointer flex items-center gap-1"
                    >
                      <Plus className="w-3 h-3" /> Add Channel
                    </button>
                  </div>

                  {/* Advantages & Disadvantages */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#F1EADF]">
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-[#1F1A17]">Strategic Advantages (1 per line)</label>
                      <textarea
                        rows={3}
                        value={customOptAdvantages}
                        onChange={(e) => setCustomOptAdvantages(e.target.value)}
                        placeholder="Direct relationship with early adopters&#10;Zero setup overhead"
                        className="w-full p-2.5 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-bold text-[#1F1A17]">Disadvantages / Trade-offs (1 per line)</label>
                      <textarea
                        rows={3}
                        value={customOptDisadvantages}
                        onChange={(e) => setCustomOptDisadvantages(e.target.value)}
                        placeholder="Requires founder bandwidth for demos&#10;Limited initial volume scale"
                        className="w-full p-2.5 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs text-[#1F1A17] focus:outline-none focus:border-[#C7431F]"
                      />
                    </div>
                  </div>

                  {/* Projected Metrics */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-[#F1EADF]">
                    <div className="space-y-1">
                      <label className="text-[11px] font-bold text-[#1F1A17]">Projected CAC</label>
                      <input
                        type="text"
                        value={customOptCAC}
                        onChange={(e) => setCustomOptCAC(e.target.value)}
                        placeholder="e.g. $450 - $750"
                        className="w-full px-3 py-1.5 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs font-semibold text-[#1F1A17]"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[11px] font-bold text-[#1F1A17]">Projected ROI</label>
                      <input
                        type="text"
                        value={customOptROI}
                        onChange={(e) => setCustomOptROI(e.target.value)}
                        placeholder="e.g. 3.8x - 4.5x Pipeline ROI"
                        className="w-full px-3 py-1.5 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs font-semibold text-[#1F1A17]"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[11px] font-bold text-[#1F1A17]">Risk Level</label>
                      <select
                        value={customOptRisk}
                        onChange={(e) => setCustomOptRisk(e.target.value as "Low" | "Medium" | "High")}
                        className="w-full px-3 py-1.5 rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] text-xs font-semibold text-[#1F1A17]"
                      >
                        <option value="Low">Low Risk</option>
                        <option value="Medium">Medium Risk</option>
                        <option value="High">High Risk</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Modal Footer */}
                <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#F1EADF]">
                  <button
                    type="button"
                    onClick={() => setIsCustomOptionModalOpen(false)}
                    className="px-4 py-2 rounded-xl border border-[#E1D7C8] bg-white hover:bg-[#FAF6EF] text-xs font-bold text-[#4A4239] transition cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={
                      !customOptTitle.trim() ||
                      customOptChannels.reduce((sum, c) => sum + c.budget_percentage, 0) !== 100
                    }
                    onClick={handleSaveCustomOption}
                    className="px-6 py-2 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-white text-xs font-bold transition shadow-xs cursor-pointer disabled:opacity-50"
                  >
                    Save & Activate Custom Strategy
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

          {/* STAGE 4: CONTENT — written from the approved strategy */}
          {stage === "content" && activeJobId && (
            <div className="max-w-[1080px] mx-auto space-y-6 animate-fade-up">
              <div className="border-b border-[#E1D7C8] pb-4">
                <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold">Campaign content</h1>
              </div>
              <ContentStudio
                jobId={activeJobId}
                strategyApproved={stratApproved || strategyBrief?.approval_status === "APPROVED_AND_DISPATCHED"}
                refreshKey={contentRefreshKey}
                onFocusAsset={setFocusedAssetId}
                onContinue={() => {
                  setMaxStep((prev) => Math.max(prev, 5));
                  setStage("schedule");
                }}
              />
            </div>
          )}

          {/* STAGE 5: SCHEDULE — approved assets; publishing needs connected channels */}
          {stage === "schedule" && activeJobId && (
            <div className="max-w-[1080px] mx-auto space-y-6 animate-fade-up">
              <div className="border-b border-[#E1D7C8] pb-4">
                <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold">Publishing schedule</h1>
              </div>
              <SchedulePanel jobId={activeJobId} onBackToContent={() => setStage("content")} refreshKey={contentRefreshKey} />
            </div>
          )}

          {/* STAGE 6: LIVE — results from published assets only */}
          {stage === "perf" && activeJobId && (
            <div className="max-w-[1080px] mx-auto space-y-6 animate-fade-up">
              <div className="border-b border-[#E1D7C8] pb-4">
                <h1 className="font-['Bricolage_Grotesque'] text-3xl font-extrabold">Live results</h1>
              </div>
              <LivePanel jobId={activeJobId} refreshKey={contentRefreshKey} />
            </div>
          )}
        </main>
      </div>

      {/* ─── STEP-AWARE AGENT CHAT & HITL ACTION ASSISTANT ─── */}
      {activeJobId && (
        <ChatWidget
          jobId={activeJobId}
          rivals={rivalsList}
          merchantName={productName || undefined}
          step={STAGE_SLUG[stage] ?? "research"}
          focusAssetId={focusedAssetId || undefined}
          isOpen={agentOpen}
          onOpenChange={setAgentOpen}
          initialDraft={draft}
          onOpenRival={(idx) => {
            if (rivalsList[idx]) setSelectedRival(rivalsList[idx]);
          }}
          onAction={runChatAction}
        />
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
              <div className="flex items-center gap-3.5">
                {selectedRival.logoUrl ? (
                  <div className="w-12 h-12 rounded-xl border border-[#E1D7C8] bg-white overflow-hidden flex items-center justify-center shrink-0 shadow-xs">
                    <img
                      src={selectedRival.logoUrl}
                      alt={selectedRival.name}
                      className="w-full h-full object-contain p-1"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = "none";
                        const parent = (e.target as HTMLElement).parentElement;
                        if (parent) {
                          parent.className = "w-12 h-12 rounded-xl text-white flex items-center justify-center font-bold text-sm shadow-xs bg-[#C7431F]";
                          parent.innerText = selectedRival.initials;
                        }
                      }}
                    />
                  </div>
                ) : (
                  <span className="w-12 h-12 rounded-xl bg-[#C7431F] text-white flex items-center justify-center font-bold text-sm shadow-xs">
                    {selectedRival.initials}
                  </span>
                )}
                <div>
                  <h2 className="font-['Bricolage_Grotesque'] text-2xl font-extrabold text-[#19191B]">
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

                  {selectedRival.productImageUrl && (
                    <div className="bg-white p-4 rounded-2xl border border-[#E1D7C8] space-y-2">
                      <span className="font-bold uppercase text-[11px] text-[#8A8176]">Flagship Product Visual</span>
                      <div className="w-full h-48 rounded-xl overflow-hidden bg-[#FAF6EF] flex items-center justify-center border border-[#EFE7DB]">
                        <img
                          src={selectedRival.productImageUrl}
                          alt={`${selectedRival.name} Product`}
                          className="w-full h-full object-contain p-2"
                        />
                      </div>
                    </div>
                  )}

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
                  {/* Growth Trajectory & Inflection Graph */}
                  <div className="bg-white p-5 rounded-2xl border border-[#E1D7C8] space-y-4 shadow-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-[#FAF6EF] text-[#C7431F] border border-[#E1D7C8]">
                          <TrendingUp className="w-4 h-4" />
                        </div>
                        <div>
                          <span className="font-bold text-xs text-[#1F1A17] block">
                            Growth Trajectory & Inflection Curve
                          </span>
                          <span className="text-[11px] text-[#8A8176]">
                            Breakout milestones, commercial scaling & valuation velocity
                          </span>
                        </div>
                      </div>
                      <span className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-[#FAF6EF] text-[#C7431F] border border-[#EFE7DB]">
                        {selectedRival.comp.leap_benchmark?.current_scale
                          ? "Category Leader"
                          : selectedRival.comp.employee_count || selectedRival.comp.funding
                          ? "Scaling Rival"
                          : "Wedge Benchmark"}
                      </span>
                    </div>

                    {/* SVG Trajectory Curve */}
                    <div className="relative w-full h-44 bg-gradient-to-b from-[#FFFDF9] to-[#FAF6EF] rounded-xl border border-[#EFE7DB] p-3 flex flex-col justify-between overflow-hidden">
                      {/* Gridlines */}
                      <div className="absolute inset-0 flex flex-col justify-between p-4 pointer-events-none opacity-30">
                        <div className="border-b border-dashed border-[#C7431F]/30 w-full" />
                        <div className="border-b border-dashed border-[#C7431F]/30 w-full" />
                        <div className="border-b border-dashed border-[#C7431F]/30 w-full" />
                      </div>

                      <svg className="w-full h-28 overflow-visible" viewBox="0 0 500 120" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="growthGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#C7431F" stopOpacity="0.25" />
                            <stop offset="100%" stopColor="#C7431F" stopOpacity="0.0" />
                          </linearGradient>
                        </defs>
                        <path
                          d="M 25 105 Q 150 95 240 65 T 475 15 L 475 115 L 25 115 Z"
                          fill="url(#growthGradient)"
                        />
                        <path
                          d="M 25 105 Q 150 95 240 65 T 475 15"
                          fill="none"
                          stroke="#C7431F"
                          strokeWidth="3"
                          strokeLinecap="round"
                        />
                        <circle cx="25" cy="105" r="5" fill="#FAF6EF" stroke="#C7431F" strokeWidth="2.5" />
                        <circle cx="160" cy="85" r="5" fill="#FAF6EF" stroke="#C7431F" strokeWidth="2.5" />
                        <circle cx="310" cy="48" r="5" fill="#FAF6EF" stroke="#C7431F" strokeWidth="2.5" />
                        <circle cx="475" cy="15" r="6" fill="#C7431F" stroke="#FAF6EF" strokeWidth="2" />
                      </svg>

                      {/* Timeline Labels Along X-Axis */}
                      <div className="grid grid-cols-4 text-center text-[10px] font-bold uppercase text-[#8A8176] tracking-wider z-10 pt-1">
                        <div>Inception</div>
                        <div>Wedge Fit</div>
                        <div>Expansion</div>
                        <div className="text-[#C7431F]">Current Scale</div>
                      </div>
                    </div>

                    {/* Milestone Cards Along Trajectory */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8] space-y-1">
                        <span className="text-[10px] uppercase font-bold text-[#8A8176] block">
                          Phase 1: Inception
                        </span>
                        <p className="font-bold text-xs text-[#1F1A17] truncate">
                          {selectedRival.comp.founded ? `Est. ${selectedRival.comp.founded}` : "Niche Genesis"}
                        </p>
                        <p className="text-[11px] text-[#6B625A] line-clamp-2">
                          {selectedRival.comp.headquarters || "Category market entry"}
                        </p>
                      </div>

                      <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8] space-y-1">
                        <span className="text-[10px] uppercase font-bold text-[#8A8176] block">
                          Phase 2: Wedge Fit
                        </span>
                        <p className="font-bold text-xs text-[#1F1A17] truncate">
                          {selectedRival.comp.product_name || "Core Solution"}
                        </p>
                        <p className="text-[11px] text-[#6B625A] line-clamp-2">
                          {selectedRival.comp.milestones?.[0] || "Targeted segment capture"}
                        </p>
                      </div>

                      <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#E1D7C8] space-y-1">
                        <span className="text-[10px] uppercase font-bold text-[#8A8176] block">
                          Phase 3: Leap Catalyst
                        </span>
                        <p className="font-bold text-xs text-[#1F1A17] truncate">
                          {selectedRival.comp.leap_benchmark?.leap_catalysts?.[0] ||
                            (selectedRival.comp.pricing_model ? `Tier: ${selectedRival.comp.pricing_model}` : "Commercial Rollout")}
                        </p>
                        <p className="text-[11px] text-[#6B625A] line-clamp-2">
                          {selectedRival.comp.leap_benchmark?.pricing_power_leap || "Monetization expansion"}
                        </p>
                      </div>

                      <div className="p-2.5 rounded-xl bg-[#FAF6EF] border border-[#C7431F]/30 bg-gradient-to-br from-[#FAF6EF] to-[#FDF1EB] space-y-1">
                        <span className="text-[10px] uppercase font-bold text-[#C7431F] block">
                          Phase 4: Market Peak
                        </span>
                        <p className="font-bold text-xs text-[#1F1A17] truncate">
                          {selectedRival.comp.employee_count || selectedRival.comp.annual_revenue || "Market Footprint"}
                        </p>
                        <p className="text-[11px] text-[#6B625A] line-clamp-2">
                          {selectedRival.comp.funding || "Category Benchmark"}
                        </p>
                      </div>
                    </div>
                  </div>

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

                  {!selectedRival.comp.leap_benchmark && (
                    <div className="bg-[#FAF6EF] p-4 rounded-xl border border-[#E1D7C8] text-center space-y-1">
                      <p className="text-xs font-semibold text-[#1F1A17]">
                        Baseline trajectory mapped from verified market footprint & scale
                      </p>
                      <p className="text-[11px] text-[#8A8176]">
                        Autonomous crawler continuously monitors for new filings, funding announcements, and client disclosures.
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
