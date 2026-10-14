import type { AudienceProfile } from "@/types/research";
import type { PersonaInput } from "@/types/strategy";
import { PointList, SourceTag } from "./Sourced";

/** ICP, personas, segments, pains, triggers and channels, all from the research. */
export function AudiencePanel({ audience, personas = [] }: { audience?: AudienceProfile | null; personas?: PersonaInput[] }) {
  const icp = audience?.icp;
  const hasAny =
    !!icp ||
    personas.length > 0 ||
    !!audience?.segments.length ||
    !!audience?.pains.length ||
    !!audience?.channels.length;
  if (!hasAny) {
    return (
      <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 text-xs text-[#8A8176]">
        The research did not surface enough about buyers to profile an audience. Add customer details or documents to your
        brief and re-run, or ask the agent.
      </section>
    );
  }
  return (
    <div className="space-y-6">
      {icp && (
        <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wide text-[#8A8176]">Primary ICP</div>
            <h2 className="font-['Bricolage_Grotesque'] text-2xl font-bold mt-1">{icp.name}</h2>
            {icp.description && <p className="text-sm text-[#4A4239] mt-1 leading-relaxed">{icp.description}</p>}
          </div>
          {Object.keys(icp.attributes).length > 0 && (
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(icp.attributes).map(([k, v]) => (
                <div key={k} className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB]">
                  <dt className="text-[10px] uppercase font-bold text-[#8A8176]">{k.replace(/_/g, " ")}</dt>
                  <dd className="text-xs font-semibold text-[#1F1A17] mt-0.5">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <PointList title="Why this ICP" points={icp.why} />
            {icp.fit_signals.length > 0 && (
              <PointList title="✓ Fit signals" points={icp.fit_signals.map((text) => ({ text }))} marker="✓" />
            )}
            {icp.low_fit_signals.length > 0 && (
              <PointList title="✕ Low-fit signals" points={icp.low_fit_signals.map((text) => ({ text }))} marker="✕" />
            )}
          </div>
        </section>
      )}

      {personas.length > 0 && (
        <section className="space-y-3">
          <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Key personas</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {personas.slice(0, 3).map((p) => (
              <div key={p.persona_id} className="bg-white rounded-2xl border border-[#E1D7C8] p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-sm text-[#1F1A17]">{p.name}</span>
                  {p.role && (
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-[#F1EADF] text-[#6B625A]">{p.role}</span>
                  )}
                </div>
                {p.description && <p className="text-xs text-[#4A4239] leading-relaxed">{p.description}</p>}
                {(p.motivations ?? []).length > 0 && (
                  <PointList title="Key motivators" points={(p.motivations ?? []).slice(0, 3).map((text) => ({ text }))} />
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {audience && audience.segments.length > 0 && (
        <section className="bg-white rounded-2xl border border-[#E1D7C8] overflow-hidden">
          <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold px-6 pt-5 pb-3">Audience segments</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-[10px] uppercase text-[#8A8176] bg-[#FAF6EF]">
                <tr>
                  <th className="px-6 py-2">Segment</th>
                  <th className="px-3 py-2">Size</th>
                  <th className="px-3 py-2">What defines them</th>
                  <th className="px-3 py-2">Likely trigger</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EFE7DB]">
                {audience.segments.map((g, i) => (
                  <tr key={i}>
                    <td className="px-6 py-2.5 font-semibold text-[#1F1A17]">{g.name}</td>
                    <td className="px-3 py-2.5 text-[#8A8176]" title={g.size_note ? undefined : "No source states a size"}>
                      {g.size_note || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[#4A4239]">{g.definition}</td>
                    <td className="px-3 py-2.5 text-[#4A4239]">{g.trigger}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {audience && (
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-white rounded-2xl border border-[#E1D7C8] p-6">
          <PointList title="Pain points" points={audience.pains} />
          <PointList title="Motivations" points={audience.motivations} />
          <PointList title="Behaviors" points={audience.behaviors} />
          <PointList
            title="Triggers and barriers"
            points={[
              ...audience.triggers.map((p) => ({ ...p, text: `Trigger: ${p.text}` })),
              ...audience.barriers.map((p) => ({ ...p, text: `Barrier: ${p.text}` })),
            ]}
          />
        </section>
      )}

      {audience && audience.channels.length > 0 && (
        <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 space-y-3">
          <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Where to reach them</h3>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {audience.channels.map((c, i) => (
              <li key={i} className="p-3 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-[#1F1A17]">{c.text}</span>
                  <SourceTag point={c} />
                </div>
                {c.reason && <p className="text-[#4A4239] mt-1 leading-relaxed">{c.reason}</p>}
              </li>
            ))}
          </ul>
          {audience.preferred_message && (
            <p className="text-xs text-[#4A4239]">
              <span className="font-bold">Preferred message:</span> {audience.preferred_message}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
