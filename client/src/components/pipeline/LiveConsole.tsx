import { useEffect, useRef, useState } from "react";
import { TelemetryLogItem } from "@/types/campaign";
import {
  Terminal,
  Copy,
  Check,
  Trash2,
  ArrowDownCircle,
  Filter,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * One colour per pipeline stage / research tool subagent.
 * Keep in sync with TAG_STYLES in orchestrator/core/log_format.py (server console colours).
 */
const TAG_STYLES: Record<string, { chip: string; dot: string; label: string }> = {
  DYNAMIC_PARAMS: { chip: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/40", dot: "bg-fuchsia-400", label: "Taxonomy" },
  TAVILY_SEARCH: { chip: "bg-sky-500/15 text-sky-300 border-sky-500/40", dot: "bg-sky-400", label: "Search" },
  DEEP_SEARCH: { chip: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40", dot: "bg-cyan-400", label: "Deep search" },
  DQS_EVAL: { chip: "bg-lime-500/15 text-lime-300 border-lime-500/40", dot: "bg-lime-400", label: "Quality" },
  AD_INTELLIGENCE: { chip: "bg-amber-500/15 text-amber-300 border-amber-500/40", dot: "bg-amber-400", label: "Ad intel" },
  LLM_SYNTH: { chip: "bg-violet-500/15 text-violet-300 border-violet-500/40", dot: "bg-violet-400", label: "Synthesis" },
  DATA_VALIDATION: { chip: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", dot: "bg-emerald-400", label: "Grounding" },
  FIND_MORE_COMPETITORS: { chip: "bg-pink-500/15 text-pink-300 border-pink-500/40", dot: "bg-pink-400", label: "Find more" },
  MORE_COMPETITORS_FOUND: { chip: "bg-pink-500/15 text-pink-300 border-pink-500/40", dot: "bg-pink-400", label: "Find more" },
  CONFIG: { chip: "bg-orange-500/20 text-orange-300 border-orange-500/50", dot: "bg-orange-400", label: "Config" },
  LLM_CONFIG: { chip: "bg-rose-500/20 text-rose-300 border-rose-500/50", dot: "bg-rose-400", label: "LLM config" },
  FILTER_VALIDATOR: { chip: "bg-teal-500/15 text-teal-300 border-teal-500/40", dot: "bg-teal-400", label: "Validator" },
  DATA_REPAIR: { chip: "bg-teal-500/15 text-teal-300 border-teal-500/40", dot: "bg-teal-400", label: "Repair" },
  REVIEW_CONTEXT: { chip: "bg-blue-500/15 text-blue-300 border-blue-500/40", dot: "bg-blue-400", label: "Reviews" },
  FRESHNESS_AUDIT: { chip: "bg-slate-500/15 text-slate-300 border-slate-500/40", dot: "bg-slate-400", label: "Freshness" },
  PRICE_NORM: { chip: "bg-green-500/15 text-green-300 border-green-500/40", dot: "bg-green-400", label: "Pricing" },
  EXEC_SUMMARY: { chip: "bg-zinc-500/15 text-zinc-200 border-zinc-500/40", dot: "bg-zinc-300", label: "Summary" },
  CHANGE_DETECT: { chip: "bg-yellow-500/15 text-yellow-300 border-yellow-500/40", dot: "bg-yellow-400", label: "Changes" },
  AD_COPY: { chip: "bg-purple-500/15 text-purple-300 border-purple-500/40", dot: "bg-purple-400", label: "Ad copy" },
  WEDGE_FINDER: { chip: "bg-cyan-500/15 text-cyan-200 border-cyan-400/40", dot: "bg-cyan-300", label: "Niche scan" },
  THREAT_MONITOR: { chip: "bg-red-500/15 text-red-300 border-red-500/40", dot: "bg-red-400", label: "Threat watch" },
  LEAP_BENCHMARK: { chip: "bg-purple-500/15 text-purple-200 border-purple-400/40", dot: "bg-purple-300", label: "Leap" },
  PROFILE_COMPLETER: { chip: "bg-green-500/15 text-green-300 border-green-500/40", dot: "bg-green-400", label: "Profile facts" },
  NODE: { chip: "bg-indigo-500/15 text-indigo-300 border-indigo-500/40", dot: "bg-indigo-400", label: "Pipeline" },
};

// Matches "Round N query M/T [vector][time] → domain: query text"
const QUERY_LINE_RE = /^Round \d+ query \d+\/\d+ \[([^\]]+)\]/;
// Matches "Queue N/T: https://..."
const CRAWL_QUEUE_RE = /^Queue \d+\/\d+: (https?:\/\/\S+)/;

/** Renders search query lines with vector badge + optional clickable URL for crawl queues. */
function renderQueryLine(rest: string) {
  const crawlMatch = rest.match(CRAWL_QUEUE_RE);
  if (crawlMatch) {
    const url = crawlMatch[1];
    const prefix = rest.slice(0, rest.indexOf(url));
    return (
      <span>
        <span className="text-cyan-300">{prefix}</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-400 underline underline-offset-2 hover:text-cyan-200 break-all"
        >
          {url}
        </a>
      </span>
    );
  }

  const qMatch = rest.match(QUERY_LINE_RE);
  if (qMatch) {
    const vector = qMatch[1];
    // Colour the vector name and make the query text stand out.
    const afterVector = rest.slice(rest.indexOf(`[${vector}]`) + vector.length + 2).trim();
    return (
      <span>
        <span className="text-slate-400">{rest.slice(0, rest.indexOf(`[${vector}]`))}</span>
        <span className="px-1 py-0.5 rounded text-[10px] font-bold bg-sky-900/50 text-sky-300 border border-sky-700/40">
          {vector}
        </span>
        <span className="text-slate-300"> {afterVector}</span>
      </span>
    );
  }

  return <span className="text-slate-200">{rest}</span>;
}
const DEFAULT_TAG_STYLE = { chip: "bg-slate-800 text-slate-300 border-slate-700", dot: "bg-slate-400", label: "Other" };

const LEVEL_BADGES: Record<TelemetryLogItem["level"], string> = {
  INFO: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  WARN: "bg-amber-400/25 text-amber-200 border-amber-400/50",
  ERROR: "bg-rose-500/30 text-rose-200 border-rose-500/60",
};

/** Splits "[TAG] rest" into its tag and text; untagged pipeline lines are grouped under NODE. */
function parseTag(message: string): { tag: string | null; rest: string } {
  const match = message.match(/^\[([A-Z][A-Z0-9_]*)\]\s*(.*)$/s);
  if (match) return { tag: match[1], rest: match[2] };
  if (/^(Started|Completed) execution node|^Orchestration run/.test(message)) {
    return { tag: "NODE", rest: message };
  }
  return { tag: null, rest: message };
}

function tagStyle(tag: string | null) {
  return (tag && TAG_STYLES[tag]) || DEFAULT_TAG_STYLE;
}

interface LiveConsoleProps {
  logs: TelemetryLogItem[];
  onClearLogs?: () => void;
  className?: string;
}

export function LiveConsole({
  logs,
  onClearLogs,
  className,
}: LiveConsoleProps) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevel, setFilterLevel] = useState<"ALL" | "INFO" | "WARN" | "ERROR">("ALL");
  const [filterTag, setFilterTag] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const terminalBottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (autoScroll) {
      terminalBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const handleCopy = () => {
    const text = logs
      .map(
        (l) =>
          `[${new Date(l.timestamp).toISOString()}] [${l.level}] ${l.message}`
      )
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Count lines per tag for the colour legend.
  const tagCounts = new Map<string, number>();
  for (const log of logs) {
    const { tag } = parseTag(log.message);
    if (tag) tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
  }

  const filteredLogs = logs.filter((log) => {
    if (filterLevel !== "ALL" && log.level !== filterLevel) return false;
    if (filterTag && parseTag(log.message).tag !== filterTag) return false;
    return true;
  });

  const renderHighlightedMessage = (message: string) => {
    const { tag, rest } = parseTag(message);
    if (!tag) {
      return <span className="text-slate-200">{message}</span>;
    }
    const style = tagStyle(tag);
    const isQueryOrCrawl = (tag === "TAVILY_SEARCH" || tag === "DEEP_SEARCH")
      && (QUERY_LINE_RE.test(rest) || CRAWL_QUEUE_RE.test(rest));
    return (
      <span className="inline-flex items-baseline gap-1.5 flex-wrap">
        <span
          className={cn(
            "inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded border tracking-wide",
            style.chip
          )}
          title={style.label}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full", style.dot)} />
          {tag}
        </span>
        {isQueryOrCrawl ? renderQueryLine(rest) : <span className="text-slate-200">{rest}</span>}
      </span>
    );
  };

  return (
    <div
      className={cn(
        "flex flex-col h-[340px] rounded-2xl bg-slate-950 border border-slate-800/90 shadow-2xl overflow-hidden font-mono text-xs",
        className
      )}
    >
      {/* Terminal Title Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/90 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block" />
          </div>
          <div className="flex items-center gap-1.5 text-slate-300 font-semibold text-xs ml-2">
            <Terminal className="w-3.5 h-3.5 text-indigo-400" />
            <span>Agent Telemetry Stream</span>
          </div>
        </div>

        {/* Console Controls */}
        <div className="flex items-center gap-2">
          {/* Level Filter */}
          <div className="flex items-center gap-1 text-[11px] bg-slate-950 px-2 py-1 rounded-lg border border-slate-800">
            <Filter className="w-3 h-3 text-slate-500" />
            <select
              value={filterLevel}
              onChange={(e) => setFilterLevel(e.target.value as any)}
              className="bg-transparent text-slate-300 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All ({logs.length})</option>
              <option value="INFO">Info</option>
              <option value="WARN">Warnings</option>
              <option value="ERROR">Errors</option>
            </select>
          </div>

          {/* Auto-scroll button */}
          <button
            type="button"
            onClick={() => setAutoScroll(!autoScroll)}
            className={cn(
              "px-2 py-1 rounded-lg text-[11px] border flex items-center gap-1 transition-colors",
              autoScroll
                ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/30"
                : "bg-slate-900 text-slate-500 border-slate-800 hover:text-slate-300"
            )}
            title="Toggle Auto-Scroll"
          >
            <ArrowDownCircle className="w-3 h-3" />
            <span>Scroll</span>
          </button>

          {/* Copy Button */}
          <button
            type="button"
            onClick={handleCopy}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition"
            title="Copy All Logs"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          {/* Clear Logs */}
          {onClearLogs && (
            <button
              type="button"
              onClick={onClearLogs}
              className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-rose-400 border border-slate-800 transition"
              title="Clear Console"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Colour legend: one flag per subagent, click to filter */}
      {tagCounts.size > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3.5 py-2 bg-slate-900/60 border-b border-slate-800/80">
          {[...tagCounts.entries()].map(([tag, count]) => {
            const style = tagStyle(tag);
            const active = filterTag === tag;
            return (
              <button
                key={tag}
                type="button"
                onClick={() => setFilterTag(active ? null : tag)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold transition",
                  style.chip,
                  active ? "ring-1 ring-white/60" : filterTag ? "opacity-40 hover:opacity-80" : "hover:brightness-125"
                )}
                title={active ? "Show all" : `Show only ${tag}`}
              >
                <span className={cn("w-2 h-2 rounded-full", style.dot)} />
                {style.label}
                <span className="opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Terminal Output Body */}
      <div className="flex-1 p-3.5 overflow-y-auto space-y-1.5 selection:bg-indigo-600/30">
        {filteredLogs.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-1">
            <Terminal className="w-6 h-6 opacity-40" />
            <p>Telemetry socket idle. Logs will stream on graph execution.</p>
          </div>
        ) : (
          filteredLogs.map((log) => {
            const timeStr = new Date(log.timestamp).toLocaleTimeString([], {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });

            return (
              <div
                key={log.id}
                className={cn(
                  "flex items-start gap-2.5 py-0.5 leading-relaxed hover:bg-slate-900/50 px-1.5 rounded transition-colors",
                  log.level === "ERROR" && "text-rose-400 bg-rose-950/20",
                  log.level === "WARN" && "text-amber-300 bg-amber-950/20",
                  log.level === "INFO" && "text-slate-300"
                )}
              >
                <span className="text-slate-600 text-[10px] select-none flex-shrink-0 pt-0.5">
                  {timeStr}
                </span>

                <span
                  className={cn(
                    "text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 w-12 text-center",
                    LEVEL_BADGES[log.level]
                  )}
                >
                  {log.level}
                </span>

                <div className="flex-1 break-words">
                  {renderHighlightedMessage(log.message)}
                </div>
              </div>
            );
          })
        )}
        <div ref={terminalBottomRef} />
      </div>
    </div>
  );
}
