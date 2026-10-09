import { CompetitorProfile, FieldStatus } from "@/types/research";
import { safeHref, cn } from "@/lib/utils";
import { ExternalLink } from "lucide-react";

/**
 * Every profile fact with where it came from, or why it is missing.
 *
 * "Not available" hid four different situations. A merchant reading "Searched 14 pages,
 * including directory profiles and their own site; none states their revenue. Private companies
 * rarely publish revenue." knows the gap is real and not a bug; a value shows its page and the
 * sentence it was read from, so it can be checked in one click.
 */

const FACTS: Array<{ key: string; label: string; value: (c: CompetitorProfile) => string | null }> = [
  { key: "pricing_model", label: "Price", value: (c) => (c.pricing_model && c.pricing_model !== "detected" ? c.pricing_model : null) },
  { key: "rating", label: "Rating", value: (c) => (c.rating ? `${c.rating} / 5` : null) },
  { key: "review_count", label: "Reviews", value: (c) => (c.review_count != null ? c.review_count.toLocaleString() : null) },
  { key: "founded", label: "Founded", value: (c) => c.founded ?? null },
  { key: "headquarters", label: "Headquarters", value: (c) => c.headquarters ?? null },
  { key: "employee_count", label: "Team size", value: (c) => c.employee_count ?? null },
  { key: "annual_revenue", label: "Revenue", value: (c) => c.annual_revenue ?? null },
  { key: "funding", label: "Funding", value: (c) => c.funding ?? null },
];

const MISSING_LABEL: Record<string, string> = {
  not_stated: "Not stated anywhere we looked",
  removed: "Found, but removed",
  not_searched: "Not searched yet",
};

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Row({ label, value, status }: { label: string; value: string | null; status?: FieldStatus }) {
  const href = status?.source_url ? safeHref(status.source_url) : undefined;
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 py-2 border-b border-line last:border-b-0">
      <dt className="text-[11px] text-ink-faint pt-0.5">{label}</dt>
      <dd className="min-w-0">
        {value ? (
          <div className="space-y-0.5">
            <div className="text-sm font-semibold text-ink break-words">{value}</div>
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                title={status?.quote ? `“${status.quote}”` : undefined}
                className="inline-flex items-center gap-1 text-[11px] text-ink-faint hover:text-ink"
              >
                {hostOf(href)} <ExternalLink className="w-3 h-3" />
              </a>
            ) : status?.reason ? (
              <div className="text-[11px] text-ink-faint">{status.reason}</div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-0.5">
            <div className={cn("text-xs font-medium", status?.status === "removed" ? "text-amber-700" : "text-ink-faint")}>
              {MISSING_LABEL[status?.status ?? "not_searched"] ?? "Not found"}
            </div>
            {status?.reason && <p className="text-[11px] text-ink-faint leading-relaxed">{status.reason}</p>}
          </div>
        )}
      </dd>
    </div>
  );
}

export function FactSheet({ comp }: { comp: CompetitorProfile }) {
  const status = comp.fact_status ?? {};
  const found = FACTS.filter((f) => f.value(comp)).length;
  return (
    <section className="rounded-xl bg-white border border-line p-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">Company facts</div>
        <div className="text-[11px] text-ink-faint tabular-nums">
          {found} of {FACTS.length} found · never estimated
        </div>
      </div>
      <dl className="mt-1">
        {FACTS.map((f) => (
          <Row key={f.key} label={f.label} value={f.value(comp)} status={status[f.key]} />
        ))}
      </dl>
    </section>
  );
}
