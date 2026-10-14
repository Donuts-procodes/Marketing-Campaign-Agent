import type { ChannelListing, CompetitorProfile } from "@/types/research";
import { safeHref } from "@/lib/utils";

function money(value: number, currency?: string | null): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD", maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency ?? ""} ${value.toLocaleString()}`.trim();
  }
}

const SOURCE_NOTE: Record<string, string> = {
  page: "",
  search_snippet: " · from search excerpt",
  ai_search: " · AI-cited",
  shopping_api: " · Google Shopping",
};

/** Each rival's lowest listed price per store, with the merchant's own price for reference. */
export function PriceMatrix({
  competitors,
  merchantName,
  merchantPrice,
  currency,
}: {
  competitors: CompetitorProfile[];
  merchantName?: string;
  merchantPrice?: number | null;
  currency?: string | null;
}) {
  const rows = competitors
    .map((c) => ({ name: c.brand_name, listings: (c.channel_listings ?? []).filter((l) => l.selling_price != null) }))
    .filter((r) => r.listings.length > 0);
  if (!rows.length) return null;
  const sites = Array.from(new Set(rows.flatMap((r) => r.listings.map((l) => l.site))));
  const cheapest = (ls: ChannelListing[], site: string) =>
    ls.filter((l) => l.site === site).sort((a, b) => (a.selling_price ?? 0) - (b.selling_price ?? 0))[0];

  return (
    <section className="bg-white rounded-2xl border border-[#E1D7C8] overflow-hidden">
      <div className="px-6 pt-5 pb-3">
        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Prices by marketplace</h3>
        <p className="text-[11px] text-[#8A8176]">Lowest listed price per store, read from each listing. Select a price to open it.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left text-[10px] uppercase text-[#8A8176] bg-[#FAF6EF]">
            <tr>
              <th className="px-6 py-2">Brand</th>
              {sites.map((s) => (
                <th key={s} className="px-3 py-2 whitespace-nowrap">{s}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EFE7DB]">
            {merchantPrice != null && (
              <tr className="bg-[#FDF9F3]">
                <td className="px-6 py-2.5 font-bold">{merchantName || "You"} (you)</td>
                <td colSpan={sites.length} className="px-3 py-2.5 font-bold">{money(merchantPrice, currency)}</td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.name}>
                <td className="px-6 py-2.5 font-semibold text-[#1F1A17]">{r.name}</td>
                {sites.map((s) => {
                  const l = cheapest(r.listings, s);
                  if (!l) return <td key={s} className="px-3 py-2.5 text-[#B5AA9C]" title="Not found on this store">—</td>;
                  return (
                    <td key={s} className="px-3 py-2.5 whitespace-nowrap">
                      <a
                        href={safeHref(l.url)}
                        target="_blank"
                        rel="noreferrer"
                        title={`${l.product ?? ""}${SOURCE_NOTE[l.source ?? "page"] ?? ""}`}
                        className="hover:underline"
                      >
                        <span className="font-bold text-[#1F1A17]">
                          {l.price_in_merchant_currency != null ? money(l.price_in_merchant_currency, l.merchant_currency) : money(l.selling_price!, l.currency)}
                        </span>
                        {l.price_in_merchant_currency != null && (
                          <span className="ml-1 text-[10px] text-[#8A8176]">({money(l.selling_price!, l.currency)})</span>
                        )}
                        {l.page_kind === "grid" && l.product_count ? (
                          <span className="ml-1 text-[10px] text-[#8A8176]">median of {l.product_count}</span>
                        ) : null}
                        {l.mrp != null && <span className="ml-1 text-[#8A8176] line-through">{money(l.mrp, l.currency)}</span>}
                        {l.source && l.source !== "page" && l.source !== "shopping_api" && <span className="ml-1 text-[10px] text-[#B07A12]">*</span>}
                      </a>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-6 py-2 text-[10px] text-[#8A8176]">* read from a search excerpt or cited by AI web search, not from the page itself.</p>
    </section>
  );
}
