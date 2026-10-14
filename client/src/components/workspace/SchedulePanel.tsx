import { useEffect, useState } from "react";
import { getCampaignContent } from "@/lib/api-client";
import { CHANNEL_LABEL, type ContentPack } from "@/types/content";

/**
 * What would publish, from the approved content. Publishing needs connected channel accounts;
 * until a channel is connected its assets stay here, unscheduled, rather than pretending to send.
 */
export function SchedulePanel({
  jobId,
  onBackToContent,
  refreshKey = 0,
}: {
  jobId: string;
  onBackToContent: () => void;
  /** Bumped when the chat reschedules or approves content, so the table reloads. */
  refreshKey?: number;
}) {
  const [pack, setPack] = useState<ContentPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCampaignContent(jobId).then(setPack).catch((e) => setError(e instanceof Error ? e.message : "Could not load"));
  }, [jobId, refreshKey]);

  const approved = pack?.assets.filter((a) => pack.approved_channels.includes(a.channel)) ?? [];
  if (error) return <p className="text-xs text-[#C7431F]">{error}</p>;
  if (!approved.length) {
    return (
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 space-y-3 text-sm text-[#4A4239]">
        <p>No approved content yet. Approve at least one channel in Content to schedule it.</p>
        <button onClick={onBackToContent} className="px-4 py-2 rounded-xl bg-[#1F1A17] text-white text-xs font-bold">
          Back to content
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <div className="bg-[#FFF8E6] border border-[#F0DDB0] rounded-2xl p-4 text-xs text-[#6B4E12]">
        Dates below are planned from the strategy's phases, at each channel's usual engagement time. No channel accounts
        are connected yet, so nothing will publish until you connect one.
      </div>
      <div className="bg-white rounded-2xl border border-[#E1D7C8] overflow-hidden">
        <table className="w-full text-xs">
          <thead className="text-left text-[10px] uppercase text-[#8A8176] bg-[#FAF6EF]">
            <tr>
              <th className="px-5 py-2">Channel</th>
              <th className="px-3 py-2">Content</th>
              <th className="px-3 py-2">Phase</th>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EFE7DB]">
            {approved.map((a) => (
              <tr key={a.asset_id}>
                <td className="px-5 py-2.5 font-semibold">{CHANNEL_LABEL[a.channel]}</td>
                <td className="px-3 py-2.5">{a.name}</td>
                <td className="px-3 py-2.5 text-[#6B625A]">{a.phase || "—"}</td>
                <td className="px-3 py-2.5 text-[#6B625A]">{a.scheduled_for ? `${new Date(a.scheduled_for).toLocaleString()} (planned)` : "Not planned"}</td>
                <td className="px-3 py-2.5 capitalize">{a.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Results appear only for assets that were actually published; nothing is simulated. */
export function LivePanel({ jobId, refreshKey = 0 }: { jobId: string; refreshKey?: number }) {
  const [pack, setPack] = useState<ContentPack | null>(null);
  useEffect(() => {
    getCampaignContent(jobId).then(setPack).catch(() => setPack(null));
  }, [jobId, refreshKey]);
  const published = pack?.assets.filter((a) => a.status === "published") ?? [];
  if (!published.length) {
    return (
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 text-sm text-[#4A4239]">
        Nothing has been published yet. Results from each channel appear here once its first asset goes live.
      </div>
    );
  }
  return (
    <ul className="bg-white rounded-2xl border border-[#E1D7C8] divide-y divide-[#EFE7DB]">
      {published.map((a) => (
        <li key={a.asset_id} className="px-5 py-3 text-xs flex justify-between">
          <span className="font-semibold">{CHANNEL_LABEL[a.channel]} · {a.name}</span>
          <span className="text-[#8A8176]">{a.external_id}</span>
        </li>
      ))}
    </ul>
  );
}
