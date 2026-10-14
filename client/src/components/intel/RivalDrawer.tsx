import { useEffect, useRef, useState } from "react";
import { ChannelListing, DynamicParameterTaxonomy, CompetitorChange, ReviewAspect } from "@/types/research";
import { RivalView, attributeFor, hostOf, relevanceLabel } from "@/lib/rivalMetrics";
import { safeHref, cn } from "@/lib/utils";
import { FactSheet } from "@/components/intel/FactSheet";
import { Avatar, CompletenessDots, RatingBadge, SentimentBar } from "@/components/intel/RivalCard";
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Compass,
  DollarSign,
  ExternalLink,
  Megaphone,
  Quote,
  Sparkles,
  Target,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";

const TABS = ["Overview", "Breakout Leap", "Customers", "Marketing", "History", "Sources"] as const;
type Tab = (typeof TABS)[number];

interface RivalDrawerProps {
  rivals: RivalView[];
  openIndex: number | null;
  taxonomy?: DynamicParameterTaxonomy;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

const H = "text-[10px] font-bold uppercase tracking-wider text-ink-faint";

const SOURCE_LABEL: Record<NonNullable<ChannelListing["source"]>, { text: string; title: string; cls: string }> = {
  page: { text: "Page", title: "Read off the listing page", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  search_snippet: {
    text: "Excerpt",
    title: "Read from the search engine's excerpt of the page (the page itself was blocked)",
    cls: "bg-amber-50 text-amber-700 border-amber-200",
  },
  shopping_api: {
    text: "Google Shopping",
    title: "Offer data from Google Shopping (SerpApi)",
    cls: "bg-violet-50 text-violet-700 border-violet-200",
  },
  ai_search: {
    text: "AI cited",
    title: "Found by AI web search with this page as its citation; not re-read by us",
    cls: "bg-sky-50 text-sky-700 border-sky-200",
  },
};

function money(value: number | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD", maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency ?? ""} ${value.toLocaleString()}`.trim();
  }
}

function ListingImage({ url }: { url?: string | null }) {
  const [failed, setFailed] = useState(false);
  const href = safeHref(url);
  if (!href || failed) return <div className="aspect-square bg-zinc-50" aria-hidden />;
  return (
    <img
      src={href}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="aspect-square w-full object-contain bg-white"
    />
  );
}

/** Rival prices grouped by the merchant product they compare against, each with where it came from. */
function ListingPrices({ listings }: { listings: ChannelListing[] }) {
  const priced = listings.filter((l) => l.selling_price != null || l.mrp != null);
  if (!priced.length) return null;
  const groups = new Map<string, ChannelListing[]>();
  for (const l of priced) {
    const key = l.matched_product || "";
    groups.set(key, [...(groups.get(key) ?? []), l]);
  }
  return (
    <section className="rounded-xl bg-white border border-line p-4 space-y-3 shadow-2xs">
      <div className={cn(H, "flex items-center gap-1.5")}>
        <DollarSign className="w-3 h-3 text-emerald-600" /> Catalogue & prices
      </div>
      {[...groups.entries()].map(([product, rows]) => (
        <div key={product || "_"} className="space-y-1.5">
          {product && <div className="text-[11px] font-semibold text-ink-soft">vs your {product}</div>}
          <ul className="grid grid-cols-2 gap-2">
            {rows.map((l, i) => {
              const src = SOURCE_LABEL[l.source ?? "page"];
              return (
                <li key={i} className="rounded-lg border border-line overflow-hidden flex flex-col text-xs">
                  <ListingImage url={l.image_url} />
                  <div className="p-2 space-y-1 min-w-0">
                    <div className="line-clamp-2 text-ink-soft leading-snug" title={l.product}>{l.product || "Listing"}</div>
                    <div className="flex flex-wrap items-baseline gap-x-1.5">
                      <span className="font-bold text-ink">{money(l.selling_price, l.currency)}</span>
                      {l.mrp != null && <span className="text-ink-faint line-through">{money(l.mrp, l.currency)}</span>}
                      {l.discount_pct != null && <span className="text-emerald-700">{l.discount_pct}% off</span>}
                    </div>
                    <div className="flex items-center justify-between gap-1">
                      <a href={safeHref(l.url)} target="_blank" rel="noreferrer" className="truncate text-ink-faint underline-offset-2 hover:underline">
                        {l.site}
                      </a>
                      <span title={src.title} className={cn("shrink-0 px-1.5 py-px rounded border text-[10px] font-semibold", src.cls)}>
                        {src.text}
                      </span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}

function Empty({ children }: { children: string }) {
  return <p className="text-xs text-ink-faint italic py-1">{children}</p>;
}

/**
 * One recurring review theme. The root cause and the counter-angle are the point of this
 * block: a quote says what one customer felt, the mechanism says whether it keeps happening.
 */
function AspectCard({ aspect, tone }: { aspect: ReviewAspect; tone: "positive" | "negative" }) {
  const accent = tone === "negative" ? "border-rose-300" : "border-emerald-300";
  return (
    <div className={cn("rounded-lg bg-white border border-line border-l-2 px-3 py-2 space-y-1.5", accent)}>
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs font-semibold text-ink">{aspect.topic}</span>
      {aspect.sentiment && aspect.sentiment !== tone && (
        <span className="text-[10px] uppercase tracking-wide text-ink-faint">{aspect.sentiment}</span>
      )}
    </div>
    {aspect.summary && <p className="text-[11px] text-ink-soft leading-relaxed">{aspect.summary}</p>}
    {aspect.root_cause && (
      <p className="text-[11px] text-ink-soft leading-relaxed">
        <span className={H}>Root cause</span>{" "}
        <span className="text-ink">{aspect.root_cause}</span>
      </p>
    )}
    {aspect.sample_quotes?.slice(0, 2).map((q, i) => (
      <blockquote key={i} className="text-[11px] text-ink-faint italic leading-relaxed pl-2 border-l border-line">
        “{q}”
      </blockquote>
    ))}
    {aspect.merchant_opportunity && (
      <div className="rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5">
        <div className="flex items-center gap-1 mb-0.5">
          <Target className="w-3 h-3 text-amber-600" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
            How to win this customer
          </span>
        </div>
        <p className="text-[11px] text-amber-900 leading-relaxed">{aspect.merchant_opportunity}</p>
      </div>
    )}
  </div>
  );
}

function describeChange(c: CompetitorChange) {
  if (c.field === "pricing_model")
    return (
      <>
        price <span className="line-through opacity-60">{c.previous ?? "—"}</span> → <strong>{c.current ?? "—"}</strong>
      </>
    );
  if (c.field === "core_claims.added") return <>started saying “{c.current}”</>;
  if (c.field === "core_claims.dropped") return <>stopped saying “{c.previous}”</>;
  if (c.field === "rating")
    return (
      <>
        rating {c.previous ?? "—"} → <strong>{c.current ?? "—"}</strong>
      </>
    );
  return (
    <>
      {c.field.replace(/[._]/g, " ")}: {c.previous ?? "—"} → {c.current ?? "—"}
    </>
  );
}

export function RivalDrawer({ rivals, openIndex, taxonomy, onClose, onNavigate }: RivalDrawerProps) {
  const [tab, setTab] = useState<Tab>("Overview");
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const pos = openIndex == null ? -1 : rivals.findIndex((r) => r.index === openIndex);
  const rival = pos >= 0 ? rivals[pos] : null;
  const isOpen = rival != null;

  useEffect(() => {
    if (!isOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0 });
  }, [openIndex, tab]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && pos < rivals.length - 1) onNavigate(rivals[pos + 1].index);
      else if (e.key === "ArrowLeft" && pos > 0) onNavigate(rivals[pos - 1].index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, pos, rivals, onClose, onNavigate]);

  if (!rival) return null;
  const comp = rival.comp;
  const rel = relevanceLabel(rival.relevance);
  const rc = comp.review_context;
  const drivers = taxonomy?.critical_jtbd_drivers ?? [];
  const driverRows = drivers.map((d) => [d, attributeFor(comp, d)] as const);
  const heads = drivers.map((d) => d.split(":")[0].trim().toLowerCase());
  const isDriverKey = (k: string) => {
    const kl = k.toLowerCase();
    return heads.some((h) => kl === h || kl === h.replace(/[\s-]+/g, "_") || kl.includes(h));
  };
  const otherAttrs = Object.entries(comp.dynamic_attributes ?? {}).filter(([k, v]) => v && !isDriverKey(k));
  const counts: Partial<Record<Tab, number>> = {
    Customers: rival.praise.length + rival.complaints.length,
    Marketing: rival.claims.length + rival.ads.length,
    History: rival.changes.length + (comp.milestones?.length ?? 0),
    Sources: comp.sources?.length ?? 0,
  };

  const visibleTabs = comp.leap_benchmark ? TABS : TABS.filter((t) => t !== "Breakout Leap");

  return (
    <div className="fixed inset-0 z-[60] no-print" role="dialog" aria-modal="true" aria-label={`${rival.name} profile`}>
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px] animate-fade-in" onClick={onClose} />
      <aside className="absolute right-0 top-0 h-full w-full max-w-xl bg-canvas shadow-2xl flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="bg-white border-b border-line px-5 pt-4 pb-0">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => pos > 0 && onNavigate(rivals[pos - 1].index)}
                disabled={pos <= 0}
                className="p-1.5 rounded-lg hover:bg-canvas disabled:opacity-30 transition"
                aria-label="Previous rival"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-[11px] font-mono text-ink-faint tabular-nums">
                {pos + 1} / {rivals.length}
              </span>
              <button
                type="button"
                onClick={() => pos < rivals.length - 1 && onNavigate(rivals[pos + 1].index)}
                disabled={pos >= rivals.length - 1}
                className="p-1.5 rounded-lg hover:bg-canvas disabled:opacity-30 transition"
                aria-label="Next rival"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-canvas transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink"
              aria-label="Close profile"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-start gap-3">
            <Avatar rival={rival} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-display text-xl font-bold text-ink">{rival.name}</h2>
                {rel && <span className={cn("px-1.5 py-0.5 rounded-md text-[10px] font-semibold", rel.cls)}>{rel.label}</span>}
              </div>
              {rival.host && safeHref(rival.siteUrl) ? (
                <a
                  href={safeHref(rival.siteUrl)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-ink"
                >
                  {rival.host} <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                rival.subtitle && <p className="text-xs text-ink-soft">{rival.subtitle}</p>
              )}
            </div>
          </div>

          <nav className="flex gap-1 mt-4 -mb-px overflow-x-auto" role="tablist">
            {visibleTabs.map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 py-2 text-xs font-semibold border-b-2 whitespace-nowrap transition-colors",
                  tab === t ? "border-ink text-ink" : "border-transparent text-ink-faint hover:text-ink",
                  t === "Breakout Leap" && "text-indigo-700 hover:text-indigo-900"
                )}
              >
                {t === "Breakout Leap" ? (
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-indigo-600" />
                    <span>Breakout Leap</span>
                  </span>
                ) : (
                  t
                )}
                {counts[t] ? <span className="ml-1 font-mono text-[10px] text-ink-faint">{counts[t]}</span> : null}
              </button>
            ))}
          </nav>
        </div>

        {/* Body */}
        <div ref={bodyRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {tab === "Overview" && (
            <>
              {comp.leap_benchmark && (
                <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/70 via-white to-purple-50/60 p-3.5 shadow-sm space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                      <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-900">
                        Breakout Leap Trajectory
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setTab("Breakout Leap")}
                      className="text-[11px] font-semibold text-indigo-700 hover:text-indigo-900 hover:underline inline-flex items-center gap-1"
                    >
                      View playbook <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                  <p className="text-xs text-ink leading-relaxed">
                    <strong className="text-ink font-semibold">Origin:</strong> {comp.leap_benchmark.origin_story}
                  </p>
                  <div className="flex flex-wrap gap-1 items-center pt-1">
                    <span className="text-[10px] uppercase font-bold text-ink-faint">Marquee Clients:</span>
                    {(comp.leap_benchmark.flagship_clients ?? []).slice(0, 4).map((c, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded-md bg-white border border-indigo-100 text-[10px] font-semibold text-indigo-900"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {comp.relevance_reason && (
                <div className="rounded-xl bg-white border border-line p-3.5">
                  <div className={H}>Why they compete with you</div>
                  <p className="mt-1 text-sm text-ink leading-relaxed">{comp.relevance_reason}</p>
                </div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>Price</div>
                  <div className={cn("mt-0.5 text-sm font-semibold", rival.hasRealPrice ? "text-ink" : "text-ink-faint")}>
                    {rival.priceLabel}
                  </div>
                </div>
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>Customer rating</div>
                  <div className="mt-0.5">
                    <RatingBadge rating={rival.rating} reviews={rival.reviewCount} />
                  </div>
                </div>
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>In business since</div>
                  <div className="mt-0.5 text-sm font-semibold text-ink">
                    {comp.founded ? (
                      <>
                        {comp.founded}
                        {(() => {
                          const years = new Date().getFullYear() - Number(comp.founded);
                          return Number.isFinite(years) && years > 0 ? (
                            <span className="text-xs font-normal text-ink-faint ml-1">({years}y)</span>
                          ) : null;
                        })()}
                      </>
                    ) : (
                      <span className="text-ink-faint font-normal" title="Not stated on any page we read">—</span>
                    )}
                  </div>
                </div>
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>Headquarters</div>
                  <div className="mt-0.5 text-sm font-semibold text-ink truncate" title={comp.headquarters ?? comp.operating_locations?.join(", ")}>
                    {comp.headquarters ?? (comp.operating_locations?.[0] ? comp.operating_locations[0] : <span className="text-ink-faint font-normal" title="Not stated on any page we read">—</span>)}
                  </div>
                </div>
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>Product catalog</div>
                  <div className="mt-0.5 text-sm font-semibold text-ink truncate">
                    {comp.product_catalog_count ? (
                      `${comp.product_catalog_count} models`
                    ) : comp.other_products?.length ? (
                      `${comp.other_products.length} other models`
                    ) : (
                      <span className="text-ink-faint font-normal" title="Catalogue size not stated">—</span>
                    )}
                  </div>
                </div>
                <div className="rounded-xl bg-white border border-line p-3">
                  <div className={H}>Profile completeness</div>
                  <div className="mt-1.5 flex items-center gap-2">
                    <CompletenessDots have={rival.completeness.have} missing={rival.completeness.missing} />
                    <span className="text-xs text-ink-soft">
                      {rival.completeness.have.length}/{rival.completeness.have.length + rival.completeness.missing.length}
                    </span>
                  </div>
                </div>
              </div>

              <FactSheet comp={comp} />


              <ListingPrices listings={comp.channel_listings ?? []} />

              {comp.buying_patterns && (
                <div className="rounded-xl bg-[#FAF6EE] border border-[#E9DFC7] p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#C7431F]">
                      Commercial Buying Patterns & Sales Channels
                    </span>
                    {comp.buying_patterns.sales_velocity_signals && comp.buying_patterns.sales_velocity_signals.length > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-[#E1D7C8] text-[#1F1A17]">
                        {comp.buying_patterns.sales_velocity_signals[0]}
                      </span>
                    )}
                  </div>

                  {comp.buying_patterns.reverse_engineered_strategy && (
                    <p className="text-xs text-[#2E2822] leading-relaxed italic border-l-2 border-[#C7431F] pl-2.5">
                      "{comp.buying_patterns.reverse_engineered_strategy}"
                    </p>
                  )}

                  {comp.buying_patterns.sales_channels && comp.buying_patterns.sales_channels.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase text-[#8A8176] block">Active Sales Channels:</span>
                      <div className="flex flex-wrap gap-1">
                        {comp.buying_patterns.sales_channels.map((ch, idx) => (
                          <span key={idx} className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-white border border-[#E1D7C8] text-[#1F1A17]">
                            {ch}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {(comp.buying_patterns.promotional_incentives?.length || comp.buying_patterns.buying_triggers?.length) ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] pt-1">
                      {comp.buying_patterns.promotional_incentives && comp.buying_patterns.promotional_incentives.length > 0 && (
                        <div className="p-2 rounded-lg bg-white border border-[#EFE7DB]">
                          <span className="text-[9px] font-bold uppercase text-[#8A8176] block mb-0.5">Pricing & Offers</span>
                          <span className="text-[#1F1A17] font-medium leading-tight">{comp.buying_patterns.promotional_incentives.join(" • ")}</span>
                        </div>
                      )}
                      {comp.buying_patterns.buying_triggers && comp.buying_patterns.buying_triggers.length > 0 && (
                        <div className="p-2 rounded-lg bg-white border border-[#EFE7DB]">
                          <span className="text-[9px] font-bold uppercase text-[#8A8176] block mb-0.5">Conversion Triggers</span>
                          <span className="text-[#1F1A17] font-medium leading-tight">{comp.buying_patterns.buying_triggers.join(" • ")}</span>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              )}

              <div className="rounded-xl bg-white border border-line overflow-hidden">
                <div className={cn(H, "px-3.5 pt-3 pb-2")}>What buyers compare</div>
                {driverRows.length === 0 && otherAttrs.length === 0 ? (
                  <div className="px-3.5 pb-3">
                    <Empty>No specifications found on their pages.</Empty>
                  </div>
                ) : (
                  <dl className="divide-y divide-line">
                    {driverRows.map(([d, v]) => (
                      <div key={d} className="grid grid-cols-5 gap-3 px-3.5 py-2">
                        <dt className="col-span-2 text-xs font-semibold text-ink">{d.split(":")[0].replace(/_/g, " ")}</dt>
                        <dd className={cn("col-span-3 text-xs", v ? "text-ink-soft" : "text-ink-faint")} title={v ? undefined : "Not stated on their pages"}>
                          {v ?? "—"}
                        </dd>
                      </div>
                    ))}
                    {otherAttrs.map(([k, v]) => (
                      <div key={k} className="grid grid-cols-5 gap-3 px-3.5 py-2">
                        <dt className="col-span-2 text-xs text-ink-soft">{k.replace(/_/g, " ")}</dt>
                        <dd className="col-span-3 text-xs text-ink-soft">{v}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </>
          )}

          {tab === "Breakout Leap" && comp.leap_benchmark && (
            <div className="space-y-4">
              {/* Scale & Origins Header */}
              <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/70 via-white to-purple-50/60 p-4 shadow-sm space-y-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-indigo-600 text-white">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-display text-sm font-bold text-indigo-950">
                      Breakout Trajectory & Scale
                    </h3>
                    <p className="text-[11px] text-indigo-800">
                      From wedge peer origins to category leader
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                  <div className="rounded-lg bg-white/80 border border-indigo-100 p-2.5 space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-indigo-900">
                      <Compass className="w-3 h-3 text-indigo-600" /> Origin Story
                    </div>
                    <p className="text-xs text-ink leading-relaxed">
                      {comp.leap_benchmark.origin_story}
                    </p>
                  </div>

                  <div className="rounded-lg bg-white/80 border border-indigo-100 p-2.5 space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-indigo-900">
                      <TrendingUp className="w-3 h-3 text-indigo-600" /> Current Scale & Valuation Tier
                    </div>
                    <p className="text-xs text-ink font-medium leading-relaxed">
                      {comp.leap_benchmark.current_scale}
                    </p>
                  </div>
                </div>
              </div>

              {/* Flagship Enterprise Clients */}
              <section className="rounded-xl bg-white border border-line p-4 space-y-2.5 shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                    <span className={H}>Marquee Enterprise Clients & Case Studies</span>
                  </div>
                  <span className="text-[10px] font-bold text-ink-faint">
                    {(comp.leap_benchmark.flagship_clients ?? []).length} landed
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(comp.leap_benchmark.flagship_clients ?? []).map((c, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-800 shadow-2xs"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              </section>

              {/* Strategic Network Deals & Partnerships */}
              <section className="rounded-xl bg-white border border-line p-4 space-y-2.5 shadow-2xs">
                <div className="flex items-center gap-1.5">
                  <Compass className="w-3.5 h-3.5 text-blue-600" />
                  <span className={H}>Strategic Network Deals & Alliances</span>
                </div>
                <ul className="space-y-1.5">
                  {(comp.leap_benchmark.network_and_deals ?? []).map((deal, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-lg bg-blue-50/50 border border-blue-100 px-3 py-2 text-xs text-blue-950 leading-relaxed"
                    >
                      <Check className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                      <span>{deal}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Pricing Power Leap */}
              <section className="rounded-xl bg-white border border-line p-4 space-y-2 shadow-2xs">
                <div className="flex items-center gap-1.5">
                  <DollarSign className="w-3.5 h-3.5 text-emerald-600" />
                  <span className={H}>Pricing Power Expansion</span>
                </div>
                <p className="text-xs text-ink leading-relaxed">
                  {comp.leap_benchmark.pricing_power_leap}
                </p>
              </section>

              {/* Leap Catalysts */}
              <section className="rounded-xl bg-white border border-line p-4 space-y-2.5 shadow-2xs">
                <div className="flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-amber-500" />
                  <span className={H}>Strategic Inflection Points (Leap Catalysts)</span>
                </div>
                <ul className="space-y-1.5">
                  {(comp.leap_benchmark.leap_catalysts ?? []).map((cat, i) => (
                    <li
                      key={i}
                      className="rounded-lg bg-amber-50/60 border border-amber-200/80 px-3 py-2 text-xs text-amber-950 leading-relaxed"
                    >
                      {cat}
                    </li>
                  ))}
                </ul>
              </section>

              {/* Merchant Emulation Playbook */}
              <section className="rounded-xl bg-gradient-to-br from-emerald-50/80 via-white to-teal-50/60 border border-emerald-200 p-4 space-y-2.5 shadow-sm">
                <div className="flex items-center gap-1.5">
                  <Target className="w-4 h-4 text-emerald-700" />
                  <span className="text-xs font-bold uppercase tracking-wider text-emerald-900">
                    How You Can Execute This Leap (Playbook)
                  </span>
                </div>
                <div className="space-y-2">
                  {(comp.leap_benchmark.merchant_takeaway_playbook ?? []).map((play, i) => (
                    <div
                      key={i}
                      className="rounded-lg bg-white border border-emerald-100 p-2.5 text-xs text-emerald-950 leading-relaxed flex items-start gap-2.5 shadow-2xs"
                    >
                      <span className="flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-800 font-bold text-[10px] shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <span>{play}</span>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          {tab === "Customers" && (
            <>
              <div className="rounded-xl bg-white border border-line p-3.5 space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-emerald-700">{rival.praise.length} praise</span>
                  <span className="font-semibold text-rose-700">
                    {rival.complaints.length} complaint{rival.complaints.length === 1 ? "" : "s"}
                  </span>
                </div>
                <SentimentBar praise={rival.praise.length} complaints={rival.complaints.length} />
                <p className="text-[11px] text-ink-faint">From review sites and forums. Mixed reviews count as complaints.</p>
              </div>

              {/* Synthesized context sits above the raw quotes: the consensus and the mechanism
                  are what a merchant acts on; the quotes below are the evidence for them. */}
              {rc && (
                <>
                  {rc.overall_sentiment_consensus && (
                    <section className="space-y-1.5">
                      <div className={H}>Consensus</div>
                      <p className="rounded-xl bg-white border border-line p-3 text-xs text-ink-soft leading-relaxed">
                        {rc.overall_sentiment_consensus}
                      </p>
                    </section>
                  )}
                  {!!rc.top_complaint_drivers?.length && (
                    <section className="space-y-2">
                      <div className={cn(H, "flex items-center gap-1.5")}>
                        <ThumbsDown className="w-3 h-3 text-rose-500" /> Why customers complain
                      </div>
                      {rc.top_complaint_drivers.map((a, i) => (
                        <AspectCard key={i} aspect={a} tone="negative" />
                      ))}
                    </section>
                  )}
                  {!!rc.top_praise_drivers?.length && (
                    <section className="space-y-2">
                      <div className={cn(H, "flex items-center gap-1.5")}>
                        <ThumbsUp className="w-3 h-3 text-emerald-500" /> Why customers stay
                      </div>
                      {rc.top_praise_drivers.map((a, i) => (
                        <AspectCard key={i} aspect={a} tone="positive" />
                      ))}
                    </section>
                  )}
                  {!!rc.unmet_customer_needs?.length && (
                    <section className="space-y-1.5">
                      <div className={H}>What customers still want</div>
                      <ul className="space-y-1">
                        {rc.unmet_customer_needs.map((n, i) => (
                          <li key={i} className="text-xs text-ink-soft leading-relaxed pl-2 border-l-2 border-line">
                            {n}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {rc.counter_positioning_angle && (
                    <section className="rounded-xl bg-amber-50 border border-amber-200 p-3 space-y-1">
                      <div className="flex items-center gap-1.5">
                        <Target className="w-3.5 h-3.5 text-amber-600" />
                        <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
                          Your counter-angle
                        </span>
                      </div>
                      <p className="text-xs text-amber-900 leading-relaxed">{rc.counter_positioning_angle}</p>
                    </section>
                  )}
                </>
              )}
              <section className="space-y-2">
                <div className={cn(H, "flex items-center gap-1.5")}>
                  <Quote className="w-3 h-3 text-emerald-500" /> Praise, verbatim
                </div>
                {rival.praise.length ? (
                  rival.praise.map((p, i) => (
                    <blockquote key={i} className="rounded-lg bg-white border-l-2 border-emerald-300 px-3 py-2 text-xs text-ink-soft leading-relaxed">
                      {p}
                    </blockquote>
                  ))
                ) : (
                  <Empty>No customer praise surfaced.</Empty>
                )}
              </section>
              <section className="space-y-2">
                <div className={cn(H, "flex items-center gap-1.5")}>
                  <Quote className="w-3 h-3 text-rose-500" /> Complaints, verbatim
                </div>
                {rival.complaints.length ? (
                  rival.complaints.map((c, i) => (
                    <blockquote key={i} className="rounded-lg bg-white border-l-2 border-rose-300 px-3 py-2 text-xs text-ink-soft leading-relaxed">
                      {c}
                    </blockquote>
                  ))
                ) : (
                  <Empty>No customer complaints surfaced.</Empty>
                )}
              </section>
            </>
          )}

          {tab === "Marketing" && (
            <>
              <section className="space-y-2">
                <div className={H}>What they claim on their website</div>
                {rival.claims.length ? (
                  <ul className="space-y-1.5">
                    {rival.claims.map((c, i) => (
                      <li key={i} className="rounded-lg bg-white border border-line px-3 py-2 text-xs text-ink leading-relaxed">
                        {c}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>No marketing claims found on their pages.</Empty>
                )}
              </section>
              <section className="space-y-2">
                <div className={cn(H, "flex items-center gap-1.5")}>
                  <Megaphone className="w-3 h-3 text-violet-500" /> Ads running now
                </div>
                {rival.ads.length ? (
                  rival.ads.map((a, i) => (
                    <div key={i} className="rounded-lg bg-violet-50 border border-violet-100 px-3 py-2 text-xs text-violet-950 leading-relaxed flex gap-2">
                      <Quote className="w-3 h-3 text-violet-400 shrink-0 mt-0.5" />
                      <span>{a}</span>
                    </div>
                  ))
                ) : (
                  <Empty>No live ads found in the Meta or Google ad libraries.</Empty>
                )}
              </section>
            </>
          )}

          {tab === "History" && (
            <>
              <section className="space-y-2">
                <div className={cn(H, "flex items-center gap-1.5")}>
                  <TrendingUp className="w-3 h-3 text-amber-500" /> Changed since our last scan
                </div>
                {rival.changes.length ? (
                  <ul className="space-y-1.5">
                    {rival.changes.map((c, i) => (
                      <li key={i} className="rounded-lg bg-amber-50 border border-amber-100 px-3 py-2 text-xs text-amber-950 leading-relaxed">
                        <span className="font-mono text-[10px] text-amber-700 mr-1.5">{c.observed_at}</span>
                        {describeChange(c)}
                        {c.source === "merchant" && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded bg-white text-[10px] font-semibold text-amber-800">your correction</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty>No changes yet — changes appear when the same product is researched again.</Empty>
                )}
              </section>
              <section className="space-y-2">
                <div className={H}>Company timeline</div>
                {comp.founded && (
                  <p className="text-xs text-ink">
                    Founded <strong>{comp.founded}</strong>
                    {(() => {
                      const years = new Date().getFullYear() - Number(comp.founded);
                      return Number.isFinite(years) && years > 0 ? ` · ${years} years in business` : "";
                    })()}
                  </p>
                )}
                {comp.milestones?.length ? (
                  <ol className="relative border-l border-line ml-1 space-y-2.5">
                    {comp.milestones.map((m, i) => (
                      <li key={i} className="pl-4 relative text-xs text-ink-soft leading-relaxed">
                        <span className="absolute -left-[4.5px] top-1.5 w-2 h-2 rounded-full bg-ink" />
                        {m}
                      </li>
                    ))}
                  </ol>
                ) : (
                  !comp.founded && <Empty>No dated company events found on their pages.</Empty>
                )}
              </section>

              <section className="space-y-2">
                <div className={H}>Corporate presence & Product catalog</div>
                <div className="p-3.5 rounded-xl bg-white border border-line space-y-2.5 text-xs">
                  {comp.founded && (
                    <p className="text-ink">
                      Established in <strong>{comp.founded}</strong>
                      {(() => {
                        const years = new Date().getFullYear() - Number(comp.founded);
                        return Number.isFinite(years) && years > 0 ? ` (${years} years active)` : "";
                      })()}
                    </p>
                  )}
                  {comp.headquarters && (
                    <p className="text-ink">
                      Headquarters: <strong>{comp.headquarters}</strong>
                    </p>
                  )}
                  {comp.operating_locations && comp.operating_locations.length > 0 && (
                    <div>
                      <span className="text-ink-faint font-semibold uppercase tracking-wider text-[10px]">
                        Active branches & territories:
                      </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {comp.operating_locations.map((loc, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-md bg-canvas border border-line text-ink">
                            {loc}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {((comp.other_products && comp.other_products.length > 0) || comp.product_catalog_count) && (
                    <div className="pt-2 border-t border-line">
                      <span className="text-ink-faint font-semibold uppercase tracking-wider text-[10px]">
                        Other products & models in catalog ({comp.product_catalog_count ?? comp.other_products?.length}):
                      </span>
                      {comp.other_products && comp.other_products.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {comp.other_products.map((p, i) => (
                            <span key={i} className="px-2 py-0.5 rounded-md bg-canvas border border-line text-ink font-medium">
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </section>
            </>
          )}

          {tab === "Sources" && (
            <>
              <section className="space-y-2">
                <div className={H}>Pages this profile is built from</div>
                {comp.sources?.length ? (
                  <ul className="space-y-1">
                    {comp.sources.map((s, i) =>
                      safeHref(s) ? (
                        <li key={i}>
                          <a
                            href={safeHref(s)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between gap-2 rounded-lg bg-white border border-line px-3 py-2 text-xs text-ink-soft hover:text-ink hover:border-ink/30 transition"
                          >
                            <span className="truncate">
                              <span className="font-semibold text-ink">{hostOf(s)}</span>
                              <span className="text-ink-faint">{(() => { try { return new URL(s).pathname; } catch { return ""; } })()}</span>
                            </span>
                            <ExternalLink className="w-3 h-3 shrink-0" />
                          </a>
                        </li>
                      ) : null
                    )}
                  </ul>
                ) : (
                  <Empty>No source pages recorded.</Empty>
                )}
              </section>
              <section className="space-y-2">
                <div className={H}>Verbatim excerpts</div>
                {comp.factual_evidence?.length ? (
                  comp.factual_evidence.map((e, i) => (
                    <blockquote key={i} className="rounded-lg bg-white border-l-2 border-line px-3 py-2 text-xs text-ink-soft italic leading-relaxed">
                      {e}
                    </blockquote>
                  ))
                ) : (
                  <Empty>No verbatim excerpts kept.</Empty>
                )}
              </section>
            </>
          )}
        </div>

        <div className="bg-white border-t border-line px-5 py-2 text-[10px] text-ink-faint flex justify-between">
          <span>← → to switch rivals · Esc to close</span>
          {comp.as_of && <span>Evidence dated {comp.as_of}</span>}
        </div>
      </aside>
    </div>
  );
}
