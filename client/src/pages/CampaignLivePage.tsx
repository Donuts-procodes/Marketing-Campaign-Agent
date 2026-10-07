import { useState } from "react";
import { useParams } from "react-router-dom";
import { useCampaignStream } from "@/hooks/useCampaignStream";
import { fetchMoreCompetitors, reResearchCampaign } from "@/lib/api-client";
import { exportToCSV, printDashboardReport } from "@/lib/exportReport";
import { AppNavbar } from "@/components/dashboard/AppNavbar";
import { PastelBentoGrid } from "@/components/dashboard/PastelBentoGrid";
import { CompetitorComparisonBoard } from "@/components/dashboard/CompetitorComparisonBoard";
import { ActionablePlaybook } from "@/components/dashboard/ActionablePlaybook";
import { RightCalendarSidebar } from "@/components/dashboard/RightCalendarSidebar";
import { SWOTGrid } from "@/components/research/SWOTGrid";
import { DQSBadge } from "@/components/research/DQSBadge";
import { LiveConsole } from "@/components/pipeline/LiveConsole";
import { PipelineProgressLoader } from "@/components/pipeline/PipelineProgressLoader";
import { safeHref, cn } from "@/lib/utils";
import {
  Search,
  SlidersHorizontal,
  ExternalLink,
  Activity,
  RefreshCw,
  Download,
  Printer,
  X,
} from "lucide-react";

