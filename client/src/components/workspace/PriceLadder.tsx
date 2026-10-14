import { useMemo, useState } from "react";
import type { CompetitorProfile, ListingItem } from "@/types/research";

const ACCENT = "#C7431F"; // rival products
const INK = "#1F1A17"; // the merchant's own price (labelled)
const MUTED = "#8A8176";
const GRID = "#EFE7DB";

interface Dot {
  rival: string;
  name: string;
  site: string;
  url: string;
  price: number; // in the merchant's currency
  matched?: string | null;
  avg90?: number | null;
  rank?: number | null;
  variants?: number;
}

function money(v: number, ccy?: string | null): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: ccy || "USD", maximumFractionDigits: 0 }).format(v);
  } catch {
    return `${ccy ?? ""} ${Math.round(v).toLocaleString()}`.trim();
  }
}

/**
 * Every rival product price the listings read, one row per rival, on one axis in the merchant's
 * currency; the merchant's price is the reference line. Foreign prices use their stored FX rate.
 */
export function PriceLadder({
  competitors,
  merchantPrice,
  currency,
}: {
  competitors: CompetitorProfile[];
  merchantPrice?: number | null;
  currency?: string | null;
}) {
  const [hover, setHover] = useState<Dot | null>(null);
  const [only, setOnly] = useState<string>("");

  const rows = useMemo(() => {
    return competitors
      .map((c) => {
        const dots: Dot[] = [];
        for (const l of c.channel_listings ?? []) {
          // Same-currency listings have no rate; converted ones carry theirs.
          const rate = l.fx_rate ?? (l.currency && currency && l.currency !== currency ? null : 1);
          if (rate == null) continue;
          const items: ListingItem[] = l.items?.length
            ? l.items
            : l.selling_price != null
              ? [{ name: l.product ?? c.brand_name, url: l.url ?? "", selling_price: l.selling_price, avg_90d: l.avg_90d,
                   sales_rank: l.sales_rank, matched_product: l.matched_product }]
              : [];
          for (const it of items) {
            dots.push({
              rival: c.brand_name, name: it.name, site: l.site, url: it.url, price: it.selling_price * rate,
              matched: it.matched_product ?? null, avg90: it.avg_90d != null ? it.avg_90d * rate : null,
              rank: it.sales_rank ?? null, variants: it.variants ?? 1,
            });
          }
        }
        const shown = only ? dots.filter((d) => d.matched === only) : dots;
        const sorted = shown.map((d) => d.price).sort((a, b) => a - b);
        const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
        return { name: c.brand_name, dots: shown, median };
      })
      .filter((r) => r.dots.length > 0);
  }, [competitors, currency, only]);

  const productNames = useMemo(
    () =>
      Array.from(
        new Set(competitors.flatMap((c) => (c.channel_listings ?? []).flatMap((l) => (l.items ?? []).map((i) => i.matched_product))))
      ).filter((n): n is string => !!n),
    [competitors]
  );

  if (!rows.length && !only) return null;

  const all = rows.flatMap((r) => r.dots.map((d) => d.price)).concat(merchantPrice != null ? [merchantPrice] : []);
  const max = Math.max(...all) * 1.05;
  const W = 640;
  const LABEL = 120;
  const ROW = 34;
  const H = rows.length * ROW + 28;
  const x = (v: number) => LABEL + (v / max) * (W - LABEL - 16);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);

  return (
    <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Where rival prices sit</h3>
        <p className="text-[11px] text-[#8A8176]">
          Each dot is one product listed on a marketplace, in {currency || "listed currency"}; the tick is that rival&apos;s
          median.{merchantPrice != null ? " The dark line is your price." : ""}
        </p>
      </div>
      {productNames.length > 0 && (
        <label className="text-[11px] text-[#8A8176]">
          Compare against
          <select
            value={only}
            onChange={(e) => setOnly(e.target.value)}
            className="ml-1 rounded-lg border border-[#E1D7C8] bg-[#FAF6EF] px-2 py-1 text-xs text-[#1F1A17]"
          >
            <option value="">All rival products</option>
            {productNames.map((n) => (
              <option key={n} value={n}>
                Products like your {n}
              </option>
            ))}
          </select>
        </label>
      )}
      </div>
      {!rows.length && <p className="text-xs text-[#8A8176]">No rival products matched this one.</p>}
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Rival product prices by brand">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={4} y2={H - 22} stroke={GRID} strokeWidth={1} />
              <text x={x(t)} y={H - 6} textAnchor="middle" fontSize={10} fill={MUTED}>
                {money(t, currency)}
              </text>
            </g>
          ))}
          {rows.map((r, ri) => {
            const cy = ri * ROW + ROW / 2 + 4;
            return (
              <g key={r.name}>
                <text x={LABEL - 8} y={cy + 4} textAnchor="end" fontSize={11} fontWeight={600} fill={INK}>
                  {r.name.length > 16 ? r.name.slice(0, 15) + "…" : r.name}
                </text>
                {r.dots.map((d, di) => (
                  <g key={di} onPointerEnter={() => setHover(d)} onPointerLeave={() => setHover(null)}>
                    <circle cx={x(d.price)} cy={cy} r={12} fill="transparent" />
                    <circle
                      cx={x(d.price)}
                      cy={cy}
                      r={hover === d ? 5.5 : 4}
                      fill={ACCENT}
                      fillOpacity={0.55}
                      stroke="#fff"
                      strokeWidth={1.5}
                    />
                  </g>
                ))}
                {r.median != null && (
                  <line x1={x(r.median)} x2={x(r.median)} y1={cy - 9} y2={cy + 9} stroke={INK} strokeWidth={2} strokeLinecap="round" />
                )}
              </g>
            );
          })}
          {merchantPrice != null && (
            <g>
              <line x1={x(merchantPrice)} x2={x(merchantPrice)} y1={2} y2={H - 22} stroke={INK} strokeWidth={2} strokeDasharray="4 3" />
              <text x={x(merchantPrice) + 4} y={12} fontSize={10} fontWeight={700} fill={INK}>
                You {money(merchantPrice, currency)}
              </text>
            </g>
          )}
        </svg>
        {hover && (
          <div className="pointer-events-none absolute right-0 top-0 max-w-[60%] rounded-lg bg-white border border-[#E1D7C8] shadow-sm px-2 py-1 text-[11px]">
            <div className="font-bold text-[#1F1A17]">{money(hover.price, currency)}</div>
            <div className="text-[#4A4239] truncate">{hover.name}</div>
            <div className="text-[#8A8176]">
              {hover.rival} · {hover.site}
              {hover.variants && hover.variants > 1 ? ` · ${hover.variants} sizes/colours` : ""}
            </div>
            {hover.avg90 != null && <div className="text-[#8A8176]">90-day average {money(hover.avg90, currency)}</div>}
            {hover.rank != null && <div className="text-[#8A8176]">Amazon sales rank #{hover.rank.toLocaleString()}</div>}
          </div>
        )}
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-[#8A8176]">Show as table</summary>
        <table className="mt-2 w-full">
          <thead className="text-left text-[10px] uppercase text-[#8A8176]">
            <tr>
              <th className="py-1">Brand</th>
              <th className="py-1">Products</th>
              <th className="py-1">Cheapest</th>
              <th className="py-1">Median</th>
              <th className="py-1">Dearest</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const p = r.dots.map((d) => d.price);
              return (
                <tr key={r.name} className="border-t border-[#EFE7DB]">
                  <td className="py-0.5 font-semibold">{r.name}</td>
                  <td className="py-0.5">{p.length}</td>
                  <td className="py-0.5">{money(Math.min(...p), currency)}</td>
                  <td className="py-0.5">{r.median != null ? money(r.median, currency) : "—"}</td>
                  <td className="py-0.5">{money(Math.max(...p), currency)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </section>
  );
}
