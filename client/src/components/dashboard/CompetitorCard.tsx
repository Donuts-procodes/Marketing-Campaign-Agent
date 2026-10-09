import { useState } from "react";
import { CompetitorProfile, DynamicParameterTaxonomy } from "@/types/research";
import {
  ExternalLink,
  Megaphone,
  AlertCircle,
  FileText,
  Layers,
  Clock,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  TrendingUp,
  ThumbsUp,
  MapPin,
  Target,
  Users,
} from "lucide-react";
import { pricingLabel, safeHref, cn } from "@/lib/utils";

/**
 * Completeness is what the research pipeline is actually graded on, so the card states it
 * outright. A profile missing pricing and complaints otherwise looks the same at a glance as
 * a complete one, which is how a thin report passes for a finished one.
 */
export function profileCompleteness(comp: CompetitorProfile): {
  score: number;
  have: string[];
  missing: string[];
} {
  const checks: Array<[string, boolean]> = [
    // "detected" is the placeholder written when a page mentions pricing without stating an
    // amount; the DQS scorer refuses to count it, so neither does this.
    ["Pricing", !!comp.pricing_model && comp.pricing_model !== "detected"],
    ["Claims", (comp.core_claims?.length ?? 0) > 0],
    ["Complaints", (comp.weaknesses_mined?.length ?? 0) > 0],
    ["Ad hooks", (comp.ad_hooks?.length ?? 0) > 0],
    ["Evidence", (comp.factual_evidence?.length ?? 0) > 0],
    ["Attributes", Object.keys(comp.dynamic_attributes ?? {}).length > 0],
  ];
  const have = checks.filter(([, ok]) => ok).map(([label]) => label);
  const missing = checks.filter(([, ok]) => !ok).map(([label]) => label);
  return { score: have.length / checks.length, have, missing };
}

const LABEL = "text-[10px] font-bold uppercase tracking-wider text-zinc-500";

interface CompetitorCardProps {
  competitor: CompetitorProfile;
  taxonomy?: DynamicParameterTaxonomy;
}

