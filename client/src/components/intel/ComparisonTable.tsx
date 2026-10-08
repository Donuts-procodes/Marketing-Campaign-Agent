import { useMemo, useState } from "react";
import { DynamicParameterTaxonomy } from "@/types/research";
import { RivalView, attributeFor, priceUnit } from "@/lib/rivalMetrics";
import { cn } from "@/lib/utils";
import { Avatar, CompletenessDots, RatingBadge } from "@/components/intel/RivalCard";
import { ArrowUpDown, ChevronDown, ChevronUp, LayoutGrid, Table2 } from "lucide-react";

type SortKey = "price" | "rating" | "praise" | "complaints" | "ads" | "profile";

const UNIT_RANK = { hour: 0, month: 1, year: 2, project: 3, other: 4 } as const;

const SORTERS: Record<SortKey, (r: RivalView) => number | null> = {
  // Grouped by unit first, so an hourly rate is never ranked against a project fee.
  price: (r) => (r.priceValue == null ? null : UNIT_RANK[priceUnit(r.comp.pricing_model)] * 1e12 + r.priceValue),
  rating: (r) => r.rating,
  praise: (r) => r.praise.length,
  complaints: (r) => r.complaints.length,
  ads: (r) => r.ads.length,
  profile: (r) => r.completeness.score,
};

interface ComparisonTableProps {
  rivals: RivalView[];
  taxonomy?: DynamicParameterTaxonomy;
  merchantName?: string;
  merchantPrice?: string | null;
  onOpen: (index: number) => void;
}

