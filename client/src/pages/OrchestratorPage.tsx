import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  Play,
  ChevronRight,
  Search,
  Users,
  Target,
  ShieldAlert,
  LayoutDashboard,
  Clock,
  UploadCloud,
  X,
  FileText,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Layers,
  Send,
  MapPin,
} from "lucide-react";
import { AppNavbar } from "@/components/dashboard/AppNavbar";
import { RecentSessions } from "@/components/dashboard/RecentSessions";
import { AutofillFields, CampaignInitPayload, PriorRunInfo } from "@/types/api";
import { autofillFromFiles, checkPriorRun, createCampaignJob, interpretQuery, uploadDossiers } from "@/lib/api-client";
import { cn } from "@/lib/utils";

// ─── Agent registry ──────────────────────────────────────────────────────────

type AgentStatus = "idle" | "queued" | "running" | "done" | "error";

interface AgentDef {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  color: string; // bg color token for the icon badge
  textColor: string;
  group: string;
}

const AGENTS: AgentDef[] = [
  {
    id: "market_research",
    label: "Market Research",
    description: "4-vector web search, competitor scrape & DQS validation",
    icon: Search,
    color: "bg-[#96BFE6]",
    textColor: "text-[#0F2D4A]",
    group: "Research",
  },
  {
    id: "audience_persona",
    label: "Audience Persona",
    description: "Psychographic profiling, ICP decomposition & objections",
    icon: Users,
    color: "bg-[#F8B4D9]",
    textColor: "text-[#3D102A]",
    group: "Persona",
  },
  {
    id: "campaign_strategy",
    label: "Campaign Strategy",
    description: "Positioning hierarchy, channel mix & budget allocation",
    icon: Target,
    color: "bg-[#FDE583]",
    textColor: "text-[#2D2306]",
    group: "Campaign",
  },
  {
    id: "media_generation",
    label: "Media Generation",
    description: "Multi-format ad creative variants, copy & visual assets",
    icon: Sparkles,
    color: "bg-[#96C87C]",
    textColor: "text-[#19350E]",
    group: "Media",
  },
  {
    id: "publishing",
    label: "Publishing",
    description: "Multi-platform scheduling, CMS dispatch & social sync",
    icon: Send,
    color: "bg-[#D2B4DE]",
    textColor: "text-[#3B154C]",
    group: "Publishing",
  },
];

const GROUPS = ["Research", "Persona", "Campaign", "Media", "Publishing"];

// ─── Component ───────────────────────────────────────────────────────────────

