import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers, Trash2, ArrowRight, RefreshCw, Check, X } from "lucide-react";
import { listSessions, renameSession, deleteSession } from "@/lib/api-client";
import { SessionSummary } from "@/types/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  running: "bg-[#96BFE6]/30 text-[#0F2D4A] border-[#96BFE6]",
  pending: "bg-[#FDE583]/50 text-[#2D2306] border-[#FDE583]",
  complete: "bg-[#96C87C]/30 text-[#19350E] border-[#96C87C]",
  failed: "bg-rose-100 text-rose-700 border-rose-200",
};

export function RecentSessions() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions((await listSessions()).sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sessions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleDelete = async (jobId: string) => {
    if (!window.confirm("Delete this session? This removes its saved report and cannot be undone.")) return;
    setBusyId(jobId);
    try {
      await deleteSession(jobId);
      setSessions((rows) => rows.filter((s) => s.job_id !== jobId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete session.");
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = async (jobId: string) => {
    const label = draftLabel.trim();
    setEditingId(null);
    if (!label) return;
    setBusyId(jobId);
    try {
      await renameSession(jobId, label);
      setSessions((rows) => rows.map((s) => (s.job_id === jobId ? { ...s, label } : s)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename session.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="p-6 sm:p-7 rounded-[28px] bg-[#FFFDF9] border border-[#EDE7D8] shadow-xs space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-[#19191B]" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">Recent sessions</h3>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-1.5 text-[11px] font-bold text-zinc-500 hover:text-black transition"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && <p className="text-xs font-medium text-rose-600">{error}</p>}

      {!loading && sessions.length === 0 && !error && (
        <p className="text-xs text-zinc-500">No sessions yet. Launch a run and it will appear here.</p>
      )}

      <ul className="space-y-2">
        {sessions.map((s) => (
          <li
            key={s.job_id}
            className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8]"
          >
            <div className="min-w-0 flex-1">
              {editingId === s.job_id ? (
                <div className="flex items-center gap-1.5">
                  <input
                    autoFocus
                    value={draftLabel}
                    onChange={(e) => setDraftLabel(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleRename(s.job_id);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    className="flex-1 px-2.5 py-1 rounded-lg bg-white border border-[#EDE7D8] text-xs text-[#19191B] focus:outline-none focus:border-[#19191B]"
                  />
                  <button type="button" onClick={() => handleRename(s.job_id)} className="p-1 text-emerald-600 hover:bg-emerald-50 rounded-md">
                    <Check className="w-4 h-4" />
                  </button>
                  <button type="button" onClick={() => setEditingId(null)} className="p-1 text-zinc-400 hover:bg-zinc-100 rounded-md">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-xs font-bold text-[#19191B] truncate">
                    {s.label || s.product_name || "Untitled run"}
                  </p>
                  <p className="text-[11px] text-zinc-500 truncate">
                    {s.category || "—"} · <span className="font-mono">{s.job_id.slice(0, 14)}</span>
                  </p>
                </>
              )}
            </div>

            <span
              className={cn(
                "shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border capitalize",
                STATUS_STYLES[s.status] || "bg-zinc-100 text-zinc-600 border-zinc-200"
              )}
            >
              {s.status}
            </span>

            <div className="shrink-0 flex items-center gap-1">
              <button
                type="button"
                title="Open"
                onClick={() => navigate(`/campaigns/${encodeURIComponent(s.job_id)}`)}
                className="p-1.5 rounded-lg text-zinc-500 hover:text-black hover:bg-white transition"
              >
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                title="Rename"
                disabled={busyId === s.job_id}
                onClick={() => {
                  setEditingId(s.job_id);
                  setDraftLabel(s.label || s.product_name || "");
                }}
                className="px-2 py-1.5 rounded-lg text-[11px] font-bold text-zinc-500 hover:text-black hover:bg-white transition"
              >
                Rename
              </button>
              <button
                type="button"
                title="Delete"
                disabled={busyId === s.job_id}
                onClick={() => handleDelete(s.job_id)}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-600 hover:bg-rose-50 transition"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
