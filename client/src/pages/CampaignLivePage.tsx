import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useCampaignStream } from "@/hooks/useCampaignStream";
import { ChatAction, applyReportEdits, fetchMoreCompetitors, reResearchCampaign } from "@/lib/api-client";
import { exportToCSV, printDashboardReport } from "@/lib/exportReport";
import { parseRunProgress } from "@/lib/runProgress";
import { RivalView, confidenceOf, keyFacts, toRivalView } from "@/lib/rivalMetrics";
import { cn } from "@/lib/utils";
import { AppNavbar, NavSection } from "@/components/dashboard/AppNavbar";
import { LiveConsole } from "@/components/pipeline/LiveConsole";
import { RunProgressView } from "@/components/intel/RunProgressView";
import { RivalCard } from "@/components/intel/RivalCard";
import { RivalDrawer } from "@/components/intel/RivalDrawer";
import { ComparisonTable } from "@/components/intel/ComparisonTable";
import { MarketBrief, MarketPanel } from "@/components/intel/MarketPanel";
import { SourcesPanel } from "@/components/intel/SourcesPanel";
import { ChatWidget } from "@/components/intel/ChatWidget";
import { Download, Loader2, Plus, Printer, RefreshCw, Search, Terminal, X } from "lucide-react";

const SECTIONS: NavSection[] = [
  { id: "overview", label: "Overview" },
  { id: "rivals", label: "Rivals" },
  { id: "compare", label: "Compare" },
  { id: "market", label: "Market" },
  { id: "sources", label: "Sources" },
];

// Literal class names so Tailwind generates them; the row always spans the full width.
const FACT_COLS: Record<number, string> = {
  1: "lg:grid-cols-1",
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
};

