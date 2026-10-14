import type { CampaignStrategyBrief, PersonaInput } from "@/types/strategy";

const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED ", SGD: "S$", AUD: "A$", CAD: "C$", JPY: "¥" };

function money(amount: number | null | undefined, currency?: string): string {
  if (amount == null) return "—";
  const code = (currency || "USD").toUpperCase();
  return `${SYMBOLS[code] ?? code + " "}${Math.round(amount).toLocaleString()}`;
}

const MODE_COPY: Record<string, { label: string; tone: string }> = {
  validate: { label: "Validate", tone: "bg-[#FDF1EB] text-[#C7431F]" },
  traction: { label: "Traction", tone: "bg-[#FFF6DB] text-[#8A6100]" },
  scale: { label: "Scale", tone: "bg-[#E8F3EC] text-[#256545]" },
};

const SOURCE_COPY: Record<PersonaInput["source"], string> = {
  persona_agent: "Persona agent",
  merchant_input: "Your audience",
  research_derived: "Provisional · from research",
};

function Section({ title, children, hint }: { title: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 shadow-xs space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wider text-[#C7431F]">{title}</span>
        {hint && <span className="text-[10px] text-[#8A8176]">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Chips({ items, tone = "bg-[#FAF6EF] text-[#4A4239]" }: { items?: string[]; tone?: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i, idx) => (
        <span key={idx} className={`text-[10px] px-2 py-0.5 rounded-full border border-[#EFE7DB] ${tone}`}>
          {i}
        </span>
      ))}
    </div>
  );
}

/**
 * The grounded plan: mode, personas, readiness, message tests, phases with gates, channels with
 * evidence, marketplace findings, economics and open questions. Renders nothing for briefs saved
 * before the planner existed.
 */
export function StrategyPlanPanel({ brief }: { brief: CampaignStrategyBrief | null | undefined }) {
  const plan = brief?.plan;
  if (!brief || !plan) return null;
  const ccy = brief.currency;
  const personas = brief.personas_used ?? [];
  const personaName = (id: string) => personas.find((p) => p.persona_id === id)?.name ?? id;
  const mode = MODE_COPY[brief.mode ?? ""] ?? MODE_COPY.validate;
  const econ = brief.economics;
  const spend = plan.channels.reduce((s, c) => s + c.budget, 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[11px] font-bold px-2.5 py-1 rounded-full ${mode.tone}`}>{mode.label} plan</span>
          <span className="text-[11px] text-[#8A8176]">
            {plan.generated_by === "llm" ? "Planned by AI from your research, checked by rules" : "Rule-based plan from your research"}
          </span>
          <span className="ml-auto text-[11px] font-semibold text-[#1F1A17]">
            {money(spend, ccy)} planned · {money(plan.reserve, ccy)} reserve · {money(brief.user_budget, ccy)} budget
          </span>
        </div>
        <p className="text-sm text-[#1F1A17] leading-relaxed">{plan.rationale}</p>
        {plan.validation_notes.length > 0 && (
          <details className="text-[11px] text-[#6B625A]">
            <summary className="cursor-pointer">Checks applied ({plan.validation_notes.length})</summary>
            <ul className="list-disc pl-5 mt-1 space-y-0.5">
              {plan.validation_notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </details>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Personas */}
        <Section title="Who we target" hint="ranked by fit for this campaign">
          <div className="space-y-3">
            {personas.slice(0, 4).map((p) => (
              <div key={p.persona_id} className={`rounded-xl border p-3 space-y-1.5 ${p.role === "primary" ? "border-[#C7431F]/50 bg-[#FFFBF8]" : "border-[#EFE7DB]"}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[10px] font-bold uppercase text-[#C7431F]">{p.role ?? "later"}</span>
                  <span className="text-sm font-semibold text-[#1F1A17]">{p.name}</span>
                  <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${p.source === "research_derived" ? "bg-[#FFF6DB] text-[#8A6100]" : "bg-[#E8F3EC] text-[#256545]"}`}>
                    {SOURCE_COPY[p.source]}
                  </span>
                </div>
                {p.objections && p.objections.length > 0 && (
                  <div className="text-[11px] text-[#4A4239]"><strong>Objections:</strong> {p.objections.slice(0, 3).join(" · ")}</div>
                )}
                <Chips items={p.preferred_channels?.slice(0, 4)} />
              </div>
            ))}
            {personas.some((p) => p.source === "research_derived") && (
              <p className="text-[10px] text-[#8A8176]">Provisional personas are replaced automatically when the persona agent's output is available.</p>
            )}
          </div>
        </Section>

        {/* Readiness */}
        <Section title="Fix before spending" hint="from persona objections and rival complaints">
          {plan.readiness.length === 0 ? (
            <p className="text-[11px] text-[#6B625A]">No blocking gaps found in the research.</p>
          ) : (
            <ul className="space-y-2">
              {plan.readiness.map((r, i) => (
                <li key={i} className="flex gap-2 text-[12px]">
                  <span className={`mt-0.5 h-4 w-4 shrink-0 rounded border ${r.blocking ? "border-[#C7431F]" : "border-[#D3C6B3]"}`} />
                  <div>
                    <div className="font-semibold text-[#1F1A17]">
                      {r.item} {r.blocking && <span className="text-[10px] font-bold text-[#C7431F]">· blocks ads</span>}
                    </div>
                    <div className="text-[11px] text-[#6B625A]">{r.reason}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {/* Message tests */}
      {plan.message_tests.length > 0 && (
        <Section title="Message tests" hint="same audience, budget and landing page; keep the winner">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {plan.message_tests.map((t) => (
              <div key={t.test_id} className="rounded-xl border border-[#EFE7DB] p-3 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${t.role === "champion" ? "bg-[#FDF1EB] text-[#C7431F]" : "bg-[#FAF6EF] text-[#4A4239]"}`}>{t.role}</span>
                  <span className="text-[11px] text-[#8A8176]">for {personaName(t.persona_id)}</span>
                </div>
                <div className="font-['Bricolage_Grotesque'] text-base font-bold text-[#1F1A17]">“{t.hook}”</div>
                <div className="text-[11px] text-[#4A4239]"><strong>Angle:</strong> {t.angle} · <strong>CTA:</strong> {t.cta}</div>
                {t.proof_needed && <div className="text-[11px] text-[#6B625A]"><strong>Proof needed:</strong> {t.proof_needed}</div>}
                <Chips items={t.evidence} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Phases */}
      <Section title="Phases & decision gates" hint="ceilings, not targets">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {plan.phases.map((ph, i) => (
            <div key={i} className="rounded-xl border border-[#EFE7DB] p-3 space-y-2">
              <div className="text-[10px] font-bold uppercase text-[#8A8176]">{ph.days} · up to {money(ph.budget_ceiling, ccy)}</div>
              <div className="text-sm font-semibold text-[#1F1A17]">{ph.name}</div>
              <p className="text-[11px] text-[#4A4239]">{ph.objective}</p>
              <ul className="list-disc pl-4 text-[11px] text-[#4A4239] space-y-0.5">
                {ph.actions.map((a, j) => <li key={j}>{a}</li>)}
              </ul>
              <div className="text-[11px] rounded-lg bg-[#FAF6EF] p-2 text-[#1F1A17]"><strong>Gate:</strong> {ph.decision_gate}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* Channels */}
      <Section title="Channels & why" hint="each tied to a persona and evidence">
        <div className="space-y-2">
          {plan.channels.map((c, i) => (
            <div key={i} className="rounded-xl border border-[#EFE7DB] p-3 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-[#1F1A17]">{c.channel}</span>
                <span className="text-[10px] text-[#8A8176]">for {personaName(c.persona_id)}</span>
                <span className="ml-auto text-[12px] font-bold text-[#1F1A17]">{c.budget ? money(c.budget, ccy) : "Organic"}</span>
              </div>
              <p className="text-[11px] text-[#4A4239]">{c.purpose}</p>
              <Chips items={c.evidence} tone="bg-[#F4F8F5] text-[#256545]" />
            </div>
          ))}
        </div>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Marketplace findings */}
        {brief.market_listings && brief.market_listings.length > 0 && (
          <Section title="What rivals' listings show" hint="own sites & marketplaces">
            <ul className="list-disc pl-4 text-[12px] text-[#4A4239] space-y-1">
              {brief.market_listings.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </Section>
        )}

        {/* Economics */}
        <Section title="Unit economics">
          {econ?.orders_to_break_even ? (
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-[#FAF6EF] p-2"><div className="text-[10px] text-[#8A8176] uppercase">Contribution / unit</div><div className="font-bold">{money(econ.contribution_per_unit, ccy)}</div></div>
              <div className="rounded-xl bg-[#FAF6EF] p-2"><div className="text-[10px] text-[#8A8176] uppercase">Orders to break even</div><div className="font-bold">{econ.orders_to_break_even}</div></div>
              <div className="rounded-xl bg-[#FAF6EF] p-2"><div className="text-[10px] text-[#8A8176] uppercase">Max cost / order</div><div className="font-bold">{money(econ.max_affordable_cac, ccy)}</div></div>
            </div>
          ) : null}
          <p className="text-[11px] text-[#6B625A]">{econ?.note}</p>
        </Section>
      </div>

      {/* Questions */}
      {brief.unknowns && brief.unknowns.length > 0 && (
        <Section title="Answer these to sharpen the plan">
          <ul className="list-disc pl-4 text-[12px] text-[#4A4239] space-y-1">
            {brief.unknowns.map((u, i) => <li key={i}>{u}</li>)}
          </ul>
        </Section>
      )}
    </div>
  );
}
