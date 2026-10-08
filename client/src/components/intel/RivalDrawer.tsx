import { useEffect, useRef, useState } from "react";
import { DynamicParameterTaxonomy, CompetitorChange } from "@/types/research";
import { RivalView, attributeFor, hostOf, relevanceLabel } from "@/lib/rivalMetrics";
import { safeHref, cn } from "@/lib/utils";
import { Avatar, CompletenessDots, RatingBadge, SentimentBar } from "@/components/intel/RivalCard";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Megaphone,
  Quote,
  ThumbsDown,
  ThumbsUp,
  TrendingUp,
  X,
} from "lucide-react";

const TABS = ["Overview", "Customers", "Marketing", "History", "Sources"] as const;
type Tab = (typeof TABS)[number];

interface RivalDrawerProps {
  rivals: RivalView[];
  openIndex: number | null;
  taxonomy?: DynamicParameterTaxonomy;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

const H = "text-[10px] font-bold uppercase tracking-wider text-ink-faint";

function Empty({ children }: { children: string }) {
  return <p className="text-xs text-ink-faint italic py-1">{children}</p>;
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
            {TABS.map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 py-2 text-xs font-semibold border-b-2 whitespace-nowrap transition-colors",
                  tab === t ? "border-ink text-ink" : "border-transparent text-ink-faint hover:text-ink"
                )}
              >
                {t}
                {counts[t] ? <span className="ml-1 font-mono text-[10px] text-ink-faint">{counts[t]}</span> : null}
              </button>
            ))}
          </nav>
        </div>

        {/* Body */}
        <div ref={bodyRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {tab === "Overview" && (
            <>
              {comp.relevance_reason && (
                <div className="rounded-xl bg-white border border-line p-3.5">
                  <div className={H}>Why they compete with you</div>
                  <p className="mt-1 text-sm text-ink leading-relaxed">{comp.relevance_reason}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2">
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
                    {comp.founded ?? <span className="text-ink-faint font-normal">Not stated</span>}
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

              {rival.completeness.missing.length > 0 && (
                <p className="text-[11px] text-ink-faint">
                  Not found publicly: {rival.completeness.missing.join(", ").toLowerCase()}.
                </p>
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
                        <dd className={cn("col-span-3 text-xs", v ? "text-ink-soft" : "text-ink-faint italic")}>
                          {v ?? "Not disclosed"}
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
              <section className="space-y-2">
                <div className={cn(H, "flex items-center gap-1.5")}>
                  <ThumbsUp className="w-3 h-3 text-emerald-500" /> What customers praise
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
                  <ThumbsDown className="w-3 h-3 text-rose-500" /> What customers complain about
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