const TOOL_BTN =
  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-line bg-white hover:bg-[#FBF8F2] text-xs font-semibold text-ink transition disabled:opacity-50 disabled:cursor-not-allowed";

function SectionHeading({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2 mb-3">
      <div>
        <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
        {hint && <p className="text-xs text-ink-faint">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

export function CampaignLivePage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { state, reconnect, applyReport } = useCampaignStream(jobId);
  const { connectionStatus, telemetryLogs, swotReport: report, merchantContext, error: streamError } = state;

  const [activeSection, setActiveSection] = useState("overview");
  // The open profile lives in the URL (?rival=N), so a link can point straight at one rival.
  const [openRival, setOpenRival] = useState<number | null>(() => {
    const v = Number.parseInt(new URLSearchParams(window.location.search).get("rival") ?? "", 10);
    return Number.isFinite(v) && v >= 0 ? v : null;
  });
  useEffect(() => {
    const url = new URL(window.location.href);
    if (openRival == null) url.searchParams.delete("rival");
    else url.searchParams.set("rival", String(openRival));
    window.history.replaceState(window.history.state, "", url);
  }, [openRival]);
  const [logOpen, setLogOpen] = useState(false);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const [busy, setBusy] = useState<"more" | "rerun" | null>(null);
  const [notice, setNotice] = useState<{ tone: "info" | "error"; text: string } | null>(null);

  const merchantName = String(merchantContext?.product_name ?? "").trim();
  const category = String(merchantContext?.category ?? "").trim();
  const merchantPriceRaw = merchantContext?.price_usd;
  const merchantPrice =
    typeof merchantPriceRaw === "number" && Number.isFinite(merchantPriceRaw) ? `$${merchantPriceRaw.toLocaleString()}` : null;

  const rivals = useMemo(() => (report?.competitors ?? []).map(toRivalView), [report]);
  const facts = useMemo(() => keyFacts(rivals), [rivals]);
  const reserveCount = useMemo(() => parseRunProgress(telemetryLogs).reserveCount, [telemetryLogs]);
  const lastTimestamp = telemetryLogs[telemetryLogs.length - 1]?.timestamp;

  const visibleRivals = useMemo<RivalView[]>(() => {
    if (!deferredQuery) return rivals;
    return rivals.filter((r) =>
      [r.name, r.subtitle ?? "", r.host ?? "", r.priceLabel, ...r.claims, ...r.praise, ...r.complaints, ...r.ads]
        .join(" ")
        .toLowerCase()
        .includes(deferredQuery)
    );
  }, [rivals, deferredQuery]);

  const hasReport = !!report && rivals.length > 0;
  const showProgress = !hasReport && connectionStatus !== "COMPLETED";

  // Highlights the navbar section the reader is currently looking at.
  useEffect(() => {
    if (!hasReport) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [hasReport]);

  const goTo = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const handleFindMore = async () => {
    if (!jobId || busy) return;
    setBusy("more");
    setNotice(null);
    try {
      const res = await fetchMoreCompetitors(jobId);
      applyReport(res.swot_report);
      setNotice(
        res.added_competitors.length
          ? { tone: "info", text: `Added ${res.added_competitors.map((c) => c.brand_name).join(", ")}.` }
          : { tone: "info", text: "No further competitors in this market were found." }
      );
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Could not research more competitors." });
    } finally {
      setBusy(null);
    }
  };

  const handleRerun = async () => {
    if (!jobId || busy) return;
    setBusy("rerun");
    setNotice(null);
    try {
      reconnect(true);
      const res = await reResearchCampaign(jobId);
      applyReport(res.swot_report);
      setNotice({ tone: "info", text: "Research refreshed with the latest data." });
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Could not refresh the research." });
    } finally {
      setBusy(null);
    }
  };

  // Runs an action the merchant confirmed in the chat and returns a one-line result for its card.
  const runChatAction = async (action: ChatAction): Promise<string> => {
    if (!jobId) throw new Error("No research run is open.");
    if (busy) throw new Error("Another update is already running — try again when it finishes.");
    if (action.kind === "edit") {
      const res = await applyReportEdits(jobId, action.payload.edits ?? []);
      applyReport(res.swot_report);
      return res.applied.join(" · ") || "Report updated.";
    }
    if (action.kind === "research") {
      setBusy("more");
      try {
        const res = await fetchMoreCompetitors(jobId, action.payload.names ?? []);
        applyReport(res.swot_report);
        return res.added_competitors.length
          ? `Added ${res.added_competitors.map((c) => c.brand_name).join(", ")} to the report.`
          : "No new competitors could be researched.";
      } finally {
        setBusy(null);
      }
    }
    setBusy("rerun");
    try {
      reconnect(true);
      const res = await reResearchCampaign(jobId);
      applyReport(res.swot_report);
      return "The research was re-run and the report is up to date.";
    } finally {
      setBusy(null);
    }
  };

  const conf = report ? confidenceOf(report.dqs_score, report.assumptions_tagged) : null;
  const sourceCount = report?.source_urls?.length ?? 0;

  return (
    <div className="min-h-screen w-full bg-canvas text-ink font-sans">
      <AppNavbar
        sections={hasReport ? SECTIONS : undefined}
        activeTab={activeSection}
        onTabChange={goTo}
        connectionStatus={connectionStatus}
        onReconnect={() => reconnect(true)}
      />

      <div className="w-full max-w-7xl mx-auto pt-16 pb-16 px-4 sm:px-6 lg:px-8">
        {showProgress ? (
          <RunProgressView
            logs={telemetryLogs}
            connectionStatus={connectionStatus}
            error={streamError}
            productName={merchantName}
            onRetry={() => reconnect(true)}
            onOpenLog={() => setLogOpen(true)}
          />
        ) : !hasReport ? (
          <div className="max-w-lg mx-auto mt-20 text-center space-y-3 animate-fade-up">
            <h1 className="font-display text-2xl font-bold">No competitors were found</h1>
            <p className="text-sm text-ink-soft">
              The run finished without a usable shortlist. A broader category or a few known competitor names usually fixes
              this.
            </p>
            <div className="flex justify-center gap-2">
              <button type="button" onClick={handleRerun} disabled={!!busy} className={TOOL_BTN}>
                <RefreshCw className={cn("w-3.5 h-3.5", busy === "rerun" && "animate-spin")} /> Try again
              </button>
              <button type="button" onClick={() => setLogOpen(true)} className={TOOL_BTN}>
                <Terminal className="w-3.5 h-3.5" /> Agent log
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-10">
            {/* ── Overview ─────────────────────────────────────────── */}
            <section id="overview" className="scroll-mt-20 space-y-5 pt-6">
              <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-faint">
                    Competitor report{category ? ` · ${category}` : ""}
                  </p>
                  <h1 className="mt-1 font-display text-3xl sm:text-4xl font-bold tracking-tight">
                    {merchantName ? (
                      <>
                        {merchantName} <span className="text-ink-faint font-medium">vs.</span> {rivals.length} rival
                        {rivals.length === 1 ? "" : "s"}
                      </>
                    ) : (
                      `${rivals.length} rivals profiled`
                    )}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                    {conf && (
                      <button
                        type="button"
                        onClick={() => goTo("sources")}
                        className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border font-semibold", conf.tone)}
                        title="See what this confidence is based on"
                      >
                        <span className={cn("w-1.5 h-1.5 rounded-full", conf.dot)} />
                        {conf.label}
                      </button>
                    )}
                    <span>{sourceCount} pages read</span>
                    {lastTimestamp && (
                      <span>· {new Date(lastTimestamp).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>
                    )}
                  </div>
                </div>

                <div className="no-print flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 rounded-lg border border-line bg-white px-2.5 py-1.5 focus-within:border-ink/40 w-full sm:w-56">
                    <Search className="w-3.5 h-3.5 text-ink-faint shrink-0" />
                    <span className="sr-only">Filter rivals</span>
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Filter rivals, prices, quotes…"
                      className="flex-1 min-w-0 bg-transparent text-xs outline-none placeholder:text-ink-faint"
                    />
                    {query && (
                      <button type="button" onClick={() => setQuery("")} aria-label="Clear filter">
                        <X className="w-3.5 h-3.5 text-ink-faint hover:text-ink" />
                      </button>
                    )}
                  </label>
                  <button type="button" onClick={handleRerun} disabled={!!busy} className={TOOL_BTN} title="Run the research again">
                    <RefreshCw className={cn("w-3.5 h-3.5", busy === "rerun" && "animate-spin")} />
                    {busy === "rerun" ? "Refreshing…" : "Refresh"}
                  </button>
                  <button type="button" onClick={() => report && exportToCSV(report)} className={TOOL_BTN}>
                    <Download className="w-3.5 h-3.5" /> CSV
                  </button>
                  <button type="button" onClick={() => printDashboardReport(merchantName)} className={TOOL_BTN}>
                    <Printer className="w-3.5 h-3.5" /> PDF
                  </button>
                  <button type="button" onClick={() => setLogOpen(true)} className={TOOL_BTN} title="Agent log">
                    <Terminal className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {report?.sample_data && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-900">
                  Sample data — the server has no live search keys configured, so these rivals are illustrative.
                </div>
              )}

              {/* Key facts across all rivals: each opens the rival it is about */}
              <div className={cn("grid grid-cols-2 gap-2.5", FACT_COLS[Math.min(facts.length, 4)])}>
                {facts.slice(0, 4).map((f, i) => {
                  const clickable = f.rivalIndex != null;
                  return (
                    <button
                      key={f.id}
                      type="button"
                      disabled={!clickable}
                      onClick={() => clickable && setOpenRival(f.rivalIndex)}
                      className={cn(
                        "min-w-0 text-left rounded-2xl border border-line bg-white p-4 shadow-card animate-fade-up transition-all",
                        clickable ? "hover:shadow-lift hover:-translate-y-0.5" : "cursor-default"
                      )}
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <div className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">{f.label}</div>
                      <div className="mt-1 font-display text-lg font-bold text-ink truncate">{f.value}</div>
                      <div className="mt-0.5 text-[11px] text-ink-soft line-clamp-2">{f.detail}</div>
                    </button>
                  );
                })}
              </div>

              {report && <MarketBrief report={report} />}
            </section>

            {/* ── Rivals ───────────────────────────────────────────── */}
            <section id="rivals" className="scroll-mt-20">
              <SectionHeading
                title="Your rivals"
                hint={
                  deferredQuery
                    ? `${visibleRivals.length} of ${rivals.length} match “${query.trim()}”`
                    : "Picked for how closely they compete with you. Open any card for the full profile."
                }
              />
              {visibleRivals.length ? (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {visibleRivals.map((r) => (
                    <RivalCard key={r.key} rival={r} onOpen={setOpenRival} />
                  ))}
                </div>
              ) : (
                <p className="rounded-2xl border border-dashed border-line bg-white/50 p-8 text-center text-xs text-ink-faint">
                  No rival matches that filter.
                </p>
              )}

              <div className="no-print mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-dashed border-line bg-white/60 px-4 py-3">
                <p className="text-xs text-ink-soft">
                  {reserveCount
                    ? `${reserveCount} more competitors were found but not researched in depth.`
                    : "Want a wider view of the market?"}
                </p>
                <button type="button" onClick={handleFindMore} disabled={!!busy} className={TOOL_BTN}>
                  {busy === "more" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  {busy === "more" ? "Researching…" : "Research the next rivals"}
                </button>
              </div>
              {notice && (
                <p
                  role="status"
                  className={cn(
                    "mt-2 rounded-lg px-3 py-2 text-xs",
                    notice.tone === "error" ? "bg-rose-50 text-rose-800" : "bg-emerald-50 text-emerald-800"
                  )}
                >
                  {notice.text}
                </p>
              )}
            </section>

            {/* ── Compare ──────────────────────────────────────────── */}
            <section id="compare" className="scroll-mt-20">
              <SectionHeading title="Side by side" hint="Your product and every rival on the same measures." />
              <ComparisonTable
                rivals={visibleRivals}
                taxonomy={report?.dynamic_taxonomy}
                merchantName={merchantName}
                merchantPrice={merchantPrice}
                onOpen={setOpenRival}
              />
            </section>

            {/* ── Market ───────────────────────────────────────────── */}
            {report && (
              <section id="market" className="scroll-mt-20">
                <SectionHeading title="The market" hint="Strengths, weaknesses, openings and threats — each backed by what was found." />
                <MarketPanel report={report} />
              </section>
            )}

            {/* ── Sources ──────────────────────────────────────────── */}
            {report && (
              <section id="sources" className="scroll-mt-20">
                <SectionHeading title="Sources & confidence" hint="Every page the research used, grouped by website." />
                <SourcesPanel report={report} />
              </section>
            )}
          </div>
        )}
      </div>

      {hasReport && jobId && (
        <ChatWidget
          jobId={jobId}
          rivals={rivals}
          merchantName={merchantName}
          onOpenRival={setOpenRival}
          onAction={runChatAction}
        />
      )}

      <RivalDrawer
        rivals={rivals}
        openIndex={openRival}
        taxonomy={report?.dynamic_taxonomy}
        onClose={() => setOpenRival(null)}
        onNavigate={setOpenRival}
      />

      {logOpen && (
        <div className="no-print fixed inset-0 z-[70] flex items-center justify-center p-4 bg-ink/40 backdrop-blur-[2px] animate-fade-in" onClick={() => setLogOpen(false)}>
          <div
            className="w-full max-w-3xl rounded-2xl bg-white border border-line p-5 shadow-2xl space-y-3"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Agent log"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold">Agent log</h3>
              <button type="button" onClick={() => setLogOpen(false)} className="p-1.5 rounded-lg hover:bg-canvas" aria-label="Close log">
                <X className="w-4 h-4" />
              </button>
            </div>
            <LiveConsole logs={telemetryLogs} />
          </div>
        </div>
      )}
    </div>
  );
}
