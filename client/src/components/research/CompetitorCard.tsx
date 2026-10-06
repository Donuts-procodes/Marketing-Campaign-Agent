import { CompetitorProfile } from "@/types/research";
import { safeHref, truncateUrl } from "@/lib/utils";
import {
  ExternalLink,
  Flame,
  Check,
  CheckCircle,
  DollarSign,
  ShieldAlert,
  SlidersHorizontal,
  Zap,
} from "lucide-react";

interface CompetitorCardProps {
  competitor: CompetitorProfile;
}

export function CompetitorCard({ competitor }: CompetitorCardProps) {
  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800/90 p-5 flex flex-col justify-between hover:border-slate-700 transition shadow-lg space-y-4">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 font-semibold">
            {competitor.brand_name}
          </span>

          {competitor.pricing_model ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-emerald-300 border border-emerald-500/20">
              <DollarSign className="w-3 h-3 text-emerald-400" />
              {competitor.pricing_model}
            </span>
          ) : (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
              Pricing unlisted
            </span>
          )}
        </div>

        <h4 className="text-base font-bold text-slate-100">
          {competitor.product_name}
        </h4>
      </div>

      {/* Core Claims */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Market Claims & Features
        </span>
        <ul className="space-y-1.5">
          {competitor.core_claims.map((claim, idx) => (
            <li
              key={idx}
              className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2 rounded-lg border border-slate-800/60"
            >
              <Check className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0 mt-0.5" />
              <span>{claim}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Dynamic Specification Parameters */}
      {competitor.dynamic_attributes &&
        Object.keys(competitor.dynamic_attributes).length > 0 && (
          <div className="space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              Dynamic Spec Parameters
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(competitor.dynamic_attributes).map(
                ([key, val], idx) => (
                  <div
                    key={idx}
                    className="text-[11px] bg-slate-950/50 p-2 rounded-lg border border-slate-800/60 flex flex-col"
                  >
                    <span className="text-slate-400 font-mono text-[10px] uppercase truncate">
                      {key.replace(/_/g, " ")}
                    </span>
                    <span
                      className="text-slate-200 font-medium truncate"
                      title={val}
                    >
                      {val}
                    </span>
                  </div>
                )
              )}
            </div>
          </div>
        )}

      {/* Active Ad Intelligence & Reach Hooks */}
      {competitor.ad_hooks && competitor.ad_hooks.length > 0 && (
        <div className="space-y-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5" />
            Active Ad Angles & Reach Hooks
          </span>
          <ul className="space-y-1.5">
            {competitor.ad_hooks.map((hook, idx) => (
              <li
                key={idx}
                className="text-xs text-amber-200/90 flex items-start gap-2 bg-amber-950/20 p-2 rounded-lg border border-amber-500/20 italic"
              >
                <span className="text-amber-400 font-bold not-italic">“</span>
                <span>{hook.replace(/^"|"$/g, "")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Verified Factual Evidence & Raw Crawl Citations */}
      {competitor.factual_evidence &&
        competitor.factual_evidence.length > 0 && (
          <div className="space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <CheckCircle className="w-3.5 h-3.5" />
              Direct Factual Evidence (Web Crawl Citations)
            </span>
            <ul className="space-y-1.5">
              {competitor.factual_evidence.map((evidence, idx) => (
                <li
                  key={idx}
                  className="text-[11px] text-emerald-200/90 flex items-start gap-2 bg-emerald-950/20 p-2 rounded-lg border border-emerald-500/20 font-mono"
                >
                  <span className="text-emerald-400 font-bold not-italic">›</span>
                  <span>{evidence}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Mined Gripe / Weaknesses */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-rose-400 flex items-center gap-1.5">
          <Flame className="w-3.5 h-3.5" />
          Mined Vulnerabilities & Gripes
        </span>
        {competitor.weaknesses_mined.length > 0 ? (
          <ul className="space-y-1.5">
            {competitor.weaknesses_mined.map((weakness, idx) => (
              <li
                key={idx}
                className="text-xs text-slate-300 flex items-start gap-2 bg-rose-950/15 p-2 rounded-lg border border-rose-500/20"
              >
                <ShieldAlert className="w-3.5 h-3.5 text-rose-400 flex-shrink-0 mt-0.5" />
                <span>{weakness}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500 italic">No user complaints surfaced.</p>
        )}
      </div>

      {/* Verified Sources */}
      {competitor.sources && competitor.sources.length > 0 && (
        <div className="pt-2 border-t border-slate-800/80 space-y-1.5">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider font-mono">
            Verified Intelligence Sources
          </span>
          <div className="flex flex-wrap gap-1.5">
            {competitor.sources.map((src, i) => (
              <a
                key={i}
                href={safeHref(src)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 bg-indigo-950/30 hover:bg-indigo-900/40 px-2 py-0.5 rounded border border-indigo-500/20 transition truncate max-w-[220px]"
                title={src}
              >
                <span className="truncate">{truncateUrl(src, 30)}</span>
                <ExternalLink className="w-3 h-3 flex-shrink-0" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
