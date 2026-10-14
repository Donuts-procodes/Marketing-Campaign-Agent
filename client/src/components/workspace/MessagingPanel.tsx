import type { MessagingStrategy } from "@/types/strategy";

/** Positioning, the core line every asset carries, and the three pillars with their proof. */
export function MessagingPanel({ messaging }: { messaging?: MessagingStrategy | null }) {
  if (!messaging || !messaging.core_message) return null;
  return (
    <section className="bg-white rounded-2xl border border-[#E1D7C8] p-6 shadow-xs space-y-4">
      <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">Positioning & message</h3>
      {messaging.positioning && <p className="text-sm text-[#4A4239] leading-relaxed">{messaging.positioning}</p>}
      <p className="text-base font-bold text-[#1F1A17]">&ldquo;{messaging.core_message}&rdquo;</p>
      {messaging.pillars.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {messaging.pillars.map((p, i) => (
            <div key={i} className="p-4 rounded-xl bg-[#FAF6EF] border border-[#EFE7DB] space-y-1">
              <div className="font-bold text-sm text-[#1F1A17]">{p.title}</div>
              {p.message && <p className="text-xs text-[#4A4239] leading-relaxed">{p.message}</p>}
              {p.proof && (
                <p className={`text-[11px] ${p.needs_proof ? "text-[#B07A12]" : "text-[#8A8176]"}`}>
                  {p.needs_proof ? "Needs proof from you: " : "Proof: "}
                  {p.proof}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
