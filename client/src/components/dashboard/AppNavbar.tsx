import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  SlidersHorizontal,
  Activity,
  PlusCircle,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AppNavbarProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  connectionStatus?: string;
  onReconnect?: () => void;
}

export const AppNavbar: React.FC<AppNavbarProps> = ({
  activeTab = "dashboard",
  onTabChange,
  connectionStatus,
  onReconnect,
}) => {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "competitors", label: "Competitors & SWOT", icon: Users },
    { id: "playbook", label: "Action Playbook", icon: SlidersHorizontal },
    { id: "agents", label: "Dynamic Framework", icon: SlidersHorizontal },
    { id: "telemetry", label: "Live Telemetry", icon: Activity },
  ];

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-[#19191B]/95 text-white backdrop-blur-md border-b border-white/10 shadow-lg select-none">
      <div className="w-full max-w-7xl mx-auto flex items-center justify-between gap-4 px-4 sm:px-6 lg:px-8 py-2.5">
        {/* Brand Logo */}
        <Link to="/" className="flex items-center gap-2 group shrink-0">
          <span className="text-xl font-bold tracking-tight text-white font-mono">
            market.intel
          </span>
          <span className="w-2 h-2 rounded-full bg-emerald-400 group-hover:scale-125 transition-transform" />
          <span className="hidden md:inline-block text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 ml-1">
            v2.0
          </span>
        </Link>

        {/* Center Navigation Links */}
        <nav className="flex items-center gap-1 sm:gap-1.5 overflow-x-auto no-scrollbar py-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onTabChange?.(item.id)}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all shrink-0 cursor-pointer",
                  isActive
                    ? "text-white bg-zinc-800 font-semibold border border-zinc-700"
                    : "text-zinc-400 hover:text-white hover:bg-zinc-850"
                )}
              >
                <Icon className={cn("w-3.5 h-3.5", isActive ? "text-emerald-400" : "text-zinc-400")} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Action Section */}
        <div className="flex items-center gap-2.5 shrink-0">
          {connectionStatus && (
            <div className="hidden lg:flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-white/5 border border-white/10 text-zinc-300">
              <span
                className={cn(
                  "w-2 h-2 rounded-full",
                  connectionStatus === "COMPLETED"
                    ? "bg-emerald-500"
                    : connectionStatus === "ERROR"
                    ? "bg-rose-500"
                    : "bg-amber-400 animate-pulse"
                )}
              />
              <span className="capitalize">{connectionStatus.toLowerCase()}</span>
              {connectionStatus === "ERROR" && onReconnect && (
                <button
                  type="button"
                  onClick={onReconnect}
                  title="Reconnect to stream"
                  className="ml-1 hover:text-white cursor-pointer"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              )}
            </div>
          )}

          <Link
            to="/"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-white text-[#19191B] hover:bg-zinc-200 transition shadow-xs"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New Strategy</span>
          </Link>
        </div>
      </div>
    </header>
  );
};
