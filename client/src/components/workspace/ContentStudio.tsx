import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Loader2, RefreshCw } from "lucide-react";
import {
  editCampaignAsset,
  generateCampaignContent,
  getCampaignContent,
  regenerateCampaignAsset,
  setChannelApproval,
} from "@/lib/api-client";
import { CHANNEL_LABEL, type ChannelKey, type ContentAsset, type ContentPack } from "@/types/content";

interface Props {
  jobId: string;
  strategyApproved: boolean;
  /** Bumped by the parent when a CONTENT_READY event arrives on the stream. */
  refreshKey?: number;
  onContinue?: () => void;
  onFocusAsset?: (assetId: string | null) => void;
}

const field = "w-full rounded-xl border border-[#E1D7C8] bg-[#FAF6EF] px-3 py-2 text-xs text-[#1F1A17] focus:outline-none focus:border-[#1F1A17]";

/** Assets written from the approved strategy: edit, rewrite and approve per channel. */
export function ContentStudio({ jobId, strategyApproved, refreshKey = 0, onContinue, onFocusAsset }: Props) {
  const [pack, setPack] = useState<ContentPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [channel, setChannel] = useState<ChannelKey | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");

  const load = useCallback(async () => {
    try {
      const p = await getCampaignContent(jobId);
      setPack(p);
      if (p) setWriting(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load content");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  // While the pack is being written in the background, poll until it lands.
  useEffect(() => {
    if (!strategyApproved || pack || !writing) return;
    const t = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(t);
  }, [strategyApproved, pack, writing, load]);

  useEffect(() => {
    if (strategyApproved && !pack && !loading) setWriting(true);
  }, [strategyApproved, pack, loading]);

  const channels = useMemo(
    () => (pack ? (Array.from(new Set(pack.assets.map((a) => a.channel))) as ChannelKey[]) : []),
    [pack]
  );
  const active = channel && channels.includes(channel) ? channel : channels[0] ?? null;
  const assets = pack?.assets.filter((a) => a.channel === active) ?? [];
  const asset = assets.find((a) => a.asset_id === selected) ?? assets[0] ?? null;

  useEffect(() => {
    onFocusAsset?.(asset?.asset_id ?? null);
  }, [asset?.asset_id, onFocusAsset]);

  const replace = (a: ContentAsset) =>
    setPack((p) => (p ? { ...p, assets: p.assets.map((x) => (x.asset_id === a.asset_id ? a : x)),
      approved_channels: a.status === "draft" ? p.approved_channels.filter((c) => c !== a.channel) : p.approved_channels } : p));

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  };

  if (!strategyApproved) {
    return (
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 text-sm text-[#4A4239]">
        Approve the strategy first. Content is written from the approved strategy so every asset carries its positioning
        and messages.
      </div>
    );
  }
  if (loading || (writing && !pack)) {
    return (
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 flex items-center gap-3 text-sm text-[#4A4239]">
        <Loader2 className="w-4 h-4 animate-spin" /> Writing your content from the approved strategy. Finished channels
        appear here.
      </div>
    );
  }
  if (!pack || pack.assets.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-[#E1D7C8] p-6 space-y-3 text-sm text-[#4A4239]">
        <p>No content yet.{pack?.notes.length ? ` ${pack.notes.join(" ")}` : ""}</p>
        <button
          onClick={() => run("gen", async () => { await generateCampaignContent(jobId); setPack(null); setWriting(true); })}
          className="px-4 py-2 rounded-xl bg-[#1F1A17] text-white text-xs font-bold"
        >
          Write content
        </button>
        {error && <p className="text-xs text-[#C7431F]">{error}</p>}
      </div>
    );
  }

  const approvedCount = pack.approved_channels.length;
  const isApproved = active ? pack.approved_channels.includes(active) : false;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-xs text-[#8A8176]">
          {pack.assets.length} assets across {channels.length} channels · written from the approved strategy
        </p>
        <div className="flex flex-wrap gap-1.5 bg-[#F1EADF] p-1 rounded-xl" role="tablist">
          {channels.map((c) => (
            <button
              key={c}
              role="tab"
              aria-selected={c === active}
              onClick={() => { setChannel(c); setSelected(null); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold ${c === active ? "bg-white text-[#1F1A17] shadow-xs" : "text-[#6B625A]"}`}
            >
              {CHANNEL_LABEL[c]} {pack.approved_channels.includes(c) && <Check className="inline w-3 h-3 text-[#3F9068]" />}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[220px_minmax(0,1fr)] gap-4">
        <ul className="space-y-1.5">
          {assets.map((a) => (
            <li key={a.asset_id}>
              <button
                onClick={() => setSelected(a.asset_id)}
                className={`w-full text-left p-3 rounded-xl border text-xs ${a.asset_id === asset?.asset_id ? "bg-white border-[#1F1A17]" : "bg-[#FAF6EF] border-[#EFE7DB]"}`}
              >
                <div className="font-bold text-[#1F1A17]">{a.name}</div>
                <div className="text-[#8A8176] mt-0.5">{a.phase || a.kind.replace("_", " ")} · {a.status}</div>
              </button>
            </li>
          ))}
        </ul>

        {asset && (
          <AssetEditor
            key={`${asset.asset_id}-${asset.revision}`}
            asset={asset}
            busy={busy}
            onSave={(fields) => run(`save-${asset.asset_id}`, async () => replace(await editCampaignAsset(jobId, asset.asset_id, fields)))}
            onRewrite={() => run(`rw-${asset.asset_id}`, async () => {
              replace(await regenerateCampaignAsset(jobId, asset.asset_id, instruction));
              setInstruction("");
            })}
            instruction={instruction}
            setInstruction={setInstruction}
          />
        )}
      </div>

      {error && <p className="text-xs text-[#C7431F]">{error}</p>}

      <div className="sticky bottom-4 bg-[#1F1A17] text-white p-4 rounded-2xl shadow-xl flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs">
          {approvedCount} of {channels.length} channels approved. Approved channels can be scheduled; the rest stay in review.
        </span>
        <div className="flex gap-2">
          {active && (
            <button
              disabled={busy !== null}
              onClick={() => run("approve", async () => setPack(await setChannelApproval(jobId, active, !isApproved)))}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-bold disabled:opacity-50"
            >
              {isApproved ? `Reopen ${CHANNEL_LABEL[active]}` : `Approve ${CHANNEL_LABEL[active]}`}
            </button>
          )}
          {onContinue && approvedCount > 0 && (
            <button onClick={onContinue} className="px-4 py-2 rounded-xl bg-[#C7431F] hover:bg-[#A9381A] text-xs font-bold">
              Continue to schedule →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

type Editable = Partial<Pick<ContentAsset, "subject" | "preview_text" | "body" | "headlines" | "descriptions" | "cta" | "creative_brief">>;

function AssetEditor({ asset, busy, onSave, onRewrite, instruction, setInstruction }: {
  asset: ContentAsset;
  busy: string | null;
  onSave: (f: Editable) => void;
  onRewrite: () => void;
  instruction: string;
  setInstruction: (s: string) => void;
}) {
  const [draft, setDraft] = useState<Editable>({
    subject: asset.subject ?? "",
    preview_text: asset.preview_text ?? "",
    body: asset.body,
    headlines: asset.headlines,
    descriptions: asset.descriptions,
    cta: asset.cta ?? "",
    creative_brief: asset.creative_brief ?? "",
  });
  const locked = asset.status === "scheduled" || asset.status === "published";
  const set = (k: keyof Editable, v: string | string[]) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="bg-white rounded-2xl border border-[#E1D7C8] p-5 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-['Bricolage_Grotesque'] text-lg font-bold">{asset.name}</h3>
        <span className="text-[10px] uppercase font-bold text-[#8A8176]">rev {asset.revision}</span>
      </div>
      {asset.kind === "email" && (
        <>
          <label className="block text-[11px] font-bold text-[#8A8176]">Subject
            <input className={field} value={draft.subject ?? ""} onChange={(e) => set("subject", e.target.value)} disabled={locked} />
          </label>
          <label className="block text-[11px] font-bold text-[#8A8176]">Preview text
            <input className={field} value={draft.preview_text ?? ""} onChange={(e) => set("preview_text", e.target.value)} disabled={locked} />
          </label>
        </>
      )}
      {asset.kind === "search_ad" ? (
        <>
          <label className="block text-[11px] font-bold text-[#8A8176]">Headlines (one per line, ≤ 30 characters)
            <textarea rows={6} className={field} value={(draft.headlines ?? []).join("\n")} onChange={(e) => set("headlines", e.target.value.split("\n"))} disabled={locked} />
          </label>
          <label className="block text-[11px] font-bold text-[#8A8176]">Descriptions (one per line, ≤ 90 characters)
            <textarea rows={3} className={field} value={(draft.descriptions ?? []).join("\n")} onChange={(e) => set("descriptions", e.target.value.split("\n"))} disabled={locked} />
          </label>
        </>
      ) : (
        <label className="block text-[11px] font-bold text-[#8A8176]">{asset.kind === "email" ? "Body" : "Copy"}
          <textarea rows={8} className={field} value={draft.body ?? ""} onChange={(e) => set("body", e.target.value)} disabled={locked} />
        </label>
      )}
      {asset.kind === "ad" && (
        <label className="block text-[11px] font-bold text-[#8A8176]">Headline
          <input className={field} value={(draft.headlines ?? [])[0] ?? ""} onChange={(e) => set("headlines", [e.target.value])} disabled={locked} />
        </label>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block text-[11px] font-bold text-[#8A8176]">Call to action
          <input className={field} value={draft.cta ?? ""} onChange={(e) => set("cta", e.target.value)} disabled={locked} />
        </label>
        {asset.kind !== "email" && asset.kind !== "search_ad" && (
          <label className="block text-[11px] font-bold text-[#8A8176]">Creative brief
            <input className={field} value={draft.creative_brief ?? ""} onChange={(e) => set("creative_brief", e.target.value)} disabled={locked} />
          </label>
        )}
      </div>
      {asset.hashtags.length > 0 && <p className="text-xs text-[#6B625A]">{asset.hashtags.join(" ")}</p>}
      {asset.qa_issues.length > 0 && (
        <ul className="rounded-xl bg-[#FFF8E6] border border-[#F0DDB0] p-3 space-y-1 text-[11px] text-[#6B4E12]" aria-label="Checks before approving">
          {asset.qa_issues.map((q, i) => (
            <li key={i}>⚠ {q}</li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[#EFE7DB]">
        <button
          disabled={locked || busy !== null}
          onClick={() => onSave(draft)}
          className="px-3 py-1.5 rounded-lg bg-[#1F1A17] text-white text-xs font-bold disabled:opacity-50"
        >
          {busy === `save-${asset.asset_id}` ? "Saving…" : "Save edits"}
        </button>
        <input
          className={`${field} flex-1 min-w-[160px]`}
          placeholder="Ask for a change, e.g. shorter, more playful"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          disabled={locked}
        />
        <button
          disabled={locked || busy !== null}
          onClick={onRewrite}
          className="px-3 py-1.5 rounded-lg border border-[#E1D7C8] text-xs font-bold inline-flex items-center gap-1 disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${busy === `rw-${asset.asset_id}` ? "animate-spin" : ""}`} /> Regenerate
        </button>
      </div>
      <p className="text-[10px] text-[#8A8176]">Saving an edit sends this channel back to review. Text in [brackets] needs your input.</p>
    </div>
  );
}
