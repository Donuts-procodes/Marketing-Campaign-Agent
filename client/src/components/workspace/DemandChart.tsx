import { useMemo, useRef, useState } from "react";
import type { MarketDemand } from "@/types/research";

const ACCENT = "#C7431F"; // the one data series
const INK = "#1F1A17";
const MUTED = "#8A8176";
const GRID = "#EFE7DB";

const W = 640;
const H = 200;
const PAD = { top: 12, right: 12, bottom: 24, left: 32 };

const DIRECTION = {
  rising: { icon: "↑", label: "Rising", cls: "text-[#256545] bg-[#E4F2EA]" },
  falling: { icon: "↓", label: "Cooling", cls: "text-[#8F2F14] bg-[#FDF1EB]" },
  flat: { icon: "→", label: "Steady", cls: "text-[#4A4239] bg-[#F1EADF]" },
} as const;

function monthLabel(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short" });
}

/** Market mood: 12-month search interest, its direction, seasonality and rising searches. */
export function DemandChart({ demand }: { demand?: MarketDemand | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const pts = demand?.series ?? [];

  const geom = useMemo(() => {
    const iw = W - PAD.left - PAD.right;
    const ih = H - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (pts.length > 1 ? (i / (pts.length - 1)) * iw : 0);
    const y = (v: number) => PAD.top + ih - (v / 100) * ih;
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
    // One tick per month change, so the axis reads as months.
    const ticks = pts
      .map((p, i) => ({ i, m: p.date.slice(0, 7) }))
      .filter((t, k, arr) => k === 0 || t.m !== arr[k - 1].m)
      .filter((_, k) => k % 2 === 0);
    return { x, y, path, ticks };
  }, [pts]);

  if (!demand) return null;
  const dir = DIRECTION[demand.direction];

  return (
    <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Market mood & demand</h3>
          <p className="text-[11px] text-[#8A8176]">
            Search interest for &ldquo;{demand.keyword}&rdquo; · {demand.geo} · {demand.source}
          </p>
        </div>
        {demand.available && (
          <div className={`px-3 py-2 rounded-xl ${dir.cls}`}>
            <div className="text-xs font-bold">
              {dir.icon} {dir.label}
            </div>
            {demand.change_pct != null && (
              <div className="text-lg font-extrabold leading-tight">
                {demand.change_pct > 0 ? "+" : ""}
                {demand.change_pct}%
              </div>
            )}
            <div className="text-[10px] opacity-80">vs previous quarter</div>
          </div>
        )}
      </div>

      {!demand.available ? (
        <p className="text-xs text-[#4A4239]">
          Search-interest data was unavailable for this run ({demand.unavailable_reason}). Re-run research later to read
          the trend.
        </p>
      ) : (
        <>
          {demand.mood && <p className="text-sm text-[#1F1A17] leading-relaxed">{demand.mood}</p>}
          <div className="relative">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${W} ${H}`}
              className="w-full h-auto"
              role="img"
              aria-label={`Weekly search interest for ${demand.keyword}, last 12 months`}
              onPointerMove={(e) => {
                const r = svgRef.current?.getBoundingClientRect();
                if (!r || pts.length < 2) return;
                const px = ((e.clientX - r.left) / r.width) * W;
                const i = Math.round(((px - PAD.left) / (W - PAD.left - PAD.right)) * (pts.length - 1));
                setHover(Math.max(0, Math.min(pts.length - 1, i)));
              }}
              onPointerLeave={() => setHover(null)}
            >
              {[0, 50, 100].map((v) => (
                <g key={v}>
                  <line x1={PAD.left} x2={W - PAD.right} y1={geom.y(v)} y2={geom.y(v)} stroke={GRID} strokeWidth={1} />
                  <text x={PAD.left - 6} y={geom.y(v) + 3} textAnchor="end" fontSize={10} fill={MUTED}>
                    {v}
                  </text>
                </g>
              ))}
              {geom.ticks.map((t) => (
                <text key={t.i} x={geom.x(t.i)} y={H - 6} textAnchor="middle" fontSize={10} fill={MUTED}>
                  {monthLabel(pts[t.i].date)}
                </text>
              ))}
              <path d={geom.path} fill="none" stroke={ACCENT} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {hover != null && (
                <g>
                  <line x1={geom.x(hover)} x2={geom.x(hover)} y1={PAD.top} y2={H - PAD.bottom} stroke={MUTED} strokeWidth={1} />
                  <circle cx={geom.x(hover)} cy={geom.y(pts[hover].value)} r={4.5} fill={ACCENT} stroke="#fff" strokeWidth={2} />
                </g>
              )}
            </svg>
            {hover != null && (
              <div
                className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-lg bg-white border border-[#E1D7C8] shadow-sm px-2 py-1 text-[11px]"
                style={{ left: `${(geom.x(hover) / W) * 100}%` }}
              >
                <span className="font-bold" style={{ color: INK }}>{pts[hover].value}</span>{" "}
                <span className="text-[#8A8176]">week of {new Date(pts[hover].date + "T00:00:00").toLocaleDateString()}</span>
              </div>
            )}
          </div>
          <p className="text-[10px] text-[#8A8176]">100 = the busiest week of the year. Values are relative, not search counts.</p>
          {demand.monthly_volume != null && (
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                <div className="text-[10px] uppercase font-bold text-[#8A8176]">Monthly searches</div>
                <div className="text-lg font-extrabold text-[#1F1A17]">{demand.monthly_volume.toLocaleString()}</div>
              </div>
              <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                <div className="text-[10px] uppercase font-bold text-[#8A8176]">Ad competition</div>
                <div className="text-lg font-extrabold text-[#1F1A17] capitalize">{(demand.competition ?? "—").toLowerCase()}</div>
              </div>
              <div className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                <div className="text-[10px] uppercase font-bold text-[#8A8176]">Avg cost per click</div>
                <div className="text-lg font-extrabold text-[#1F1A17]">{demand.cpc != null ? demand.cpc.toFixed(2) : "—"}</div>
              </div>
            </div>
          )}
          {(demand.keyword_volumes ?? []).length > 1 && (
            <table className="w-full text-xs">
              <thead className="text-left text-[10px] uppercase text-[#8A8176]">
                <tr>
                  <th className="py-1">Search</th>
                  <th className="py-1">Monthly searches</th>
                  <th className="py-1">CPC</th>
                </tr>
              </thead>
              <tbody>
                {(demand.keyword_volumes ?? []).map((k) => (
                  <tr key={k.keyword} className="border-t border-[#EFE7DB]">
                    <td className="py-0.5">{k.keyword}</td>
                    <td className="py-0.5">{k.volume != null ? k.volume.toLocaleString() : "—"}</td>
                    <td className="py-0.5">{k.cpc != null ? k.cpc.toFixed(2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div>
              <div className="text-[11px] font-bold uppercase text-[#8A8176]">Seasonality</div>
              <p className="text-[#4A4239] mt-1">
                Peaks: {demand.peak_months.join(", ") || "—"}
                {demand.low_months.length > 0 && <> · Quietest: {demand.low_months.join(", ")}</>}
              </p>
            </div>
            <div className="md:col-span-2">
              <div className="text-[11px] font-bold uppercase text-[#8A8176]">Trending searches</div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {demand.rising_searches.length ? (
                  demand.rising_searches.map((s) => (
                    <span key={s.query} className="px-2 py-0.5 rounded-full bg-[#FAF6EF] border border-[#EFE7DB] text-[#1F1A17]">
                      {s.query} <span className="font-bold text-[#256545]">{s.growth}</span>
                    </span>
                  ))
                ) : (
                  <span className="text-[#8A8176]">No breakout searches this period.</span>
                )}
              </div>
            </div>
          </div>
          {demand.purchase_signals.length > 0 && (
            <div className="text-xs">
              <div className="text-[11px] font-bold uppercase text-[#8A8176]">Buying signals on marketplaces</div>
              <ul className="mt-1 text-[#4A4239] space-y-0.5">
                {demand.purchase_signals.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          <details className="text-xs">
            <summary className="cursor-pointer text-[#8A8176]">Show as table</summary>
            <table className="mt-2 w-full">
              <thead className="text-left text-[10px] uppercase text-[#8A8176]">
                <tr>
                  <th className="py-1">Week of</th>
                  <th className="py-1">Interest</th>
                </tr>
              </thead>
              <tbody>
                {pts.map((p) => (
                  <tr key={p.date} className="border-t border-[#EFE7DB]">
                    <td className="py-0.5">{p.date}</td>
                    <td className="py-0.5">{p.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}
