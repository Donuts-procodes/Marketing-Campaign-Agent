import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  SlidersHorizontal,
  Activity,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarDockProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}

export const SidebarDock: React.FC<SidebarDockProps> = ({
  activeTab = "dashboard",
  onTabChange,
}) => {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "competitors", label: "Competitors & SWOT", icon: Users },
    { id: "agents", label: "Agent Services & Models", icon: SlidersHorizontal },
    { id: "telemetry", label: "Live Telemetry", icon: Activity },
  ];

  return (
    <aside className="w-56 lg:w-60 bg-[#19191B] text-white rounded-[28px] p-5 flex flex-col justify-between shrink-0 shadow-2xl select-none">
      {/* Brand Logo */}
      <div className="space-y-6">
        <div className="flex items-center justify-between px-2 pt-1">
          <Link to="/" className="flex items-center gap-1.5 group">
            <span className="text-2xl font-bold tracking-tight text-white font-['Outfit',sans-serif]">
              intelly
            </span>
            <span className="w-2.5 h-2.5 rounded-full bg-[#F472B6] group-hover:scale-125 transition-transform" />
          </Link>
          <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-xs text-zinc-400 cursor-pointer hover:bg-white/20 transition">
            &lsaquo;
          </div>
        </div>

        {/* Navigation */}
        <div className="space-y-1.5">
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider px-3 block">
            Navigation
          </span>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onTabChange?.(item.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl text-xs font-medium transition-all text-left group cursor-pointer",
                    isActive
                      ? "text-[#F9BCD9] bg-white/[0.08] shadow-inner font-semibold"
                      : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                  )}
                >
                  <Icon
                    className={cn(
                      "w-4 h-4 transition-transform group-hover:scale-110",
                      isActive ? "text-[#F9BCD9]" : "text-zinc-400 group-hover:text-zinc-200"
                    )}
                  />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer Quick Action */}
      <div className="pt-4 border-t border-white/10 space-y-2">
        <Link
          to="/"
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-2xl text-xs text-zinc-400 hover:text-rose-300 hover:bg-rose-500/10 transition group"
        >
          <LogOut className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          <span>New Strategy Run</span>
        </Link>
      </div>
    </aside>
  );
};
