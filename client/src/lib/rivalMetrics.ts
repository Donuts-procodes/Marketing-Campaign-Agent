import { CompetitorProfile } from "@/types/research";

/**
 * Derived, display-ready view of each competitor. Everything here is computed from data the
 * research agent gathered; nothing is inferred or recommended.
 */

export interface RivalView {
  key: string;
  index: number;
  comp: CompetitorProfile;
  name: string;
  subtitle: string | null;
  /** The rival's own website, or null when no source is on their domain. */
  siteUrl: string | null;
  host: string | null;
  initials: string;
  tone: string;
  priceLabel: string;
  priceValue: number | null;
  hasRealPrice: boolean;
  rating: number | null;
  reviewCount: number | null;
  praise: string[];
  complaints: string[];
  ads: string[];
  claims: string[];
  changes: NonNullable<CompetitorProfile["change_history"]>;
  completeness: { score: number; have: string[]; missing: string[] };
  relevance: number | null;
}

const AVATAR_TONES = [
  "bg-[#DCE9F7] text-[#0F2D4A]",
  "bg-[#FBE0EE] text-[#3D102A]",
  "bg-[#FDF1C4] text-[#2D2306]",
  "bg-[#DDEFD3] text-[#19350E]",
  "bg-[#EADCF1] text-[#3B154C]",
  "bg-[#F7E3D3] text-[#4A2208]",
];

export function hostOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

const compact = (s: string) => s.toLowerCase().replace(/\(.*?\)/g, "").replace(/[^a-z0-9]/g, "");

/**
 * The rival's own website among its sources. The first source is often a directory or a
 * listicle (clutch.co, a "top 10 agencies" post), which is not where the rival lives.
 */
export function ownSite(comp: CompetitorProfile): string | null {
  const brand = compact(comp.brand_name || comp.product_name || "");
  if (brand.length < 3) return null;
  for (const url of comp.sources ?? []) {
    const host = hostOf(url);
    if (!host) continue;
    const label = compact(host.split(".").slice(0, -1).join(""));
    if (label.includes(brand) || (label.length >= 4 && brand.includes(label))) return url;
  }
  return null;
}

function initialsOf(name: string): string {
  const words = name.replace(/\(.*?\)/g, "").trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}