export function OrchestratorPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Intake inputs: dedicated product & category, target location, manual description, research goal, known competitors, and files
  const [productNameInput, setProductNameInput] = useState("");
  const [categoryInput, setCategoryInput] = useState("");
  const [targetGeographyInput, setTargetGeographyInput] = useState("");
  const [manualDescription, setManualDescription] = useState("");
  const [query, setQuery] = useState("");
  const [knownCompetitorsInput, setKnownCompetitorsInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isParsingFiles, setIsParsingFiles] = useState(false);
  const [parsedFields, setParsedFields] = useState<AutofillFields | null>(null);
  const [parseStatus, setParseStatus] = useState<"idle" | "parsing" | "success" | "error">("idle");
  // Which inputs the document autofill actually wrote into (drives the "Auto-filled" badge)
  const [autofilledKeys, setAutofilledKeys] = useState<Set<string>>(new Set());
  // The exact values autofill wrote, so a re-parse can refresh its own values but never a user edit
  const autofillOwnedRef = useRef<Record<string, string>>({});
  const [validationError, setValidationError] = useState<string | null>(null);
  const autofillPromiseRef = useRef<Promise<AutofillFields | null> | null>(null);

  // Interactive Great Minimum intake modal state
  const [isMissingModalOpen, setIsMissingModalOpen] = useState(false);
  const [missingRequirements, setMissingRequirements] = useState<string[]>([]);
  const [modalProductName, setModalProductName] = useState("");
  const [modalCategory, setModalCategory] = useState("");
  const [modalTargetGeography, setModalTargetGeography] = useState("");
  const [modalDescription, setModalDescription] = useState("");
  // LLM interpretation state: tracks whether the modal fields were AI-suggested
  const [isInterpreting, setIsInterpreting] = useState(false);
  const [aiSuggestedFields, setAiSuggestedFields] = useState<Set<string>>(new Set());

  // Cross-run memory: prior run check + run mode selection
  const [priorRun, setPriorRun] = useState<PriorRunInfo | null>(null);
  const [runMode, setRunMode] = useState<"fresh" | "update">("fresh");
  const priorRunCheckRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Agent toggle state
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(
    () => new Set(AGENTS.map((a) => a.id))
  );

  // Run state
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [isRunning, setIsRunning] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<"orchestrator" | "recent">("orchestrator");

  const toggleAgent = (id: string) => {
    setEnabledAgents((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const enableAll = () => setEnabledAgents(new Set(AGENTS.map((a) => a.id)));
  const enableGroup = (group: string) => {
    const ids = AGENTS.filter((a) => a.group === group).map((a) => a.id);
    setEnabledAgents((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  };

  // Background autofill: silently extracts fields from uploaded documents without displaying them
  const runBackgroundAutofill = (fileList: File[]): Promise<AutofillFields | null> => {
    if (!fileList.length) {
      applyAutofillToInputs(null);
      setParsedFields(null);
      setParseStatus("idle");
      setIsParsingFiles(false);
      const resolved = Promise.resolve<AutofillFields | null>(null);
      autofillPromiseRef.current = resolved;
      return resolved;
    }

    setIsParsingFiles(true);
    setParseStatus("parsing");

    const parsePromise = (async () => {
      try {
        const { fields } = await autofillFromFiles(fileList);
        setParsedFields(fields);
        setParseStatus("success");
        applyAutofillToInputs(fields);
        return fields;
      } catch {
        setParseStatus("error");
        return null;
      } finally {
        setIsParsingFiles(false);
      }
    })();

    autofillPromiseRef.current = parsePromise;
    return parsePromise;
  };

  /**
   * Writes extracted document values into the real form inputs.
   *
   * A field is only written when it is empty or still holds the value a previous parse put
   * there, so re-parsing after a file is added or removed refreshes its own values without
   * ever clobbering something the user typed. Passing null clears the values we own.
   */
  const applyAutofillToInputs = (fields: AutofillFields | null) => {
    const owned = autofillOwnedRef.current;
    const nextOwned: Record<string, string> = {};
    const applied = new Set<string>();

    const write = (
      key: string,
      incoming: string,
      setter: React.Dispatch<React.SetStateAction<string>>
    ) => {
      setter((cur) => {
        if (cur.trim() && cur !== owned[key]) return cur; // user-edited: never touch
        return incoming;
      });
      if (incoming) {
        nextOwned[key] = incoming;
        applied.add(key);
      }
    };

    write("product_name", fields?.product_name?.trim() || "", setProductNameInput);
    write("category", fields?.category?.trim() || "", setCategoryInput);
    write("target_geography", fields?.target_geography?.trim() || "", setTargetGeographyInput);
    write("primary_value_prop", fields?.primary_value_prop?.trim() || "", setManualDescription);
    write("known_competitors", fields?.known_competitors?.join(", ") || "", setKnownCompetitorsInput);
    write("goal", fields?.goal?.trim() || "", setQuery);

    autofillOwnedRef.current = nextOwned;
    setAutofilledKeys(applied);

    // The product name landed without an onChange, so the prior-run lookup needs an
    // explicit kick.
    if (nextOwned.product_name) {
      triggerPriorRunCheck(nextOwned.product_name, nextOwned.category || "");
    } else {
      setPriorRun(null);
    }
  };

  // File handling
  const addFiles = (incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const existingNames = new Set(files.map((f) => f.name));
    const newFiles = arr.filter((f) => !existingNames.has(f.name));
    if (!newFiles.length) return;
    const next = [...files, ...newFiles];
    setFiles(next);
    runBackgroundAutofill(next);
  };

  const removeFile = (name: string) => {
    const next = files.filter((f) => f.name !== name);
    setFiles(next);
    runBackgroundAutofill(next);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const CONVERSATIONAL_GOAL_RE =
    /^(i\s+(want|need|am|wish)|we\s+(want|need|are|wish)|how\s+to|looking\s+to|help\s+me|try(ing)?\s+to|increase|grow|attract)\b/i;
  const isConversational = (text: string) => {
    const s = text.trim();
    if (!s) return false;
    if (CONVERSATIONAL_GOAL_RE.test(s)) return true;
    const words = s.split(/\s+/);
    const firstPerson = /\b(i|my|we|our|me|us)\b/i;
    const actionVerbs = /\b(want|increase|grow|attract|get|need|scale|boost)\b/i;
    return words.length >= 4 && firstPerson.test(s) && actionVerbs.test(s);
  };

  // Debounced prior-run check: fires 800ms after the product name stops changing
  const triggerPriorRunCheck = (name: string, cat: string) => {
    if (priorRunCheckRef.current) clearTimeout(priorRunCheckRef.current);
    if (!name || name.length < 3 || isConversational(name)) {
      setPriorRun(null);
      return;
    }
    priorRunCheckRef.current = setTimeout(async () => {
      try {
        const info = await checkPriorRun(name, cat);
        setPriorRun(info.found ? info : null);
        if (info.found) setRunMode("update"); // default to update when prior run exists
      } catch {
        setPriorRun(null);
      }
    }, 800);
  };

  const evaluateMissingEssentials = (
    pName: string,
    cat: string,
    desc: string,
    fileCount: number,
    geo?: string
  ) => {
    const missing: string[] = [];
    if (!pName || isConversational(pName)) {
      missing.push("Product / Brand Name (e.g. Acme CRM, Linear, Zenith App)");
    }
    if (!cat || isConversational(cat)) {
      missing.push("Industry / Category (e.g. B2B Sales Automation, FinTech, E-Commerce)");
    }
    if (fileCount === 0 && (!desc || desc.length < 30 || isConversational(desc))) {
      missing.push("Product Description & Core Offering (what it does, audience, features, or upload a deck/PDF)");
    }
    if (!geo || isConversational(geo)) {
      missing.push("Target Location / Service Area (e.g. Delhi, Austin TX, United States, or Worldwide)");
    }
    return missing;
  };

  const resolvedProductName = productNameInput.trim() || parsedFields?.product_name?.trim() || "";
  const resolvedCategory = categoryInput.trim() || parsedFields?.category?.trim() || "";
  const resolvedTargetGeography = targetGeographyInput.trim() || parsedFields?.target_geography?.trim() || "";
  const resolvedDescription = manualDescription.trim() || parsedFields?.primary_value_prop?.trim() || "";

  const currentMissing = evaluateMissingEssentials(
    resolvedProductName,
    resolvedCategory,
    resolvedDescription,
    files.length,
    resolvedTargetGeography
  );
  const isGreatMinimumMet = currentMissing.length === 0;
  const canRun = enabledAgents.size > 0;

  const startCampaignRun = async (ctx: {
    productName: string;
    category: string;
    description: string;
    targetGeography?: string;
  }) => {
    setIsRunning(true);
    setErrorMsg(null);
    setValidationError(null);

    const initial: Record<string, AgentStatus> = {};
    enabledAgents.forEach((id) => (initial[id] = "queued"));
    setAgentStatuses(initial);

    // If background parsing is in-flight, await it so all extracted fields are captured
    let activeFields = parsedFields;
    if (isParsingFiles && autofillPromiseRef.current) {
      try {
        const awaited = await autofillPromiseRef.current;
        if (awaited) activeFields = awaited;
      } catch {
        // proceed gracefully
      }
    }

    const goal = query.trim() || activeFields?.goal || undefined;
    const manualCompetitors = knownCompetitorsInput
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);
    const docCompetitors = activeFields?.known_competitors || [];
    const mergedCompetitors = Array.from(new Set([...manualCompetitors, ...docCompetitors]));
    const finalGeo = (ctx.targetGeography || resolvedTargetGeography || "Worldwide").trim();

    const payload: CampaignInitPayload = {
      run_mode: priorRun?.found ? runMode : "fresh",
      merchant_context: {
        product_name: ctx.productName,
        category: ctx.category,
        target_geography: finalGeo,
        primary_value_prop:
          ctx.description ||
          (files.length > 0 ? `Context extracted from documents: ${files.map((f) => f.name).join(", ")}` : ctx.productName),
        goal: goal,
        price_usd: activeFields?.price_usd != null ? Number(activeFields.price_usd) : undefined,
        known_competitors: mergedCompetitors,
        existing_customer_profiles: activeFields?.existing_customer_profiles?.length ? activeFields.existing_customer_profiles : [],
      },
    };

    let jobId: string;
    try {
      jobId = (await createCampaignJob(payload)).job_id;
    } catch (err) {
      setErrorMsg(
        `Could not start run: ${err instanceof Error ? err.message : "orchestrator unreachable"}`
      );
      setIsRunning(false);
      setAgentStatuses({});
      return;
    }

    if (files.length) {
      try {
        await uploadDossiers(jobId, files);
      } catch {
        // Non-fatal: run continues without dossier context
      }
    }

    setIsRunning(false);
    navigate(`/campaigns/${encodeURIComponent(jobId)}`);
  };

  const handleRun = async () => {
    if (!canRun || isRunning) return;

    if (!isGreatMinimumMet) {
      // Seed modal with whatever the user already has
      const seedName = productNameInput && !isConversational(productNameInput) ? productNameInput : (parsedFields?.product_name || "");
      const seedCat = categoryInput && !isConversational(categoryInput) ? categoryInput : (parsedFields?.category || "");
      const seedGeo = targetGeographyInput && !isConversational(targetGeographyInput) ? targetGeographyInput : (parsedFields?.target_geography || "");
      const seedDesc = manualDescription || parsedFields?.primary_value_prop || "";
      setModalProductName(seedName);
      setModalCategory(seedCat);
      setModalTargetGeography(seedGeo);
      setModalDescription(seedDesc);
      setMissingRequirements(currentMissing);
      setAiSuggestedFields(new Set());
      setIsMissingModalOpen(true);

      // If there is free-form text but missing structured fields, call /interpret
      // to give the user AI-suggested values to confirm rather than typing from scratch.
      const inputText = [manualDescription, query].filter(Boolean).join("\n\n");
      const needsName = !seedName;
      const needsCategory = !seedCat;
      const needsGeo = !seedGeo;
      if (inputText.trim().length >= 10 && (needsName || needsCategory || needsGeo)) {
        setIsInterpreting(true);
        interpretQuery(inputText.trim())
          .then((res) => {
            const suggested = new Set<string>();
            if (needsName && res.fields.product_name) {
              setModalProductName(res.fields.product_name);
              suggested.add("productName");
            }
            if (needsCategory && res.fields.category) {
              setModalCategory(res.fields.category);
              suggested.add("category");
            }
            if (needsGeo && res.fields.target_geography) {
              setModalTargetGeography(res.fields.target_geography);
              suggested.add("targetGeography");
            }
            if (!seedDesc && res.fields.primary_value_prop) {
              setModalDescription(res.fields.primary_value_prop);
              suggested.add("description");
            }
            setAiSuggestedFields(suggested);
          })
          .catch(() => {
            // Silent failure — modal remains open with whatever seed values were set
          })
          .finally(() => setIsInterpreting(false));
      }
      return;
    }

    await startCampaignRun({
      productName: resolvedProductName,
      category: resolvedCategory,
      description: resolvedDescription,
      targetGeography: resolvedTargetGeography,
    });
  };

  const handleModalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const pName = modalProductName.trim() || parsedFields?.product_name?.trim() || "";
    const cat = modalCategory.trim() || parsedFields?.category?.trim() || "";
    const geo = modalTargetGeography.trim() || parsedFields?.target_geography?.trim() || "";
    const desc = modalDescription.trim() || parsedFields?.primary_value_prop?.trim() || "";

    const check = evaluateMissingEssentials(pName, cat, desc, files.length, geo);
    if (check.length > 0) {
      setMissingRequirements(check);
      return;
    }

    if (modalProductName.trim()) setProductNameInput(modalProductName.trim());
    if (modalCategory.trim()) setCategoryInput(modalCategory.trim());
    if (modalTargetGeography.trim()) setTargetGeographyInput(modalTargetGeography.trim());
    if (modalDescription.trim()) setManualDescription(modalDescription.trim());

    setIsMissingModalOpen(false);
    await startCampaignRun({
      productName: pName,
      category: cat,
      description: desc,
      targetGeography: geo,
    });
  };

  const totalEnabled = enabledAgents.size;
  const statusOf = (id: string): AgentStatus => agentStatuses[id] ?? "idle";

  return (
    <>
      <AppNavbar activeTab="dashboard" />

      <div className="w-full max-w-[1400px] mx-auto pt-20 pb-10 px-3 sm:px-5 lg:px-8">

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#19191B] flex items-center justify-center shadow-sm">
              <Bot className="w-5 h-5 text-[#F8B4D9]" />
            </div>
            <div>
              <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-zinc-500">
                Intelly Orchestrator
              </p>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-[#19191B] tracking-tight font-['Outfit',sans-serif]">
                Agent Control Center
              </h1>
            </div>
          </div>

          {/* View switcher */}
          <div className="flex items-center gap-1 p-1 rounded-2xl bg-[#EDE7D8] border border-[#D9D0C0]">
            <button
              type="button"
              onClick={() => setActiveView("orchestrator")}
              className={cn(
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all",
                activeView === "orchestrator"
                  ? "bg-[#19191B] text-white shadow-sm"
                  : "text-zinc-500 hover:text-[#19191B]"
              )}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              Orchestrator
            </button>
            <button
              type="button"
              onClick={() => setActiveView("recent")}
              className={cn(
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all",
                activeView === "recent"
                  ? "bg-[#19191B] text-white shadow-sm"
                  : "text-zinc-500 hover:text-[#19191B]"
              )}
            >
              <Clock className="w-3.5 h-3.5" />
              Recent Runs
            </button>
          </div>
        </div>

        {activeView === "recent" ? (
          <RecentSessions />
        ) : (
          <div className="flex gap-5 items-start">

            {/* ── Left: Goal / Data Input ─────────────────────────────── */}
            <div className="flex-1 min-w-0 space-y-4">

              {errorMsg && (
                <div className="p-4 rounded-2xl bg-[#FDE583]/40 border border-[#FDE583] text-[#2D2306] text-xs flex items-center gap-3">
                  <ShieldAlert className="w-4 h-4 shrink-0 text-amber-700" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {/* Input card */}
              <div className="bg-[#FAF6EE] rounded-[32px] border border-[#E3DCCB] shadow-md p-6 sm:p-8 space-y-5">
                <div className="flex items-center gap-2 border-b border-[#EDE7D8] pb-4">
                  <Sparkles className="w-4 h-4 text-[#19191B]" />
                  <h2 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
                    Campaign Brief
                  </h2>
                </div>

                {/* File upload drop zone */}
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    "relative flex flex-col items-center justify-center gap-2 px-6 py-7 rounded-2xl border-2 border-dashed cursor-pointer transition-all",
                    isDragging
                      ? "border-[#19191B] bg-[#EDE7D8]"
                      : "border-[#D9D0C0] bg-[#FFFDF9] hover:border-[#19191B] hover:bg-[#F5F0E8]"
                  )}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.txt,.md,.json,.csv,.xls,.xlsx"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files) addFiles(e.target.files);
                      e.target.value = "";
                    }}
                  />
                  <UploadCloud className={cn("w-7 h-7 transition-colors", isDragging ? "text-[#19191B]" : "text-zinc-400")} />
                  <div className="text-center">
                    <p className="text-xs font-bold text-[#19191B]">Drop files here or click to upload</p>
                    <p className="text-[11px] text-zinc-400 mt-0.5">PDF, DOCX, TXT, MD, JSON, CSV, XLS — optional context for the agents</p>
                  </div>
                </div>

                {/* Attached files list */}
                {files.length > 0 && (
                  <div className="space-y-2">
                    <div className="space-y-1.5">
                      {files.map((f) => (
                        <div key={f.name} className="flex items-center gap-2.5 px-3.5 py-2 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8]">
                          <FileText className="w-4 h-4 text-zinc-400 shrink-0" />
                          <span className="flex-1 text-xs font-medium text-[#19191B] truncate">{f.name}</span>
                          <span className="text-[11px] text-zinc-400 shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); removeFile(f.name); }}
                            className="p-0.5 rounded-full text-zinc-400 hover:text-rose-500 transition cursor-pointer"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>

                    {isParsingFiles && (
                      <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#EDE7D8]/60 text-[11px] font-medium text-zinc-600">
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-zinc-500 shrink-0" />
                        <span>Analyzing document context in background…</span>
                      </div>
                    )}
                    {!isParsingFiles && parseStatus === "success" && (
                      <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200/80 text-[11px] font-medium text-emerald-800">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>Document context analyzed & ready</span>
                      </div>
                    )}
                  </div>
                )}

                {/* 3-Column Grid: Structured Product / Brand, Category & Target Location */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                        <Target className="w-3.5 h-3.5 text-zinc-500" />
                        <span>Product / Brand Name</span>
                        <span className="text-rose-500">*</span>
                      </label>
                      {autofilledKeys.has("product_name") && (
                        <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          Auto-filled from doc
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={productNameInput}
                      onChange={(e) => {
                        setProductNameInput(e.target.value);
                        if (validationError) setValidationError(null);
                        triggerPriorRunCheck(e.target.value, categoryInput);
                      }}
                      placeholder={parsedFields?.product_name ? `e.g. ${parsedFields.product_name}` : "e.g. CloudScale CRM, Linear, Supabase"}
                      className="w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-zinc-500" />
                        <span>Category / Industry</span>
                        <span className="text-rose-500">*</span>
                      </label>
                      {autofilledKeys.has("category") && (
                        <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          Auto-filled from doc
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={categoryInput}
                      onChange={(e) => {
                        setCategoryInput(e.target.value);
                        if (validationError) setValidationError(null);
                        triggerPriorRunCheck(productNameInput, e.target.value);
                      }}
                      placeholder={parsedFields?.category ? `e.g. ${parsedFields.category}` : "e.g. B2B Sales CRM, Developer Analytics"}
                      className="w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
                    />
                  </div>

                  <div className="space-y-1.5 sm:col-span-2 lg:col-span-1">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                        <MapPin className="w-3.5 h-3.5 text-rose-500" />
                        <span>Target Location / Geography</span>
                        <span className="text-rose-500">*</span>
                      </label>
                      {autofilledKeys.has("target_geography") && (
                        <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          Auto-filled from doc
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={targetGeographyInput}
                      onChange={(e) => {
                        setTargetGeographyInput(e.target.value);
                        if (validationError) setValidationError(null);
                      }}
                      placeholder={parsedFields?.target_geography ? `e.g. ${parsedFields.target_geography}` : "e.g. Delhi, Austin TX, Worldwide"}
                      className="w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
                    />
                    <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                      {["Delhi", "India", "United States", "Worldwide"].map((preset) => (
                        <button
                          key={preset}
                          type="button"
                          onClick={() => {
                            setTargetGeographyInput(preset);
                            if (validationError) setValidationError(null);
                          }}
                          className={cn(
                            "px-2 py-0.5 rounded-md text-[10px] font-semibold border transition cursor-pointer",
                            targetGeographyInput.toLowerCase() === preset.toLowerCase()
                              ? "bg-[#19191B] text-white border-[#19191B]"
                              : "bg-white text-zinc-600 border-[#EDE7D8] hover:border-zinc-400"
                          )}
                        >
                          {preset}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Prior-run memory banner */}
                {priorRun?.found && (
                  <div className="p-4 rounded-2xl bg-indigo-50 border border-indigo-200 space-y-3">
                    <div className="flex items-start gap-2.5">
                      <Clock className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-indigo-900">Previous run found</p>
                        <p className="text-[11px] text-indigo-700 leading-relaxed mt-0.5">
                          Last researched{" "}
                          {priorRun.finished_at
                            ? new Date(priorRun.finished_at).toLocaleDateString(undefined, {
                                year: "numeric", month: "short", day: "numeric",
                              })
                            : "previously"}{" "}
                          — {priorRun.competitor_count ?? 0} competitors,{" "}
                          DQS {priorRun.dqs_score != null ? `${Math.round(priorRun.dqs_score * 100)}%` : "n/a"}
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setRunMode("update")}
                        className={cn(
                          "flex-1 py-2 px-3 rounded-xl text-xs font-bold border transition",
                          runMode === "update"
                            ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                            : "bg-white text-indigo-700 border-indigo-200 hover:border-indigo-400"
                        )}
                      >
                        Update — check what changed
                      </button>
                      <button
                        type="button"
                        onClick={() => setRunMode("fresh")}
                        className={cn(
                          "flex-1 py-2 px-3 rounded-xl text-xs font-bold border transition",
                          runMode === "fresh"
                            ? "bg-[#19191B] text-white border-[#19191B] shadow-sm"
                            : "bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400"
                        )}
                      >
                        Fresh — full rescan
                      </button>
                    </div>
                    {runMode === "update" && (
                      <p className="text-[10px] text-indigo-600 leading-relaxed px-1">
                        Searches only for changes since the last run, then merges new findings with existing data. Faster and cheaper.
                      </p>
                    )}
                    {runMode === "fresh" && (
                      <p className="text-[10px] text-zinc-500 leading-relaxed px-1">
                        Full rescan ignores previous data and discovers everything from scratch.
                      </p>
                    )}
                  </div>
                )}

                {/* Text Column 1: Manual Product / Offering Description */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-[#19191B]">
                      Product & Offering Description (Manual Context)
                    </label>
                    <span className="text-[11px] text-zinc-500 font-medium">
                      {files.length > 0 ? "Enriched by attached document" : "Required if no file uploaded"}
                    </span>
                  </div>
                  <textarea
                    rows={4}
                    value={manualDescription}
                    onChange={(e) => {
                      setManualDescription(e.target.value);
                      if (validationError) setValidationError(null);
                    }}
                    placeholder={`Describe your product or service in detail:\n• What does it do and who is it for?\n• Primary value proposition and pricing model\nE.g. "CloudScale CRM — B2B pipeline automation software for mid-market sales teams. Pricing: $49/user/month. Key value prop: zero-latency bi-directional sync with email and Slack."`}
                    className="w-full px-4 py-3 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition resize-none leading-relaxed"
                  />
                </div>

                {/* Text Column 2: Research Goal / Strategic Focus */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-[#19191B]">
                    Research Objectives & Capabilities Focus <span className="font-normal text-zinc-400">(optional)</span>
                  </label>
                  <textarea
                    rows={3}
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      if (validationError) setValidationError(null);
                    }}
                    placeholder={`What do you want the agents to research or achieve?\nE.g. "Find at least 5 direct competitors, analyze their pricing tiers, extract real customer complaints on Reddit/G2, and uncover exploitable positioning gaps."`}
                    className="w-full px-4 py-3 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition resize-none leading-relaxed"
                  />
                </div>

                {/* Text Column 3: Known Competitors (Optional) */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-[#19191B]">
                    Known Competitors <span className="font-normal text-zinc-400">(optional, comma-separated)</span>
                  </label>
                  <input
                    type="text"
                    value={knownCompetitorsInput}
                    onChange={(e) => setKnownCompetitorsInput(e.target.value)}
                    placeholder="E.g. HubSpot, Pipedrive, Close CRM, Apollo.io"
                    className="w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
                  />
                  <p className="text-[11px] text-zinc-400 pl-1">
                    Listed competitors will receive targeted search iterations to fill pricing and feature columns.
                  </p>
                </div>

                {/* Great Minimum Foundation Readiness */}
                <div className="p-3.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8] flex flex-wrap items-center justify-between gap-3 text-xs">
                  <span className="font-bold text-[#19191B] flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                    Great Minimum Foundation:
                  </span>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "px-2.5 py-1 rounded-full text-[11px] font-medium flex items-center gap-1",
                        resolvedProductName && !isConversational(resolvedProductName)
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                          : "bg-amber-50 text-amber-800 border border-amber-200"
                      )}
                    >
                      {resolvedProductName && !isConversational(resolvedProductName)
                        ? "✓ Product Name"
                        : "⚠️ Product Name required"}
                    </span>
                    <span
                      className={cn(
                        "px-2.5 py-1 rounded-full text-[11px] font-medium flex items-center gap-1",
                        resolvedCategory && !isConversational(resolvedCategory)
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                          : "bg-amber-50 text-amber-800 border border-amber-200"
                      )}
                    >
                      {resolvedCategory && !isConversational(resolvedCategory)
                        ? "✓ Category"
                        : "⚠️ Category required"}
                    </span>
                    <span
                      className={cn(
                        "px-2.5 py-1 rounded-full text-[11px] font-medium flex items-center gap-1",
                        resolvedTargetGeography && !isConversational(resolvedTargetGeography)
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                          : "bg-amber-50 text-amber-800 border border-amber-200"
                      )}
                    >
                      {resolvedTargetGeography && !isConversational(resolvedTargetGeography)
                        ? `✓ Location: ${resolvedTargetGeography}`
                        : "⚠️ Location required"}
                    </span>
                    <span
                      className={cn(
                        "px-2.5 py-1 rounded-full text-[11px] font-medium flex items-center gap-1",
                        files.length > 0 || (resolvedDescription.length >= 30 && !isConversational(resolvedDescription))
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                          : "bg-amber-50 text-amber-800 border border-amber-200"
                      )}
                    >
                      {files.length > 0
                        ? `✓ Document attached (${files.length})`
                        : resolvedDescription.length >= 30 && !isConversational(resolvedDescription)
                        ? "✓ Offering details"
                        : "⚠️ Description or File required"}
                    </span>
                  </div>
                </div>

                {/* Validation Gate Alert */}
                {validationError && (
                  <div className="p-4 rounded-2xl bg-amber-50 border border-amber-300 text-amber-900 text-xs space-y-1">
                    <div className="flex items-center gap-2 font-bold">
                      <AlertCircle className="w-4 h-4 text-amber-700 shrink-0" />
                      <span>Data Insufficient to Start Research</span>
                    </div>
                    <p className="leading-relaxed pl-6 text-amber-800">{validationError}</p>
                  </div>
                )}

                {/* Run button */}
                <button
                  type="button"
                  onClick={handleRun}
                  disabled={!canRun || isRunning}
                  className={cn(
                    "w-full py-4 px-6 rounded-full font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md",
                    !canRun || isRunning
                      ? "bg-zinc-200 text-zinc-400 cursor-not-allowed shadow-none"
                      : "bg-[#19191B] hover:bg-black text-white hover:scale-[1.01] cursor-pointer"
                  )}
                >
                  {isRunning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Initializing {totalEnabled} agent{totalEnabled !== 1 ? "s" : ""}...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-current" />
                      Run {totalEnabled} Agent{totalEnabled !== 1 ? "s" : ""}
                    </>
                  )}
                </button>
              </div>

              {/* Run progress (shown while running) */}
              {isRunning && (
                <div className="bg-[#FAF6EE] rounded-[28px] border border-[#E3DCCB] shadow-sm p-5 space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
                    Run Progress
                  </h3>
                  <div className="space-y-2">
                    {AGENTS.filter((a) => enabledAgents.has(a.id)).map((agent) => {
                      const status = statusOf(agent.id);
                      const Icon = agent.icon;
                      return (
                        <div
                          key={agent.id}
                          className="flex items-center gap-3 px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border border-[#EDE7D8]"
                        >
                          <div className={cn("w-7 h-7 rounded-full flex items-center justify-center shrink-0", agent.color, agent.textColor)}>
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className="flex-1 text-xs font-semibold text-[#19191B]">{agent.label}</span>
                          <StatusBadge status={status} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* ── Right: Agent Toggle Sidebar ─────────────────────────── */}
            <div className="w-72 shrink-0 space-y-3">
              <div className="bg-[#FAF6EE] rounded-[28px] border border-[#E3DCCB] shadow-md p-5 space-y-4">

                {/* Header */}
                <div className="flex items-center justify-between">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
                    Agents
                  </h2>
                  <span className="text-[11px] font-mono font-bold text-zinc-500">
                    {totalEnabled}/{AGENTS.length} on
                  </span>
                </div>

                {/* Quick-select presets */}
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={enableAll}
                    className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#19191B] text-white hover:bg-black transition cursor-pointer"
                  >
                    All
                  </button>
                  {GROUPS.map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => enableGroup(g)}
                      className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-[#EDE7D8] text-[#19191B] hover:bg-[#D9D0C0] transition cursor-pointer"
                    >
                      {g}
                    </button>
                  ))}
                </div>

                {/* Agent list grouped */}
                <div className="space-y-4">
                  {GROUPS.map((group) => {
                    const groupAgents = AGENTS.filter((a) => a.group === group);
                    return (
                      <div key={group} className="space-y-1.5">
                        <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-zinc-400 px-1">
                          {group}
                        </p>
                        {groupAgents.map((agent) => {
                          const Icon = agent.icon;
                          const enabled = enabledAgents.has(agent.id);
                          return (
                            <div
                              key={agent.id}
                              className={cn(
                                "flex items-center gap-3 px-3 py-2.5 rounded-2xl border cursor-pointer transition-all select-none",
                                enabled
                                  ? "bg-[#FFFDF9] border-[#D9D0C0] shadow-xs"
                                  : "bg-transparent border-transparent opacity-50 hover:opacity-70"
                              )}
                              onClick={() => toggleAgent(agent.id)}
                            >
                              <div
                                className={cn(
                                  "w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all",
                                  enabled ? cn(agent.color, agent.textColor) : "bg-zinc-200 text-zinc-400"
                                )}
                              >
                                <Icon className="w-3.5 h-3.5" />
                              </div>

                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-bold text-[#19191B] truncate">
                                  {agent.label}
                                </p>
                                <p className="text-[10px] text-zinc-400 truncate leading-tight mt-0.5">
                                  {agent.description}
                                </p>
                              </div>

                              {/* Toggle pill */}
                              <div
                                className={cn(
                                  "w-9 h-5 rounded-full flex items-center transition-all shrink-0",
                                  enabled ? "bg-[#19191B] justify-end" : "bg-zinc-300 justify-start"
                                )}
                              >
                                <div className="w-4 h-4 rounded-full bg-white mx-0.5 shadow-sm" />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Go to Agent Dashboards card */}
              <div className="bg-[#FAF6EE] rounded-[28px] border border-[#E3DCCB] shadow-md p-5 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
                  Agent Dashboards
                </h3>
                <p className="text-[11px] text-zinc-500 leading-relaxed">
                  Start a run first, then open its live dashboard to watch each agent in real time.
                </p>
                <button
                  type="button"
                  onClick={() => setActiveView("recent")}
                  className="w-full flex items-center justify-between px-4 py-3 rounded-2xl bg-[#19191B] text-white text-xs font-bold hover:bg-black transition cursor-pointer"
                >
                  <span>View Recent Runs</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Interactive Great Minimum Intake Modal */}
      {isMissingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-lg rounded-[28px] bg-[#FAF6EE] border border-[#E3DCCB] p-6 sm:p-7 shadow-2xl space-y-5 animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-2xl bg-amber-100 text-amber-800 border border-amber-200 shrink-0">
                <AlertCircle className="w-5 h-5 text-amber-700" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-[#19191B]">
                  Research Foundation Required
                </h3>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  To guarantee high-precision research (≥90% DQS) and discover at least 5 direct competitors, the agents need a concrete product anchor before starting.
                </p>
              </div>
            </div>

            {/* Missing items summary */}
            {missingRequirements.length > 0 && (
              <div className="p-3 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs space-y-1">
                <p className="font-bold">Missing essential data:</p>
                <ul className="list-disc list-inside space-y-0.5 text-[11px] text-rose-700">
                  {missingRequirements.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* AI Interpretation loading banner */}
            {isInterpreting && (
              <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-2xl bg-indigo-50 border border-indigo-200 text-indigo-800 text-xs font-medium">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500 shrink-0" />
                <span>AI is interpreting your input to suggest values…</span>
              </div>
            )}
            {!isInterpreting && aiSuggestedFields.size > 0 && (
              <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-2xl bg-violet-50 border border-violet-200 text-violet-800 text-xs font-medium">
                <Sparkles className="w-3.5 h-3.5 text-violet-500 shrink-0" />
                <span>AI suggested values based on your input — confirm or edit before launching.</span>
              </div>
            )}

            {/* Quick entry form */}
            <form onSubmit={handleModalSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-[#19191B]">
                    Product / Brand Name <span className="text-rose-500">*</span>
                  </label>
                  {aiSuggestedFields.has("productName") && (
                    <span className="text-[10px] font-semibold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-200">
                      AI suggested
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  value={modalProductName}
                  onChange={(e) => {
                    setModalProductName(e.target.value);
                    setAiSuggestedFields((prev) => { const next = new Set(prev); next.delete("productName"); return next; });
                  }}
                  placeholder="e.g. CloudScale CRM, Linear, Acme SaaS"
                  className={cn(
                    "w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-[#19191B] transition",
                    aiSuggestedFields.has("productName")
                      ? "border-violet-300 focus:border-violet-500"
                      : "border-[#EDE7D8] focus:border-[#19191B]"
                  )}
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-[#19191B]">
                    Category / Industry Domain <span className="text-rose-500">*</span>
                  </label>
                  {aiSuggestedFields.has("category") && (
                    <span className="text-[10px] font-semibold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-200">
                      AI suggested
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  value={modalCategory}
                  onChange={(e) => {
                    setModalCategory(e.target.value);
                    setAiSuggestedFields((prev) => { const next = new Set(prev); next.delete("category"); return next; });
                  }}
                  placeholder="e.g. B2B Sales Automation, Developer Tool, FinTech"
                  className={cn(
                    "w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-[#19191B] transition",
                    aiSuggestedFields.has("category")
                      ? "border-violet-300 focus:border-violet-500"
                      : "border-[#EDE7D8] focus:border-[#19191B]"
                  )}
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-rose-500" />
                    <span>Target Location / Geography <span className="text-rose-500">*</span></span>
                  </label>
                  {aiSuggestedFields.has("targetGeography") && (
                    <span className="text-[10px] font-semibold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-200">
                      AI suggested
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  value={modalTargetGeography}
                  onChange={(e) => {
                    setModalTargetGeography(e.target.value);
                    setAiSuggestedFields((prev) => { const next = new Set(prev); next.delete("targetGeography"); return next; });
                  }}
                  placeholder="e.g. Delhi, Austin TX, United States, or Worldwide"
                  className={cn(
                    "w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-[#19191B] transition",
                    aiSuggestedFields.has("targetGeography")
                      ? "border-violet-300 focus:border-violet-500"
                      : "border-[#EDE7D8] focus:border-[#19191B]"
                  )}
                />
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  {["Delhi", "India", "United States", "Worldwide"].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => {
                        setModalTargetGeography(preset);
                        setAiSuggestedFields((prev) => { const next = new Set(prev); next.delete("targetGeography"); return next; });
                      }}
                      className={cn(
                        "px-2 py-0.5 rounded-md text-[10px] font-semibold border transition cursor-pointer",
                        modalTargetGeography.toLowerCase() === preset.toLowerCase()
                          ? "bg-[#19191B] text-white border-[#19191B]"
                          : "bg-white text-zinc-600 border-[#EDE7D8] hover:border-zinc-400"
                      )}
                    >
                      {preset}
                    </button>
                  ))}
                </div>
              </div>

              {files.length === 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-[#19191B]">
                      Product Description & Core Offering <span className="text-rose-500">*</span>
                    </label>
                    {aiSuggestedFields.has("description") && (
                      <span className="text-[10px] font-semibold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full border border-violet-200">
                        AI suggested
                      </span>
                    )}
                  </div>
                  <textarea
                    rows={3}
                    value={modalDescription}
                    onChange={(e) => {
                      setModalDescription(e.target.value);
                      setAiSuggestedFields((prev) => { const next = new Set(prev); next.delete("description"); return next; });
                    }}
                    placeholder="Briefly describe what your product does, who uses it, key features, or pricing model..."
                    className={cn(
                      "w-full px-4 py-2.5 rounded-2xl bg-[#FFFDF9] border text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-[#19191B] transition resize-none leading-relaxed",
                      aiSuggestedFields.has("description")
                        ? "border-violet-300 focus:border-violet-500"
                        : "border-[#EDE7D8] focus:border-[#19191B]"
                    )}
                  />
                </div>
              )}

              {/* Action buttons */}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setIsMissingModalOpen(false); setAiSuggestedFields(new Set()); }}
                  className="px-4 py-2.5 rounded-full text-xs font-semibold text-zinc-600 hover:text-[#19191B] transition cursor-pointer"
                >
                  Cancel / Edit on Page
                </button>
                <button
                  type="submit"
                  className="px-5 py-2.5 rounded-full text-xs font-bold bg-[#19191B] hover:bg-black text-white shadow-sm transition flex items-center gap-1.5 cursor-pointer"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  Confirm & Launch Research
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Status badge sub-component ──────────────────────────────────────────────

function StatusBadge({ status }: { status: AgentStatus }) {
  const map: Record<AgentStatus, { label: string; cls: string }> = {
    idle: { label: "Idle", cls: "bg-zinc-100 text-zinc-500 border-zinc-200" },
    queued: { label: "Queued", cls: "bg-[#FDE583]/60 text-[#2D2306] border-[#FDE583] animate-pulse" },
    running: { label: "Running", cls: "bg-[#96BFE6]/40 text-[#0F2D4A] border-[#96BFE6] animate-pulse" },
    done: { label: "Done", cls: "bg-[#96C87C]/40 text-[#19350E] border-[#96C87C]" },
    error: { label: "Error", cls: "bg-rose-100 text-rose-700 border-rose-200" },
  };
  const { label, cls } = map[status];
  return (
    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border shrink-0", cls)}>
      {label}
    </span>
  );
}