export function CompetitorCard({
  competitor: comp,
  taxonomy,
}: CompetitorCardProps) {
  const [expanded, setExpanded] = useState(false);

  const { score, missing } = profileCompleteness(comp);
  const hasRealPrice = !!comp.pricing_model && comp.pricing_model !== "detected";

  const drivers = taxonomy?.critical_jtbd_drivers ?? [];
  const attrs = comp.dynamic_attributes ?? {};
  // Critical drivers first: those are the parameters the whole comparison is built on, so a
  // card showing only incidental specs hides whether the rival was actually profiled.
  const driverAttrs = drivers.map((d) => [d, attrs[d]] as const).filter(([, v]) => !!v);
  const otherAttrs = Object.entries(attrs).filter(([k, v]) => !drivers.includes(k) && !!v);

  const claims = comp.core_claims ?? [];
  const weaknesses = comp.weaknesses_mined ?? [];
  const hooks = comp.ad_hooks ?? [];
  const evidence = comp.factual_evidence ?? [];
  const sources = comp.sources ?? [];
  const strengths = comp.strengths_mined ?? [];
  const milestones = comp.milestones ?? [];
  const rc = comp.review_context;
  // Newest first: what moved most recently is what a merchant acts on.
  const changes = [...(comp.change_history ?? [])].reverse();

  const hostOf = (url: string) => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "source";
    }
  };

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-zinc-200 bg-white shadow-xs transition hover:shadow-md"
      )}
    >
      {/* Header */}
      <div className="p-4 pb-3 border-b border-zinc-100">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-zinc-900 truncate">{comp.brand_name}</h3>
            {comp.product_name && comp.product_name !== comp.brand_name && (
              <p className="text-[11px] text-zinc-500 line-clamp-1 mt-0.5">{comp.product_name}</p>
            )}
          </div>
          <span
            className={cn(
              "shrink-0 px-2 py-0.5 rounded text-[11px] font-mono border",
              hasRealPrice
                ? "bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold"
                : comp.pricing_model === "detected"
                  ? "bg-amber-50 text-amber-800 border-amber-200"
                  : "bg-zinc-100 text-zinc-500 border-zinc-200"
            )}
          >
            {pricingLabel(comp.pricing_model)}
          </span>
        </div>

        <div className="flex items-center flex-wrap gap-1.5 mt-2.5">
          {comp.as_of && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-amber-50 text-amber-800 border border-amber-200"
              title="Carried forward from an earlier run — not re-found in the latest scan"
            >
              <Clock className="w-2.5 h-2.5" />
              Last seen {comp.as_of}
            </span>
          )}
          <span
            className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
              score >= 0.67
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : score >= 0.34
                  ? "bg-amber-50 text-amber-700 border-amber-200"
                  : "bg-zinc-100 text-zinc-600 border-zinc-200"
            )}
            title={missing.length ? `Not found: ${missing.join(", ")}` : "Fully profiled"}
          >
            {score >= 0.67 ? (
              <CheckCircle2 className="w-2.5 h-2.5" />
            ) : (
              <AlertCircle className="w-2.5 h-2.5" />
            )}
            {Math.round(score * 100)}% profiled
          </span>
          {comp.rating && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-800 border border-amber-200"
              title={comp.review_count ? `${comp.review_count} reviews` : "Rating stated on a review page"}
            >
              <ThumbsUp className="w-2.5 h-2.5" />
              {comp.rating}/5
              {comp.review_count ? (
                <span className="font-mono opacity-70">({comp.review_count.toLocaleString()})</span>
              ) : null}
            </span>
          )}
          {comp.founded && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-800 border border-blue-200"
              title={`In business since ${comp.founded}`}
            >
              <Clock className="w-2.5 h-2.5" />
              Est. {comp.founded}
              {(() => {
                const years = new Date().getFullYear() - Number(comp.founded);
                return Number.isFinite(years) && years > 0 ? ` (${years}y)` : "";
              })()}
            </span>
          )}
          {(comp.headquarters || (comp.operating_locations && comp.operating_locations.length > 0)) && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-800 border border-purple-200 max-w-[180px] truncate"
              title={`Headquarters / Offices: ${comp.headquarters ?? comp.operating_locations?.join(", ")}`}
            >
              <MapPin className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{comp.headquarters ?? comp.operating_locations?.[0]}</span>
            </span>
          )}
          {((comp.other_products && comp.other_products.length > 0) || comp.product_catalog_count) && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-800 border border-slate-200"
              title={comp.other_products?.length ? `Other models: ${comp.other_products.join(", ")}` : "Product catalog"}
            >
              <Layers className="w-2.5 h-2.5" />
              {comp.product_catalog_count ? `${comp.product_catalog_count} models` : `${comp.other_products?.length} other models`}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-4 space-y-3.5 flex-1">
        {/* Core claims */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <FileText className="w-3 h-3 text-zinc-400 shrink-0" />
            <span className={LABEL}>Core claims</span>
            {claims.length > 1 && (
              <span className="text-[10px] font-mono text-zinc-400">{claims.length}</span>
            )}
          </div>
          {claims.length ? (
            <ul className="space-y-1">
              {(expanded ? claims : claims.slice(0, 2)).map((c, i) => (
                <li key={i} className="text-[11px] text-zinc-700 leading-relaxed line-clamp-3">
                  {c}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No marketing claim found on their pages</p>
          )}
        </div>

        {/* Strengths — mined from the same review pages as the complaints. Shown directly
            above them so a rival reads as a balanced picture rather than a list of faults. */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <ThumbsUp className="w-3 h-3 text-emerald-500 shrink-0" />
            <span className={LABEL}>What customers praise</span>
            {strengths.length > 1 && (
              <span className="text-[10px] font-mono text-zinc-400">{strengths.length}</span>
            )}
          </div>
          {strengths.length ? (
            <ul className="space-y-1">
              {(expanded ? strengths : strengths.slice(0, 2)).map((st, i) => (
                <li
                  key={i}
                  className="text-[11px] text-emerald-900 leading-relaxed line-clamp-3 pl-2 border-l-2 border-emerald-200"
                >
                  {st}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No customer praise surfaced</p>
          )}
        </div>

        {/* Complaints */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <AlertCircle className="w-3 h-3 text-rose-500 shrink-0" />
            <span className={LABEL}>Complaints</span>
            {weaknesses.length > 1 && (
              <span className="text-[10px] font-mono text-zinc-400">{weaknesses.length}</span>
            )}
          </div>
          {weaknesses.length ? (
            <ul className="space-y-1">
              {(expanded ? weaknesses : weaknesses.slice(0, 2)).map((w, i) => (
                <li
                  key={i}
                  className="text-[11px] text-rose-900 leading-relaxed line-clamp-3 pl-2 border-l-2 border-rose-200"
                >
                  {w}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No user complaints surfaced</p>
          )}
        </div>

        {/* Ad hooks */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Megaphone className="w-3 h-3 text-violet-500 shrink-0" />
            <span className={LABEL}>Live ad hooks</span>
            {hooks.length > 1 && (
              <span className="text-[10px] font-mono text-zinc-400">{hooks.length}</span>
            )}
          </div>
          {hooks.length ? (
            <ul className="space-y-1">
              {(expanded ? hooks : hooks.slice(0, 1)).map((h, i) => (
                <li
                  key={i}
                  className="text-[11px] text-violet-900 bg-violet-50 border border-violet-100 rounded px-2 py-1 leading-relaxed line-clamp-3"
                >
                  {h}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No active ads found in the libraries</p>
          )}
        </div>

        {/* Attributes */}
        {(driverAttrs.length > 0 || otherAttrs.length > 0) && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Layers className="w-3 h-3 text-zinc-400 shrink-0" />
              <span className={LABEL}>Attributes</span>
              <span className="text-[10px] font-mono text-zinc-400">
                {driverAttrs.length + otherAttrs.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {driverAttrs.map(([k, v]) => (
                <span
                  key={k}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-900 text-white"
                  title={`${k}: ${v}`}
                >
                  {k.replace(/_/g, " ")}:{" "}
                  <span className="font-mono">{String(v).slice(0, 28)}</span>
                </span>
              ))}
              {(expanded ? otherAttrs : otherAttrs.slice(0, 4)).map(([k, v]) => (
                <span
                  key={k}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-100 text-zinc-700 border border-zinc-200"
                  title={`${k}: ${v}`}
                >
                  {k.replace(/_/g, " ")}:{" "}
                  <span className="font-mono">{String(v).slice(0, 28)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* What changed since our last scan. Shown unexpanded because a price move is the
            most actionable thing on the card, and it exists for no other reason than that we
            scanned this competitor before. */}
        {changes.length > 0 && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <TrendingUp className="w-3 h-3 text-amber-500 shrink-0" />
              <span className={LABEL}>Changed since last scan</span>
              <span className="text-[10px] font-mono text-zinc-400">{changes.length}</span>
            </div>
            <ul className="space-y-1">
              {(expanded ? changes : changes.slice(0, 3)).map((c, i) => (
                <li
                  key={i}
                  className="text-[11px] text-amber-900 bg-amber-50 border border-amber-100 rounded px-2 py-1 leading-relaxed"
                >
                  <span className="font-mono text-[10px] text-amber-700">{c.observed_at}</span>{" "}
                  {c.field === "pricing_model" ? (
                    <>
                      price{" "}
                      <span className="line-through opacity-60">{c.previous ?? "—"}</span>
                      {" → "}
                      <strong>{c.current ?? "—"}</strong>
                    </>
                  ) : c.field === "core_claims.added" ? (
                    <>started claiming "{c.current}"</>
                  ) : c.field === "core_claims.dropped" ? (
                    <>stopped claiming "{c.previous}"</>
                  ) : (
                    <>
                      {c.field.replace(/[._]/g, " ")}: {c.previous ?? "—"} → {c.current ?? "—"}
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Review context, only once expanded: the consensus and the counter-angle behind the
            quotes above. Collapsed cards stay a scannable grid. */}
        {expanded && rc && (rc.overall_sentiment_consensus || rc.counter_positioning_angle || !!rc.top_complaint_drivers?.length) && (
          <div className="space-y-2 p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
            <div className="flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-zinc-600 shrink-0" />
              <span className={LABEL}>Customer sentiment & feedback</span>
            </div>
            {rc.overall_sentiment_consensus && (
              <p className="text-[11px] text-zinc-700 leading-relaxed">{rc.overall_sentiment_consensus}</p>
            )}
            {!!rc.top_complaint_drivers?.length && (
              <ul className="space-y-1">
                {rc.top_complaint_drivers.slice(0, 3).map((a, i) => (
                  <li key={i} className="text-[11px] text-rose-900 leading-relaxed pl-2 border-l-2 border-rose-200">
                    <strong>{a.topic}</strong>
                    {a.root_cause ? ` — ${a.root_cause}` : a.summary ? ` — ${a.summary}` : ""}
                  </li>
                ))}
              </ul>
            )}
            {!!rc.unmet_customer_needs?.length && (
              <p className="text-[11px] text-zinc-700">
                <span className="text-zinc-500 font-medium">Still asking for: </span>
                {rc.unmet_customer_needs.slice(0, 3).join(" · ")}
              </p>
            )}
            {rc.counter_positioning_angle && (
              <div className="rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5">
                <div className="flex items-center gap-1 mb-0.5">
                  <Target className="w-3 h-3 text-amber-600 shrink-0" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
                    Your counter-angle
                  </span>
                </div>
                <p className="text-[11px] text-amber-900 leading-relaxed">{rc.counter_positioning_angle}</p>
              </div>
            )}
          </div>
        )}

        {/* Company background, only once expanded */}
        {expanded && (comp.founded || comp.headquarters || (comp.operating_locations && comp.operating_locations.length > 0) || (comp.other_products && comp.other_products.length > 0) || milestones.length > 0) && (
          <div className="space-y-2 p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
            <div className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-zinc-600 shrink-0" />
              <span className={LABEL}>Corporate footprint & Catalog</span>
            </div>
            {comp.founded && (
              <p className="text-[11px] text-zinc-700">
                Established <strong>{comp.founded}</strong>
                {(() => {
                  const years = new Date().getFullYear() - Number(comp.founded);
                  return Number.isFinite(years) && years > 0 ? ` · ${years} years active` : "";
                })()}
              </p>
            )}
            {comp.headquarters && (
              <p className="text-[11px] text-zinc-700 flex items-start gap-1">
                <MapPin className="w-3 h-3 text-zinc-400 mt-0.5 shrink-0" />
                <span>Headquarters: <strong>{comp.headquarters}</strong></span>
              </p>
            )}
            {comp.operating_locations && comp.operating_locations.length > 0 && (
              <div className="text-[11px] text-zinc-700 space-y-0.5">
                <span className="text-zinc-500 font-medium">Active branches & territories:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {comp.operating_locations.map((loc, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded bg-white border border-zinc-200 text-[10px] text-zinc-700">
                      {loc}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {((comp.other_products && comp.other_products.length > 0) || comp.product_catalog_count) && (
              <div className="text-[11px] text-zinc-700 space-y-0.5">
                <span className="text-zinc-500 font-medium">
                  Product lineup ({comp.product_catalog_count ?? comp.other_products?.length} products):
                </span>
                {comp.other_products && comp.other_products.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {comp.other_products.map((prod, i) => (
                      <span key={i} className="px-1.5 py-0.5 rounded bg-white border border-zinc-200 text-[10px] text-zinc-700 font-medium">
                        {prod}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
            {milestones.length > 0 && (
              <div className="pt-1 border-t border-zinc-200 space-y-1">
                <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Milestones</span>
                <ul className="space-y-1">
                  {milestones.map((m, i) => (
                    <li
                      key={i}
                      className="text-[11px] text-zinc-600 leading-relaxed border-l-2 border-zinc-300 pl-2"
                    >
                      {m}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Verbatim evidence, only once expanded */}
        {expanded && evidence.length > 0 && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <FileText className="w-3 h-3 text-zinc-400 shrink-0" />
              <span className={LABEL}>Verbatim evidence</span>
              <span className="text-[10px] font-mono text-zinc-400">{evidence.length}</span>
            </div>
            <ul className="space-y-1">
              {evidence.map((e, i) => (
                <li
                  key={i}
                  className="text-[11px] text-zinc-600 italic leading-relaxed border-l-2 border-zinc-200 pl-2"
                >
                  {e}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-zinc-100 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {sources.length > 0 && safeHref(sources[0]) ? (
            <>
              <a
                href={safeHref(sources[0])}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-zinc-600 hover:text-zinc-900 truncate"
              >
                <ExternalLink className="w-3 h-3 shrink-0" />
                <span className="truncate">{hostOf(sources[0])}</span>
              </a>
              {sources.length > 1 && (
                <span className="text-[10px] font-mono text-zinc-400 shrink-0">
                  +{sources.length - 1}
                </span>
              )}
            </>
          ) : (
            <span className="text-[11px] text-zinc-400 italic">No source URL</span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-zinc-600 hover:text-zinc-900 cursor-pointer shrink-0"
        >
          {expanded ? (
            <>
              Less <ChevronUp className="w-3 h-3" />
            </>
          ) : (
            <>
              More <ChevronDown className="w-3 h-3" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