function hashOf(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

/** Strips scraper and markdown boilerplate that would otherwise be shown as a customer quote. */
export function cleanSnippet(text: string): string {
  return text
    .replace(/^Title:\s*[^|]+\|\s*/i, "")
    .replace(/#{1,6}\s*/g, "")
    .replace(/\*{2,}/g, "")
    .replace(/##\s*Post details\.?\s*##\s*Content\.?\s*##\s*Top Comments\.?/i, "")
    .replace(/^(?:written by|by)\s+[A-Za-z0-9 "'.,-]+?(?:—|-|:|\.\s+)/i, "")
    .replace(/^Web ad mention:\s*["']?/i, "")
    .replace(/["']$/, "")
    .trim();
}

const PRICE_RE = /(?:[$€£₹]|\b(?:rs\.?|inr|usd|eur|gbp)\s?)\s?(\d[\d,]*(?:\.\d+)?)\s*(k\b)?/i;

/**
 * First stated amount in a pricing string, for sorting only. Units differ between rivals
 * ("/mo", "/hr", "per project"), so the label is always shown next to it.
 */
export function parsePrice(pricing: string | null | undefined): number | null {
  if (!pricing || pricing === "detected") return null;
  const m = pricing.match(PRICE_RE);
  if (!m) return null;
  const value = Number(m[1].replace(/,/g, ""));
  if (!Number.isFinite(value)) return null;
  return m[2] ? value * 1000 : value;
}

export type PriceUnit = "hour" | "month" | "year" | "project" | "other";

const UNIT_LABEL: Record<PriceUnit, string> = {
  hour: "hourly rate",
  month: "monthly price",
  year: "yearly price",
  project: "project price",
  other: "listed price",
};

/** What a stated price is per. "$150/hr" and "$5,000 per project" must never be compared. */
export function priceUnit(pricing: string | null | undefined): PriceUnit {
  const p = (pricing ?? "").toLowerCase();
  if (/\/\s*h(ou)?r\b|per\s+hour|hourly|\/\s*hour/.test(p)) return "hour";
  if (/\/\s*mo|per\s+month|monthly|a month/.test(p)) return "month";
  if (/\/\s*y(ea)?r\b|per\s+year|annual|yearly/.test(p)) return "year";
  if (/project|engagement|one[-\s]?time|million|build|fixed/.test(p)) return "project";
  return "other";
}

export function profileCompleteness(comp: CompetitorProfile) {
  const checks: Array<[string, boolean]> = [
    // "detected" means a page mentioned pricing without an amount; the quality score refuses it too.
    ["Pricing", !!comp.pricing_model && comp.pricing_model !== "detected"],
    ["Claims", (comp.core_claims?.length ?? 0) > 0],
    ["Praise", (comp.strengths_mined?.length ?? 0) > 0],
    ["Complaints", (comp.weaknesses_mined?.length ?? 0) > 0],
    ["Ads", (comp.ad_hooks?.length ?? 0) > 0],
    ["Specs", Object.values(comp.dynamic_attributes ?? {}).some(Boolean)],
  ];
  const have = checks.filter(([, ok]) => ok).map(([label]) => label);
  const missing = checks.filter(([, ok]) => !ok).map(([label]) => label);
  return { score: have.length / checks.length, have, missing };
}

export function toRivalView(comp: CompetitorProfile, index: number): RivalView {
  const name = comp.brand_name || comp.product_name || "Unnamed competitor";
  const hasRealPrice = !!comp.pricing_model && comp.pricing_model !== "detected";
  const rating = comp.rating != null ? Number.parseFloat(String(comp.rating)) : NaN;
  const dedupe = (items: string[] | undefined) =>
    Array.from(new Set((items ?? []).map(cleanSnippet).filter(Boolean)));
  const siteUrl = ownSite(comp);

  return {
    key: `${name}-${index}`,
    index,
    comp,
    name,
    subtitle: comp.product_name && comp.product_name !== comp.brand_name ? comp.product_name : null,
    siteUrl,
    host: hostOf(siteUrl),
    initials: initialsOf(name),
    tone: AVATAR_TONES[hashOf(name) % AVATAR_TONES.length],
    priceLabel: !comp.pricing_model
      ? "Not published"
      : comp.pricing_model === "detected"
        ? "On request"
        : comp.pricing_model,
    priceValue: parsePrice(comp.pricing_model),
    hasRealPrice,
    rating: Number.isFinite(rating) && rating > 0 && rating <= 5 ? rating : null,
    reviewCount: comp.review_count ?? null,
    praise: dedupe(comp.strengths_mined),
    complaints: dedupe(comp.weaknesses_mined),
    ads: dedupe(comp.ad_hooks),
    claims: dedupe(comp.core_claims),
    // Newest first: the most recent move is the one a merchant notices.
    changes: [...(comp.change_history ?? [])].reverse(),
    completeness: profileCompleteness(comp),
    relevance: typeof comp.relevance_score === "number" ? comp.relevance_score : null,
  };
}

export function relevanceLabel(score: number | null): { label: string; cls: string } | null {
  if (score == null) return null;
  if (score >= 0.75) return { label: "Direct rival", cls: "bg-ink text-white" };
  if (score >= 0.5) return { label: "Close rival", cls: "bg-[#EDE7D8] text-ink" };
  return { label: "Adjacent", cls: "bg-zinc-100 text-ink-soft" };
}

/** The critical-driver value for a rival, tolerant of key spelling differences. */
export function attributeFor(comp: CompetitorProfile, driver: string): string | null {
  const attrs = comp.dynamic_attributes ?? {};
  const head = driver.split(":")[0].trim();
  const snake = head.toLowerCase().replace(/[\s-]+/g, "_");
  const direct = attrs[driver] ?? attrs[head] ?? attrs[snake];
  if (direct) return direct;
  const fuzzy = Object.entries(attrs).find(([k, v]) => v && k.toLowerCase().includes(head.toLowerCase()));
  return fuzzy?.[1] ?? null;
}

export interface KeyFact {
  id: string;
  label: string;
  value: string;
  detail: string;
  rivalIndex: number | null;
}

/** A handful of cross-rival facts worth reading before any individual profile. */
export function keyFacts(rivals: RivalView[]): KeyFact[] {
  const facts: KeyFact[] = [];

  const priced = rivals.filter((r) => r.priceValue != null);
  // Compare only within one unit: the unit most rivals quote in.
  const byUnit = new Map<PriceUnit, RivalView[]>();
  for (const r of priced) {
    const u = priceUnit(r.comp.pricing_model);
    byUnit.set(u, [...(byUnit.get(u) ?? []), r]);
  }
  const [unit, sameUnit] = [...byUnit.entries()].sort((a, b) => b[1].length - a[1].length)[0] ?? [null, []];
  if (unit && sameUnit.length >= 2) {
    const lo = sameUnit.reduce((a, b) => (b.priceValue! < a.priceValue! ? b : a));
    const hi = sameUnit.reduce((a, b) => (b.priceValue! > a.priceValue! ? b : a));
    const others = priced.length - sameUnit.length;
    facts.push({
      id: "price",
      label: `Lowest ${UNIT_LABEL[unit]}`,
      value: lo.name,
      detail: `${lo.priceLabel} · highest: ${hi.name} (${hi.priceLabel})${others ? ` · ${others} priced differently` : ""}`,
      rivalIndex: lo.index,
    });
  } else {
    const published = rivals.filter((r) => r.hasRealPrice).length;
    facts.push({
      id: "price",
      label: "Published pricing",
      value: `${published} of ${rivals.length}`,
      detail: !published
        ? "no rival publishes a price — likely quote-based"
        : priced.length >= 2
          ? "rivals publish prices, but in different units (hourly, per project…)"
          : "rivals state a price publicly",
      rivalIndex: priced[0]?.index ?? null,
    });
  }

  const rated = rivals.filter((r) => r.rating != null);
  if (rated.length) {
    const best = rated.reduce((a, b) => (b.rating! > a.rating! ? b : a));
    facts.push({
      id: "rating",
      label: "Best rated",
      value: best.name,
      detail: `${best.rating!.toFixed(1)} / 5${best.reviewCount ? ` from ${best.reviewCount.toLocaleString()} reviews` : ""}`,
      rivalIndex: best.index,
    });
  }

  const complained = rivals.filter((r) => r.complaints.length > 0);
  if (complained.length) {
    const worst = complained.reduce((a, b) => (b.complaints.length > a.complaints.length ? b : a));
    facts.push({
      id: "complaints",
      label: "Most complaints found",
      value: worst.name,
      detail: `${worst.complaints.length} customer complaint${worst.complaints.length === 1 ? "" : "s"} on review sites`,
      rivalIndex: worst.index,
    });
  }

  const advertising = rivals.filter((r) => r.ads.length > 0);
  facts.push({
    id: "ads",
    label: "Advertising right now",
    value: `${advertising.length} of ${rivals.length}`,
    detail: advertising.length
      ? advertising.map((r) => r.name).join(", ")
      : "no live ads found in the ad libraries",
    rivalIndex: advertising.length === 1 ? advertising[0].index : null,
  });

  const moved = rivals.filter((r) => r.changes.length > 0);
  if (moved.length) {
    facts.push({
      id: "changes",
      label: "Changed since last scan",
      value: `${moved.length} rival${moved.length === 1 ? "" : "s"}`,
      detail: moved.map((r) => r.name).join(", "),
      rivalIndex: moved.length === 1 ? moved[0].index : null,
    });
  }

  return facts;
}

export function confidenceOf(dqs: number, assumptionsTagged: boolean) {
  if (dqs >= 0.85 && !assumptionsTagged)
    return { label: "High confidence", tone: "bg-emerald-50 text-emerald-800 border-emerald-200", dot: "bg-emerald-500" };
  if (dqs >= 0.65)
    return { label: "Good confidence", tone: "bg-amber-50 text-amber-800 border-amber-200", dot: "bg-amber-500" };
  return { label: "Limited data", tone: "bg-rose-50 text-rose-800 border-rose-200", dot: "bg-rose-500" };
}