export function ComparisonTable({ rivals, taxonomy, merchantName, merchantPrice, onOpen }: ComparisonTableProps) {
  const [mode, setMode] = useState<"glance" | "specs">("glance");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" } | null>(null);
  const drivers = taxonomy?.critical_jtbd_drivers ?? [];

  const sorted = useMemo(() => {
    if (!sort) return rivals;
    const get = SORTERS[sort.key];
    // Rivals with no value always sink, whichever direction is chosen.
    return [...rivals].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sort.dir === "asc" ? va - vb : vb - va;
    });
  }, [rivals, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s?.key !== key ? { key, dir: key === "price" ? "asc" : "desc" } : s.dir === "desc" ? { key, dir: "asc" } : null
    );

  // Render helpers, not components: a component declared here would remount on every render.
  const sortHead = (k: SortKey, children: string, className?: string) => {
    const active = sort?.key === k;
    return (
      <th
        key={k}
        scope="col"
        aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"}
        className={cn("px-3 py-2.5 font-semibold", className)}
      >
        <button
          type="button"
          onClick={() => toggleSort(k)}
          className={cn("inline-flex items-center gap-1 hover:text-ink transition", active && "text-ink")}
        >
          {children}
          {active ? (
            sort!.dir === "asc" ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
          ) : (
            <ArrowUpDown className="w-3 h-3 opacity-40" />
          )}
        </button>
      </th>
    );
  };

  const stickyName = (r: RivalView) => (
    <th scope="row" className="sticky left-0 z-10 bg-white group-hover:bg-[#FBF8F2] px-3 py-2.5 text-left font-normal transition-colors">
      <div className="flex items-center gap-2.5 min-w-[170px]">
        <Avatar rival={r} />
        <div className="min-w-0">
          <div className="text-xs font-bold text-ink truncate max-w-[160px]">{r.name}</div>
          <div className="text-[10px] text-ink-faint truncate max-w-[160px]">{r.host ?? r.subtitle ?? ""}</div>
        </div>
      </div>
    </th>
  );

  return (
    <div className="rounded-2xl border border-line bg-white shadow-card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-line">
        <p className="text-[11px] text-ink-faint">
          {mode === "glance"
            ? "Click a column to sort · click a rival to open its profile. Prices may use different units."
            : `Each rival against the ${drivers.length} factors buyers in your market weigh most.`}
        </p>
        <div className="inline-flex rounded-lg bg-canvas p-0.5 text-xs font-semibold" role="tablist">
          {(
            [
              ["glance", "At a glance", LayoutGrid],
              ["specs", "Specs", Table2],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              onClick={() => setMode(id)}
              disabled={id === "specs" && drivers.length === 0}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition disabled:opacity-40",
                mode === id ? "bg-white text-ink shadow-card" : "text-ink-soft hover:text-ink"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="bg-canvas/60 text-[10px] uppercase tracking-wider text-ink-faint">
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-[#FAF8F3] px-3 py-2.5 font-semibold">
                Rival
              </th>
              {mode === "glance" ? (
                <>
                  {sortHead("price", "Price")}
                  {sortHead("rating", "Rating")}
                  {sortHead("praise", "Praise")}
                  {sortHead("complaints", "Complaints")}
                  {sortHead("ads", "Live ads")}
                  {sortHead("profile", "Profile", "text-right")}
                </>
              ) : (
                drivers.map((d) => (
                  <th key={d} scope="col" className="px-3 py-2.5 font-semibold min-w-[160px]" title={d}>
                    {d.split(":")[0].replace(/_/g, " ")}
                  </th>
                ))
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {mode === "glance" && merchantName && (
              <tr className="bg-[#FFFBEF]">
                <th scope="row" className="sticky left-0 z-10 bg-[#FFFBEF] px-3 py-2.5 text-left font-normal">
                  <div className="flex items-center gap-2.5">
                    <span className="w-10 h-10 rounded-xl bg-ink text-white flex items-center justify-center text-[10px] font-bold">
                      YOU
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-ink truncate max-w-[160px]">{merchantName}</div>
                      <div className="text-[10px] text-ink-faint">Your product</div>
                    </div>
                  </div>
                </th>
                <td className="px-3 py-2.5 font-semibold text-ink">{merchantPrice ?? <span className="text-ink-faint font-normal">—</span>}</td>
                <td colSpan={5} className="px-3 py-2.5 text-[11px] text-ink-faint">
                  Your own row for comparison
                </td>
              </tr>
            )}
            {sorted.map((r) => (
              <tr
                key={r.key}
                onClick={() => onOpen(r.index)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(r.index))}
                tabIndex={0}
                className="group cursor-pointer hover:bg-[#FBF8F2] focus-visible:outline-none focus-visible:bg-[#FBF8F2] transition-colors"
              >
                {stickyName(r)}
                {mode === "glance" ? (
                  <>
                    <td className={cn("px-3 py-2.5 max-w-[200px]", r.hasRealPrice ? "text-ink font-semibold" : "text-ink-faint")}>
                      <span className="line-clamp-2" title={r.priceLabel}>
                        {r.priceLabel}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <RatingBadge rating={r.rating} reviews={r.reviewCount} />
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span className={r.praise.length ? "text-emerald-700 font-semibold" : "text-ink-faint"}>{r.praise.length}</span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span className={r.complaints.length ? "text-rose-700 font-semibold" : "text-ink-faint"}>{r.complaints.length}</span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {r.ads.length ? (
                        <span className="inline-flex px-1.5 py-0.5 rounded-md bg-violet-50 text-violet-800 font-semibold">{r.ads.length}</span>
                      ) : (
                        <span className="text-ink-faint">0</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <CompletenessDots have={r.completeness.have} missing={r.completeness.missing} />
                    </td>
                  </>
                ) : (
                  drivers.map((d) => {
                    const v = attributeFor(r.comp, d);
                    return (
                      <td key={d} className="px-3 py-2.5 align-top max-w-[240px]">
                        {v ? (
                          <span className="text-ink-soft leading-relaxed line-clamp-3" title={v}>
                            {v}
                          </span>
                        ) : (
                          <span className="text-ink-faint italic">Not disclosed</span>
                        )}
                      </td>
                    );
                  })
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
