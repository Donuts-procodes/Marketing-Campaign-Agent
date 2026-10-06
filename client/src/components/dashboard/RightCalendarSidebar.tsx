import { RefreshCw, Terminal, CheckCircle, Clock } from "lucide-react";

interface RightCalendarSidebarProps {
  onReconnect?: () => void;
  onOpenLogs?: () => void;
  connectionStatus?: string;
}

export const RightCalendarSidebar: React.FC<RightCalendarSidebarProps> = ({
  onReconnect,
  onOpenLogs,
  connectionStatus = "STREAMING",
}) => {
  const isCompleted = connectionStatus === "COMPLETED";

  return (
    <aside className="w-full lg:w-64 xl:w-72 bg-white rounded-lg p-3.5 border border-zinc-200 shadow-xs flex flex-col shrink-0 space-y-3">
      <div>
        <span className="text-xs font-bold uppercase tracking-wider text-zinc-500 block">
          Agent Execution
        </span>
        <div className="mt-1.5 flex items-center justify-between">
          <span className="text-xs text-zinc-700 font-medium">Pipeline Status</span>
          <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2 py-0.5 rounded bg-zinc-100 text-zinc-800 border border-zinc-200">
            {isCompleted ? (
              <CheckCircle className="w-3 h-3 text-emerald-600" />
            ) : (
              <Clock className="w-3 h-3 text-amber-600" />
            )}
            {connectionStatus}
          </span>
        </div>
      </div>

      <div className="pt-2 border-t border-zinc-100 flex items-center gap-2">
        {onReconnect && (
          <button
            type="button"
            onClick={onReconnect}
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-semibold border border-zinc-300 bg-white hover:bg-zinc-50 text-zinc-700 transition cursor-pointer"
          >
            <RefreshCw className="w-3 h-3" />
            Reconnect
          </button>
        )}
        {onOpenLogs && (
          <button
            type="button"
            onClick={onOpenLogs}
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-semibold bg-zinc-900 hover:bg-zinc-800 text-white transition cursor-pointer"
          >
            <Terminal className="w-3 h-3" />
            Live Logs
          </button>
        )}
      </div>
    </aside>
  );
};