export function CampaignLivePage() {
  const { jobId } = useParams<{ jobId: string }>();

  const [activeTab, setActiveTab] = useState("dashboard");
  const [searchQuery, setSearchQuery] = useState("");
  const [showConsoleDrawer, setShowConsoleDrawer] = useState(false);
  const [isFindingMore, setIsFindingMore] = useState(false);
  const [isReResearching, setIsReResearching] = useState(false);
  const [findMoreError, setFindMoreError] = useState<string | null>(null);

  const { state, reconnect, applyReport } = useCampaignStream(jobId);

  const {
    connectionStatus,
    telemetryLogs,
    swotReport,
    error: streamError,
  } = state;

  const allCompetitors = swotReport?.competitors ?? [];
  const query = searchQuery.trim().toLowerCase();
  const matchedCompetitors = query
    ? allCompetitors.filter((c) =>
        [c.brand_name, c.product_name, c.pricing_model ?? "", ...c.core_claims, ...c.weaknesses_mined]
          .join(" ")
          .toLowerCase()
          .includes(query)
      )
    : allCompetitors;
  const competitorsToDisplay = matchedCompetitors.slice(0, 5);

  const isExecuting = connectionStatus !== "COMPLETED" && (!swotReport || allCompetitors.length === 0);

  const statusLine =
    connectionStatus === "COMPLETED"
      ? `Research run completed: ${allCompetitors.length} competitor(s) extracted with grounded evidence.`
      : connectionStatus === "ERROR"
        ? streamError ?? "The research run failed."
        : "Autonomous research agents actively crawling, extracting attributes, and verifying claims...";

  const handleFindMoreCompetitors = async () => {
    if (!jobId) return;
    setIsFindingMore(true);
    setFindMoreError(null);
    try {
      const res = await fetchMoreCompetitors(jobId);
      applyReport(res.swot_report);
      if (res.added_competitors.length === 0) {
        setFindMoreError("No additional competitors were found.");
      }
    } catch (err: unknown) {
      setFindMoreError(
        err instanceof Error ? err.message : "Failed to find more competitors"
      );
    } finally {
      setIsFindingMore(false);
    }
  };

  const handleReResearch = async () => {
    if (!jobId || isReResearching) return;
    setIsReResearching(true);
    setFindMoreError(null);
    try {
      reconnect(true);
      const res = await reResearchCampaign(jobId);
      applyReport(res.swot_report);
    } catch (err: unknown) {
      setFindMoreError(
        err instanceof Error ? err.message : "Failed to execute re-research"
      );
    } finally {
      setIsReResearching(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 w-full">
      {/* ── Fixed Top Navbar ─────────────────────────────────── */}
      <AppNavbar
        activeTab={activeTab}
        connectionStatus={connectionStatus}
        onReconnect={reconnect}
        onTabChange={(tab) => {
          setActiveTab(tab);
          if (tab === "telemetry") {
            setShowConsoleDrawer(true);
          } else if (tab === "playbook") {
            document.getElementById("playbook-section")?.scrollIntoView({ behavior: "smooth" });
          } else if (tab === "competitors") {
            document.getElementById("competitors-section")?.scrollIntoView({ behavior: "smooth" });
          } else if (tab === "agents" || tab === "framework") {
            document.getElementById("framework-section")?.scrollIntoView({ behavior: "smooth" });
          } else if (tab === "dashboard") {
            window.scrollTo({ top: 0, behavior: "smooth" });
          }
        }}
      />

      <div className="w-full max-w-7xl mx-auto pt-16 pb-12 px-4 sm:px-6 lg:px-8">
        {/* Report masthead for print */}
        <div className="print-only mb-4 pb-3 border-b border-zinc-400">
          <h1 className="text-lg font-bold">Market &amp; Competitor Intelligence Report</h1>
          <p className="text-xs mt-1">
            Generated {new Date().toLocaleString()}
            {swotReport?.competitors?.length
              ? ` · ${swotReport.competitors.length} competitors`
              : ""}
            {swotReport?.dqs_score != null
              ? ` · Data Quality Score ${(swotReport.dqs_score * 100).toFixed(0)}%`
              : ""}
            {swotReport?.assumptions_tagged ? " · contains tagged assumptions" : ""}
          </p>
        </div>

        {/* Live Zero to 100 Loader Screen while Autonomous Pipeline is Running */}
        {isExecuting ? (
          <PipelineProgressLoader
            logs={telemetryLogs}
            connectionStatus={connectionStatus}
            error={streamError}
            onViewLogs={() => setShowConsoleDrawer(true)}
            onRetry={() => reconnect(true)}
          />
        ) : (
          /* Main Work Area */
          <div className="flex flex-col lg:flex-row items-start gap-5 mt-4">
            <main className="flex-1 min-w-0 space-y-5">
              {/* Header + Search Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-200">
                <div>
                  <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900">
                    Market &amp; Competitor Intelligence Dashboard
                  </h1>
                  <div className="flex items-center gap-2 mt-1 text-xs text-zinc-500">
                    <span>{statusLine}</span>
                    <button
                      type="button"
                      onClick={() => setShowConsoleDrawer(true)}
                      className="font-medium text-zinc-900 hover:underline cursor-pointer"
                    >
                      View agent trace &rarr;
                    </button>
                  </div>
                </div>

                {/* Toolbar: Re-research + Quick Export Buttons + Filter Input */}
                <div className="no-print flex items-center flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleReResearch}
                    disabled={isReResearching || isFindingMore}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-white border border-zinc-300 hover:bg-zinc-50 text-zinc-800 transition disabled:opacity-50 cursor-pointer shadow-2xs shrink-0"
                    title="Re-run the entire market research agent and discovery loop"
                  >
                    <RefreshCw className={cn("w-3.5 h-3.5 text-zinc-600", isReResearching && "animate-spin text-zinc-900")} />
                    <span>{isReResearching ? "Re-researching..." : "Re-research"}</span>
                  </button>

                  {swotReport && (
                    <>
                      <button
                        type="button"
                        onClick={() => exportToCSV(swotReport)}
                        className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-white border border-zinc-300 hover:bg-zinc-50 text-zinc-700 transition cursor-pointer shadow-2xs shrink-0"
                        title="Export competitor intelligence matrix to CSV"
                      >
                        <Download className="w-3.5 h-3.5 text-zinc-500" />
                        <span>Export CSV</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => printDashboardReport()}
                        className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold bg-white border border-zinc-300 hover:bg-zinc-50 text-zinc-700 transition cursor-pointer shadow-2xs shrink-0"
                        title="Print executive summary or save as PDF"
                      >
                        <Printer className="w-3.5 h-3.5 text-zinc-500" />
                        <span>Print / PDF</span>
                      </button>
                    </>
                  )}

                  <div className="w-full sm:w-60 flex items-center gap-2 bg-white border border-zinc-300 rounded-md px-3 py-1.5 shadow-2xs focus-within:border-zinc-500">
                    <Search className="w-4 h-4 text-zinc-400 shrink-0" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Filter competitors, pricing..."
                      className="bg-transparent text-xs text-zinc-900 outline-hidden flex-1 placeholder:text-zinc-400"
                    />
                    {query && (
                      <span className="text-[11px] font-mono text-zinc-400 shrink-0">
                        {competitorsToDisplay.length}/{allCompetitors.length}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* 4 Clean Metric Cards */}
              <PastelBentoGrid
                swotReport={swotReport}
                competitorCount={allCompetitors.length}
              />

              {/* Competitor Comparison Board Table */}
              <div id="competitors-section">
                <CompetitorComparisonBoard
                  competitors={competitorsToDisplay}
                  dynamicTaxonomy={swotReport?.dynamic_taxonomy}
                  onFindMore={handleFindMoreCompetitors}
                  isFindingMore={isFindingMore}
                  onReResearch={handleReResearch}
                  isReResearching={isReResearching}
                />
              </div>

              {/* Merchant Action Plan & Counter-Campaign Playbook */}
              {swotReport && competitorsToDisplay.length > 0 && (
                <div id="playbook-section">
                  <ActionablePlaybook
                    competitors={competitorsToDisplay}
                    positioningGap={swotReport.positioning_gap || swotReport.market_positioning_gap}
                    dynamicTaxonomy={swotReport.dynamic_taxonomy}
                  />
                </div>
              )}

              {findMoreError && (
                <div className="p-3 rounded bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                  {findMoreError}
                </div>
              )}

              {/* Dynamic Market Attributes & SWOT */}
              {swotReport && (
                <section id="framework-section" className="space-y-4 pt-2">
                  <div className="flex items-center justify-between pb-2 border-b border-zinc-200">
                    <div className="flex items-center gap-2">
                      <SlidersHorizontal className="w-4 h-4 text-zinc-700" />
                      <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-900">
                        Learned Parameter Framework &amp; Strategic SWOT
                      </h3>
                    </div>
                    <DQSBadge
                      score={swotReport.dqs_score}
                      assumptionsTagged={swotReport.assumptions_tagged}
                      diagnostics={swotReport.dqs_diagnostics}
                      sourceUrlsCount={swotReport.source_urls.length}
                    />
                  </div>

                  {/* Attribute Matrix Card */}
                  {swotReport.dynamic_taxonomy && (
                    <div className="p-4 rounded-lg bg-white border border-zinc-200 shadow-xs space-y-3">
                      <div className="flex items-center justify-between border-b border-zinc-100 pb-2">
                        <span className="text-xs font-bold text-zinc-900">
                          Dynamic Spec Parameter Taxonomy
                        </span>
                        {swotReport.attribute_density !== undefined && (
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-zinc-100 text-zinc-700 border border-zinc-200">
                            {Math.round(swotReport.attribute_density * 100)}% Spec Density
                          </span>
                        )}
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <span className="text-[11px] font-bold text-zinc-600 uppercase tracking-wider block">
                            Critical JTBD Drivers ({swotReport.dynamic_taxonomy.critical_jtbd_drivers.length})
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {swotReport.dynamic_taxonomy.critical_jtbd_drivers.map((d, i) => (
                              <span
                                key={i}
                                className="px-2.5 py-0.5 rounded text-xs font-medium bg-zinc-100 text-zinc-800 border border-zinc-200"
                              >
                                {d.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <span className="text-[11px] font-bold text-zinc-600 uppercase tracking-wider block">
                            Minor Specification Attributes ({swotReport.dynamic_taxonomy.minor_attributes.length})
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {swotReport.dynamic_taxonomy.minor_attributes.map((a, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded text-[11px] font-medium bg-zinc-50 text-zinc-600 border border-zinc-200"
                              >
                                {a.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* SWOT Grid */}
                  <SWOTGrid
                    swot={swotReport.swot || swotReport.swot_analysis}
                    positioningGap={swotReport.positioning_gap || swotReport.market_positioning_gap}
                  />

                  {/* Verified Research Sources */}
                  {swotReport.source_urls && swotReport.source_urls.length > 0 && (
                    <div className="p-4 rounded-lg bg-white border border-zinc-200 shadow-xs space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-900 block">
                          Verified Web Research Provenance ({swotReport.source_urls.length} URLs)
                        </span>
                        <span className="text-[11px] text-zinc-500 font-mono">
                          Grounding Evidence
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                        {swotReport.source_urls.map((url, i) => (
                          <a
                            key={i}
                            href={safeHref(url)}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-zinc-700 hover:text-zinc-900 bg-zinc-50 hover:bg-zinc-100 p-2 rounded border border-zinc-200 truncate flex items-center justify-between gap-1 transition"
                          >
                            <span className="truncate">{url}</span>
                            <ExternalLink className="w-3 h-3 shrink-0 text-zinc-400" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              )}
            </main>

            {/* Right Pipeline Info Sidebar */}
            <RightCalendarSidebar
              onReconnect={reconnect}
              onOpenLogs={() => setShowConsoleDrawer(true)}
              connectionStatus={connectionStatus}
            />
          </div>
        )}
      </div>

      {/* ── Telemetry Drawer Modal ──────────────────────────────── */}
      {showConsoleDrawer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="w-full max-w-3xl bg-white rounded-lg border border-zinc-300 p-5 shadow-2xl space-y-3">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-2.5">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-zinc-700" />
                <h3 className="text-sm font-bold text-zinc-900">Live Execution Telemetry &amp; Agent Logs</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowConsoleDrawer(false)}
                className="w-7 h-7 rounded hover:bg-zinc-100 flex items-center justify-center text-zinc-500 transition cursor-pointer"
              >
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
