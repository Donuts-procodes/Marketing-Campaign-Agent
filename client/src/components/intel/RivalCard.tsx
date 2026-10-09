import { memo } from "react";
import { RivalView, relevanceLabel } from "@/lib/rivalMetrics";
import { cn } from "@/lib/utils";
import { ArrowRight, Megaphone, ThumbsDown, ThumbsUp, TrendingUp, Clock, MapPin, Layers } from "lucide-react";

/** Why this rival matters to a small merchant; each label is set only with evidence. */
const COHORTS: Record<string, { label: string; cls: string; hint: string }> = {
  leapfrog: {
    label: "Grew from your level",
    cls: "bg-indigo-50 text-indigo-800 border-indigo-200",
    hint: "Sells what you sell, and its stated founding year and size show how far it grew.",
  },
  catching_up: {
    label: "Catching up",
    cls: "bg-rose-50 text-rose-700 border-rose-200",
    hint: "Your size, and measurably accelerating since the last scan.",
  },
  peer: { label: "Your size", cls: "bg-sky-50 text-sky-800 border-sky-200", hint: "Sized from its own stated team, funding or founding facts." },
  larger: { label: "Larger", cls: "bg-violet-50 text-violet-800 border-violet-200", hint: "Clearly bigger, by stated funding or size." },
  incumbent: { label: "Category giant", cls: "bg-zinc-100 text-zinc-700 border-zinc-200", hint: "A budget you are not competing with head-on." },
};

interface RivalCardProps {
  rival: RivalView;
  onOpen: (index: number) => void;
}

export function Avatar({ rival, size = "md" }: { rival: RivalView; size?: "md" | "lg" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "rounded-xl flex items-center justify-center font-display font-bold shrink-0",
        size === "lg" ? "w-12 h-12 text-base" : "w-10 h-10 text-sm",
        rival.tone
      )}
    >
      {rival.initials}
    </span>
  );
}

export function RatingBadge({ rating, reviews }: { rating: number | null; reviews: number | null }) {
  if (rating == null) return <span className="text-[11px] text-ink-faint">No rating found</span>;
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-ink">
      <span className="text-amber-500" aria-hidden>
        ★
      </span>
      {rating.toFixed(1)}
      {reviews ? <span className="font-normal text-ink-faint">({reviews.toLocaleString()})</span> : null}
    </span>
  );
}

/** Praise vs complaints found on review sites, as one proportional bar. */
export function SentimentBar({ praise, complaints }: { praise: number; complaints: number }) {
  const total = praise + complaints;
  if (!total) return <div className="h-1.5 rounded-full bg-zinc-100" title="No customer reviews surfaced" />;
  const pct = Math.round((praise / total) * 100);
  return (
    <div
      className="flex h-1.5 rounded-full overflow-hidden bg-rose-200"
      title={`${praise} praise · ${complaints} complaints`}
      role="img"
      aria-label={`${praise} praise and ${complaints} complaints found`}
    >
      <div className="bg-emerald-400" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function CompletenessDots({ have, missing }: { have: string[]; missing: string[] }) {
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={missing.length ? `Not found: ${missing.join(", ")}` : "Fully profiled"}
      aria-label={`${have.length} of ${have.length + missing.length} data points found`}
    >
      {[...have.map(() => true), ...missing.map(() => false)].map((ok, i) => (
        <span key={i} className={cn("w-1.5 h-1.5 rounded-full", ok ? "bg-ink" : "bg-zinc-200")} />
      ))}
    </span>
  );
}

function Line({ icon: Icon, tone, text }: { icon: typeof ThumbsUp; tone: string; text: string }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className={cn("w-3.5 h-3.5 mt-0.5 shrink-0", tone)} />
      <p className="text-xs text-ink-soft leading-relaxed line-clamp-2">{text}</p>
    </div>
  );
}

