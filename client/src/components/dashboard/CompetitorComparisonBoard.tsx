import React, { useState } from "react";
import { CompetitorProfile, DynamicParameterTaxonomy } from "@/types/research";
import {
  ExternalLink,
  Megaphone,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
} from "lucide-react";
import { pricingLabel, safeHref, cn } from "@/lib/utils";

interface CompetitorComparisonBoardProps {
  competitors: CompetitorProfile[];
  dynamicTaxonomy?: DynamicParameterTaxonomy;
  onFindMore?: () => void;
  isFindingMore?: boolean;
  onReResearch?: () => void;
  isReResearching?: boolean;
}

export const CompetitorComparisonBoard: React.FC<CompetitorComparisonBoardProps> = ({
  competitors,
  dynamicTaxonomy,
  onFindMore,
  isFindingMore = false,
  onReResearch,
  isReResearching = false,
}) => {
  const [selectedCompId, setSelectedCompId] = useState<number>(0);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"executive" | "specs">("executive");

  const criticalDrivers = dynamicTaxonomy?.critical_jtbd_drivers || [];
  const active = competitors[selectedCompId] || competitors[0];

  const toggleRow = (idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedRow((prev) => (prev === idx ? null : idx));
    setSelectedCompId(idx);
  };

  return (
    <div className="space-y-4">
      {/* ── Table Controls Bar ─────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-zinc-200">
        <div>
          <h2 className="text-base font-bold text-zinc-900 tracking-tight flex items-center gap-2">
            <span>Competitor Comparison &amp; Grounding Matrix</span>
            <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-zinc-100 text-zinc-700 border border-zinc-200">
              {competitors.length} tracked
            </span>
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Structured extraction of verified pricing, claims, customer complaints, ad copy hooks, and web citations.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {/* View Mode Toggle */}
          <div className="inline-flex rounded-md border border-zinc-200 bg-zinc-100 p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setViewMode("executive")}
              className={cn(
                "px-2.5 py-1 rounded cursor-pointer transition",
                viewMode === "executive"
                  ? "bg-white text-zinc-900 shadow-2xs font-semibold"
                  : "text-zinc-600 hover:text-zinc-900"
              )}
            >
              Executive View
            </button>
            <button
              type="button"
              onClick={() => setViewMode("specs")}
              className={cn(
                "px-2.5 py-1 rounded cursor-pointer transition flex items-center gap-1.5",
                viewMode === "specs"
                  ? "bg-white text-zinc-900 shadow-2xs font-semibold"
                  : "text-zinc-600 hover:text-zinc-900"
              )}
            >
              <span>Spec Parameter Matrix</span>
              {criticalDrivers.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-zinc-200 text-zinc-800 font-mono">
                  {criticalDrivers.length}
                </span>
              )}
            </button>
          </div>

          {onReResearch && (
            <button
              type="button"
              onClick={onReResearch}
              disabled={isReResearching || isFindingMore}
              className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-white border border-zinc-300 hover:bg-zinc-50 text-zinc-800 transition disabled:opacity-50 cursor-pointer shadow-2xs"
              title="Re-run the entire market research agent and discovery loop"
            >
              <RefreshCw className={cn("w-3.5 h-3.5 text-zinc-600", isReResearching && "animate-spin text-zinc-900")} />
              <span>{isReResearching ? "Re-researching..." : "Re-research"}</span>
            </button>
          )}

          {onFindMore && (
            <button
              type="button"
              onClick={onFindMore}
              disabled={isFindingMore || isReResearching}
              className="inline-flex items-center justify-center px-3 py-1.5 rounded-md text-xs font-semibold bg-zinc-900 hover:bg-zinc-800 text-white transition disabled:opacity-50 cursor-pointer"
            >
              {isFindingMore ? "Searching Web..." : "+ Expand Competitor Search"}
            </button>
          )}
        </div>
      </div>

      {/* ── Comparison Table ───────────────────────────────────────── */}
      <div className="border border-zinc-200 rounded-lg bg-white overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              {viewMode === "executive" ? (
                <tr className="bg-zinc-50 border-b border-zinc-200 text-[11px] font-bold uppercase tracking-wider text-zinc-600">
                  <th className="py-2.5 px-3 min-w-[190px]">Competitor / Product</th>
                  <th className="py-2.5 px-3 min-w-[130px]">Pricing Model</th>
                  <th className="py-2.5 px-3 min-w-[240px]">Verified Core Claim</th>
                  <th className="py-2.5 px-3 min-w-[240px]">Mined Weakness / Gripe</th>
                  <th className="py-2.5 px-3 min-w-[220px]">Live Ad Hook</th>
                  <th className="py-2.5 px-3 min-w-[90px] text-right">Grounding</th>
                </tr>
              ) : (
                <tr className="bg-zinc-50 border-b border-zinc-200 text-[11px] font-bold uppercase tracking-wider text-zinc-600">
                  <th className="py-2.5 px-3 min-w-[180px]">Competitor</th>
                  <th className="py-2.5 px-3 min-w-[120px]">Pricing Model</th>
                  {criticalDrivers.map((driver, i) => (
                    <th key={i} className="py-2.5 px-3 min-w-[180px] max-w-[240px]">
                      <span className="block truncate" title={driver}>
                        {driver.split(":")[0]}
                      </span>
                    </th>
                  ))}
                  <th className="py-2.5 px-3 min-w-[80px] text-right">Source</th>
                </tr>
              )}
            </thead>
            <tbody>
              {competitors.length === 0 ? (
                <tr>
                  <td
                    colSpan={viewMode === "executive" ? 6 : 3 + criticalDrivers.length}
                    className="py-12 text-center text-zinc-400 text-xs"
                  >
                    Autonomous search loop is harvesting competitor data...
                  </td>
                </tr>
              ) : (
                competitors.map((comp, idx) => {
                  const isSelected = idx === selectedCompId;
                  const isExpanded = expandedRow === idx;
                  const adHook = comp.ad_hooks?.[0];
                  const weakness = comp.weaknesses_mined?.[0];
                  const claim = comp.core_claims?.[0];
                  const source = comp.sources?.[0];

                  return (
                    <React.Fragment key={idx}>
                      <tr
                        onClick={() => setSelectedCompId(idx)}
                        className={cn(
                          "transition-colors cursor-pointer border-b border-zinc-200",
                          isSelected ? "bg-zinc-50 font-medium" : "hover:bg-zinc-50/70"
                        )}
                      >
                        {/* Name & Expand Toggle */}
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={(e) => toggleRow(idx, e)}
                              className="text-zinc-400 hover:text-zinc-700 cursor-pointer p-0.5"
                              title="Toggle full details"
                            >
                              {isExpanded ? (
                                <ChevronUp className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5" />
                              )}
                            </button>
                            <div className="min-w-0 max-w-[220px]">
                              <span className="font-semibold text-zinc-900 block truncate">
                                {comp.brand_name}
                              </span>
                              {comp.product_name && comp.product_name !== comp.brand_name && (
                                <span className="text-[11px] text-zinc-500 font-normal line-clamp-1">
                                  {comp.product_name}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>

                        {/* Pricing */}
                        <td className="py-2.5 px-3">
                          <span
                            className={cn(
                              "inline-block px-2 py-0.5 rounded text-[11px] font-mono border",
                              comp.pricing_model && comp.pricing_model !== "detected"
                                ? "bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold"
                                : comp.pricing_model === "detected"
                                ? "bg-amber-50 text-amber-800 border-amber-200"
                                : "bg-zinc-100 text-zinc-500 border-zinc-200"
                            )}
                          >
                            {pricingLabel(comp.pricing_model)}
                          </span>
                        </td>

                        {viewMode === "executive" ? (
                          <>
                            {/* Claim */}
                            <td className="py-2.5 px-3 text-zinc-700 max-w-xs">
                              <p className="line-clamp-2 leading-relaxed">
                                {claim || (comp.factual_evidence?.[0] ? comp.factual_evidence[0].replace(/^["']|["']$/g, "") : null) || (
                                  <span className="text-zinc-400 italic">No marketing claim on page</span>
                                )}
                              </p>
                            </td>

                            {/* Weakness */}
                            <td className="py-2.5 px-3 text-rose-900 max-w-xs">
                              {weakness ? (
                                <div className="flex items-start gap-1.5">
                                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-600" />
                                  <span className="line-clamp-2 leading-relaxed">{weakness}</span>
                                </div>
                              ) : (
                                <span className="text-zinc-400 text-[11px]">No complaints found</span>
                              )}
                            </td>

                            {/* Ad Hook */}
                            <td className="py-2.5 px-3 text-zinc-800 max-w-xs">
                              {adHook ? (
                                <div className="flex items-start gap-1.5 bg-blue-50/60 px-2 py-1 rounded border border-blue-100">
                                  <Megaphone className="w-3 h-3 text-blue-600 shrink-0 mt-0.5" />
                                  <span className="line-clamp-2 italic font-medium text-[11px] text-blue-900">
                                    {adHook.startsWith("Web ad mention: ")
                                      ? adHook.replace(/^Web ad mention:\s*["']?/, "").replace(/["']?$/, "")
                                      : adHook}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-zinc-400 text-[11px]">No active ad library ads</span>
                              )}
                            </td>
                          </>
                        ) : (
                          criticalDrivers.map((driver, di) => {
                            const driverKey = driver.split(":")[0].trim().toLowerCase().replace(/[\s-]+/g, "_");
                            const attrVal =
                              comp.dynamic_attributes?.[driver] ||
                              comp.dynamic_attributes?.[driver.split(":")[0]] ||
                              comp.dynamic_attributes?.[driverKey] ||
                              Object.entries(comp.dynamic_attributes || {}).find(([k]) =>
                                k.toLowerCase().includes(driver.split(":")[0].toLowerCase().trim())
                              )?.[1];

                            return (
                              <td key={di} className="py-2.5 px-3 text-xs max-w-[240px]">
                                {attrVal ? (
                                  <span className="inline-block px-2 py-0.5 rounded bg-zinc-100 text-zinc-800 border border-zinc-200 text-[11px] font-medium leading-relaxed">
                                    {attrVal}
                                  </span>
                                ) : (
                                  <span className="text-zinc-400 text-[11px] italic">Not disclosed</span>
                                )}
                              </td>
                            );
                          })
                        )}

                        {/* Source */}
                        <td className="py-2.5 px-3 text-right">
                          {safeHref(source) ? (
                            <a
                              href={safeHref(source)}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-[11px] text-zinc-600 hover:text-zinc-900 font-medium"
                            >
                              <span>Inspect</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          ) : (
                            <span className="text-zinc-400 text-[11px]">Crawl</span>
                          )}
                        </td>
                      </tr>

                      {/* Expanded In-Depth Inspection Row */}
                      {isExpanded && (
                        <tr className="bg-zinc-50/50 border-b border-zinc-200">
                          <td colSpan={viewMode === "executive" ? 6 : 3 + criticalDrivers.length} className="p-4">
                            <div className="space-y-3">
                              {/* Extracted Specs */}
                              {comp.dynamic_attributes && Object.keys(comp.dynamic_attributes).length > 0 && (
                                <div>
                                  <span className="text-[11px] font-bold text-zinc-700 uppercase tracking-wider block mb-1.5">
                                    Extracted Attribute Specifications:
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {Object.entries(comp.dynamic_attributes)
                                      .filter(([, v]) => Boolean(v))
                                      .map(([k, v], i) => (
                                        <span
                                          key={i}
                                          className="px-2 py-0.5 rounded text-[11px] bg-white border border-zinc-200 text-zinc-800"
                                        >
                                          <strong className="font-semibold text-zinc-950">{k.replace(/_/g, " ")}:</strong>{" "}
                                          {v}
                                        </span>
                                      ))}
                                  </div>
                                </div>
                              )}

                              {/* Verbatim Factual Excerpt */}
                              {comp.factual_evidence && comp.factual_evidence.length > 0 && (
                                <div>
                                  <span className="text-[11px] font-bold text-zinc-700 uppercase tracking-wider block mb-1">
                                    Grounding Excerpt from Scraped Page:
                                  </span>
                                  <blockquote className="p-2.5 rounded bg-zinc-100 text-zinc-800 font-mono text-[11px] leading-relaxed border border-zinc-200 italic">
                                    "{comp.factual_evidence[0]}"
                                  </blockquote>
                                </div>
                              )}

                              {/* All Mined Weaknesses */}
                              {comp.weaknesses_mined && comp.weaknesses_mined.length > 1 && (
                                <div>
                                  <span className="text-[11px] font-bold text-zinc-700 uppercase tracking-wider block mb-1">
                                    Additional Customer Grievances:
                                  </span>
                                  <ul className="list-disc list-inside space-y-0.5 text-[11px] text-rose-800">
                                    {comp.weaknesses_mined.slice(1).map((w, wi) => (
                                      <li key={wi}>{w}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Active Inspection Card (When row clicked) ──────────────── */}
      {active && (
        <div className="border border-zinc-200 rounded-lg p-4 bg-white shadow-xs space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-zinc-200 pb-2.5">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-zinc-900">
                  {active.brand_name} {active.product_name && active.product_name !== active.brand_name ? `• ${active.product_name}` : ""}
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-100 border border-zinc-200 text-zinc-700">
                  {pricingLabel(active.pricing_model)}
                </span>
              </div>
            </div>

            {safeHref(active.sources?.[0]) && (
              <a
                href={safeHref(active.sources[0])}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium bg-zinc-100 hover:bg-zinc-200 text-zinc-800 border border-zinc-200 transition shrink-0"
              >
                <span>View Web Evidence Source</span>
                <ExternalLink className="w-3 h-3 text-zinc-500" />
              </a>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {/* Core Claims */}
            <div className="space-y-1">
              <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">Core Market Claims</span>
              <ul className="list-disc list-inside space-y-1 text-zinc-700">
                {(active.core_claims && active.core_claims.length > 0 ? active.core_claims : ["No explicit claims extracted."]).map((c, ci) => (
                  <li key={ci} className="leading-relaxed">{c}</li>
                ))}
              </ul>
            </div>

            {/* Weaknesses Mined */}
            <div className="space-y-1">
              <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600">Customer Pain Points &amp; Limitations</span>
              <ul className="list-disc list-inside space-y-1 text-rose-900">
                {(active.weaknesses_mined && active.weaknesses_mined.length > 0 ? active.weaknesses_mined : ["No critical customer complaints verified."]).map((w, wi) => (
                  <li key={wi} className="leading-relaxed">{w}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
