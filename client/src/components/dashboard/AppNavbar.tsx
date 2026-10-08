import { useState } from "react";
import { Link } from "react-router-dom";
import { PlusCircle, RefreshCw, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlobalSettingsModal } from "./GlobalSettingsModal";

export interface NavSection {
  id: string;
  label: string;
}

interface AppNavbarProps {
  /** In-page sections to jump between; omitted on pages that have none. */
  sections?: NavSection[];
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  connectionStatus?: string;
  onReconnect?: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  COMPLETED: "Report ready",
  ERROR: "Disconnected",
  STREAMING: "Researching",
  CONNECTING: "Connecting",
  RECONNECTING: "Reconnecting",
  INTERRUPTED: "Waiting for you",
  IDLE: "Idle",
};

export const AppNavbar: React.FC<AppNavbarProps> = ({
  sections,
  activeTab,
  onTabChange,
  connectionStatus,
  onReconnect,
}) => {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <header className="no-print fixed top-0 left-0 right-0 z-50 bg-ink/95 text-white backdrop-blur-md border-b border-white/10 select-none">
      <div className="w-full max-w-7xl mx-auto flex items-center justify-between gap-4 px-4 sm:px-6 lg:px-8 h-12">
        <Link to="/" className="flex items-center gap-2 group shrink-0">
          <span className="text-lg font-bold tracking-tight font-display">intelly</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 group-hover:scale-125 transition-transform" />
        </Link>

        {sections && sections.length > 0 && (
          <nav className="min-w-0 flex items-center gap-0.5 overflow-x-auto [scrollbar-width:none]" aria-label="Report sections">
            {sections.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onTabChange?.(item.id)}
                  aria-current={isActive ? "true" : undefined}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0",
                    isActive ? "text-white bg-white/10" : "text-zinc-400 hover:text-white"
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        )}

        <div className="flex items-center gap-2.5 shrink-0">
          {connectionStatus && (
            <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-white/5 border border-white/10 text-zinc-300">
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  connectionStatus === "COMPLETED"
                    ? "bg-emerald-400"
                    : connectionStatus === "ERROR"
                      ? "bg-rose-400"
                      : "bg-amber-300 animate-pulse"
                )}
              />
              <span>{STATUS_LABEL[connectionStatus] ?? connectionStatus.toLowerCase()}</span>
              {connectionStatus === "ERROR" && onReconnect && (
                <button type="button" onClick={onReconnect} title="Reconnect" className="ml-0.5 hover:text-white">
                  <RefreshCw className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-white text-ink hover:bg-zinc-200 transition"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New research</span>
          </Link>
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            className="inline-flex items-center justify-center p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer"
            title="Global Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
      <GlobalSettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </header>
  );
};
