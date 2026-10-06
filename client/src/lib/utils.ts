import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatScore(score: number): string {
  return score.toFixed(2);
}

export function formatScorePercentage(score: number): string {
  return `${Math.round(score * 100)}%`;
}

/**
 * Returns the URL only when it is http(s); research URLs come from web search and LLM
 * output, so anything else (e.g. `javascript:`) must never reach an href.
 */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

/** Human label for a competitor's pricing field ("detected" means mentioned but not extracted). */
export function pricingLabel(pricing: string | null | undefined): string {
  if (!pricing) return "Price not found";
  if (pricing === "detected") return "Pricing mentioned";
  return pricing;
}

export function truncateUrl(url: string, maxLength: number = 40): string {
  try {
    const parsed = new URL(url);
    const domain = parsed.hostname.replace(/^www\./, "");
    const path = parsed.pathname;
    const combined = `${domain}${path}`;
    return combined.length > maxLength
      ? `${combined.slice(0, maxLength)}…`
      : combined;
  } catch {
    return url.length > maxLength ? `${url.slice(0, maxLength)}…` : url;
  }
}