function RivalCardImpl({ rival, onOpen }: RivalCardProps) {
  const rel = relevanceLabel(rival.relevance);
  const cohort = COHORTS[rival.comp.cohort ?? ""];
  const reason = rival.comp.relevance_reason;
  const comp = rival.comp;
  const hasFootprint = !!(comp.founded || comp.headquarters || (comp.operating_locations && comp.operating_locations.length > 0) || (comp.other_products && comp.other_products.length > 0) || comp.product_catalog_count);

  return (
    <button
      type="button"
      onClick={() => onOpen(rival.index)}
      className="group min-w-0 text-left flex flex-col rounded-2xl border border-line bg-white shadow-card hover:shadow-lift hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink transition-all duration-200 animate-fade-up"
      style={{ animationDelay: `${rival.index * 50}ms` }}
    >
      <div className="p-4 pb-3 flex items-start gap-3">
        <Avatar rival={rival} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-[15px] font-bold text-ink truncate">{rival.name}</h3>
            {rel && (
              <span className={cn("shrink-0 px-1.5 py-0.5 rounded-md text-[10px] font-semibold", rel.cls)}>
                {rel.label}
              </span>
            )}
          </div>
          <p className="text-[11px] text-ink-faint truncate">{rival.host ?? rival.subtitle ?? "Own website not found"}</p>
          {(cohort || rival.comp.named_by_merchant) && (
            <div className="mt-1 flex flex-wrap gap-1">
              {rival.comp.named_by_merchant && (
                <span
                  className="inline-flex px-1.5 py-0.5 rounded-md border text-[10px] font-semibold bg-canvas text-ink-soft border-line"
                  title="You listed this rival. It was researched in addition to the ones the agent found."
                >
                  You named
                </span>
              )}
              {cohort && (
                <span className={cn("inline-flex px-1.5 py-0.5 rounded-md border text-[10px] font-semibold", cohort.cls)} title={cohort.hint}>
                  {cohort.label}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Margin, not padding: line-clamp clips at the padding box, so padding would show a cut third line. */}
      {reason && <p className="mx-4 -mt-1 mb-3 text-xs text-ink-soft leading-relaxed line-clamp-2">{reason}</p>}

      <div className="mx-4 grid grid-cols-2 gap-2 rounded-xl bg-canvas px-3 py-2.5">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-ink-faint font-semibold">Price</div>
          <div
            className={cn("text-xs font-semibold truncate", rival.hasRealPrice ? "text-ink" : "text-ink-faint")}
            title={rival.priceLabel}
          >
            {rival.priceLabel}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-ink-faint font-semibold">Rating</div>
          <RatingBadge rating={rival.rating} reviews={rival.reviewCount} />
        </div>
      </div>

      {hasFootprint && (
        <div className="mx-4 mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-soft">
          {comp.founded && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">
              <Clock className="w-2.5 h-2.5" />
              Est. {comp.founded}
            </span>
          )}
          {(comp.headquarters || (comp.operating_locations && comp.operating_locations.length > 0)) && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 font-medium max-w-[140px] truncate" title={`HQ: ${comp.headquarters ?? comp.operating_locations?.join(", ")}`}>
              <MapPin className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{comp.headquarters ?? comp.operating_locations?.[0]}</span>
            </span>
          )}
          {((comp.other_products && comp.other_products.length > 0) || comp.product_catalog_count) && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-700 font-medium">
              <Layers className="w-2.5 h-2.5" />
              {comp.product_catalog_count ? `${comp.product_catalog_count} models` : `${comp.other_products?.length} other models`}
            </span>
          )}
        </div>
      )}

      <div className="p-4 space-y-2.5 flex-1">
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            <span>{rival.praise.length} praise</span>
            <span>
              {rival.complaints.length} complaint{rival.complaints.length === 1 ? "" : "s"}
            </span>
          </div>
          <SentimentBar praise={rival.praise.length} complaints={rival.complaints.length} />
        </div>
        {rival.praise[0] && <Line icon={ThumbsUp} tone="text-emerald-500" text={rival.praise[0]} />}
        {rival.complaints[0] && <Line icon={ThumbsDown} tone="text-rose-500" text={rival.complaints[0]} />}
        {rival.ads[0] && <Line icon={Megaphone} tone="text-violet-500" text={rival.ads[0]} />}
        {!rival.praise[0] && !rival.complaints[0] && !rival.ads[0] && rival.claims[0] && (
          <p className="text-xs text-ink-soft leading-relaxed line-clamp-3">{rival.claims[0]}</p>
        )}
      </div>

      <div className="px-4 py-2.5 border-t border-line flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CompletenessDots have={rival.completeness.have} missing={rival.completeness.missing} />
          {rival.changes.length > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-800 text-[10px] font-semibold">
              <TrendingUp className="w-3 h-3" />
              {rival.changes.length} change{rival.changes.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-ink-soft group-hover:text-ink">
          Full profile <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </button>
  );
}

export const RivalCard = memo(RivalCardImpl);
