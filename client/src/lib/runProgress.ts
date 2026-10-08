import { TelemetryLogItem } from "@/types/campaign";

/**
 * Reads the research agent's telemetry and turns it into what a merchant can follow:
 * which stage the run is in, plain-language activity, live counters, and the shortlist of
 * rivals as soon as it is settled (long before the report itself exists).
 */

export const STAGES = [
  { id: "understand", label: "Understanding your business" },
  { id: "discover", label: "Finding competitors" },
  { id: "research", label: "Researching the top rivals" },
  { id: "report", label: "Writing your report" },
] as const;

const STAGE_OF_TAG: Record<string, number> = {
  CONFIG: 0,
  CAMPAIGN_CLASSIFIED: 0,
  INTENT_UNDERSTOOD: 0,
  DYNAMIC_PARAMS: 0,
  TAVILY_SEARCH: 1,
  DISCOVERY: 1,
  GEO_FILTER: 1,
  RECENCY: 1,
  COMPETITOR_LIST: 2,
  DEEP_TARGETS: 2,
  DEEP_SEARCH: 2,
  AD_INTELLIGENCE: 2,
  DQS_EVAL: 2,
  TAXONOMY_REVISED: 2,
  PLATEAU_STOP: 2,
  COMPETITOR_BENCH: 2,
  LLM_SYNTH: 3,
  DATA_VALIDATION: 3,
  VALIDATOR: 3,
  RELEVANCE_FILTER: 3,
};

export interface RunActivity {
  id: string;
  text: string;
  timestamp: number;
}

export interface RunProgress {
  stageIndex: number;
  startedAt: number | null;
  lastAt: number | null;
  shortlist: string[];
  reserveCount: number | null;
  candidates: number | null;
  stats: { results: number; pages: number; adHooks: number };
  activity: RunActivity[];
}

const TAG_RE = /^\[([A-Z_]+)\]\s*(.*)$/s;
const num = (s: string | undefined) => (s ? Number(s.replace(/,/g, "")) : 0);

function describe(tag: string, rest: string): string | null {
  switch (tag) {
    case "CAMPAIGN_CLASSIFIED":
    case "INTENT_UNDERSTOOD":
      return "Understood your business and goal";
    case "DYNAMIC_PARAMS": {
      const m = rest.match(/(\d+) critical drivers/);
      return m ? `Worked out the ${m[1]} things buyers in your market compare` : "Mapped what buyers compare";
    }
    case "TAVILY_SEARCH": {
      const m = rest.match(/returned (\d+) results/);
      return m ? `Searched the web — ${m[1]} results` : null; // per-query lines are noise
    }
    case "DISCOVERY": {
      const m = rest.match(/alternatives to (.+?) ->/);
      return m ? `Looked for alternatives to ${m[1]}` : "Widened the competitor search";
    }
    case "COMPETITOR_LIST":
      return "Picked the closest rivals for deep research";
    case "DEEP_SEARCH": {
      const m = rest.match(/Scraped (\d+)\//);
      return m ? `Read ${m[1]} pages on rivals' own websites` : null;
    }
    case "AD_INTELLIGENCE": {
      const m = rest.match(/Collected (\d+) real ad hooks across (\d+)/);
      return m ? `Found ${m[1]} live ads from ${m[2]} rivals` : null;
    }
    case "DQS_EVAL": {
      const m = rest.match(/DQS (\d\.\d+)/);
      return m ? `Checked data quality — ${Math.round(Number(m[1]) * 100)}%` : null;
    }
    case "GEO_FILTER":
      return "Removed results from outside your market area";
    case "RECENCY":
      return "Dropped outdated pages";
    case "TAXONOMY_REVISED":
      return "Adjusted the comparison factors to fit what was found";
    case "PLATEAU_STOP":
      return "Stopped early — no new information was turning up";
    case "LLM_SYNTH":
      return rest.startsWith("Produced") ? "Drafted the competitor profiles" : "Writing the report";
    case "DATA_VALIDATION":
      return "Fact-checked every claim against its source";
    case "VALIDATOR": {
      if (rest.startsWith("Sending the research back")) return "Sent the research back for more evidence";
      const m = rest.match(/rejected (\d+) item/);
      if (!m) return null;
      return Number(m[1]) ? `A second reviewer removed ${m[1]} item${m[1] === "1" ? "" : "s"} its source didn't back up` : "A second reviewer approved every item";
    }
    case "RELEVANCE_FILTER":
      return "Ranked what matters most for you";
    default:
      return null;
  }
}

function splitNames(list: string): string[] {
  return list
    .split(/,\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function parseRunProgress(logs: TelemetryLogItem[]): RunProgress {
  const progress: RunProgress = {
    stageIndex: 0,
    startedAt: logs[0]?.timestamp ?? null,
    lastAt: logs[logs.length - 1]?.timestamp ?? null,
    shortlist: [],
    reserveCount: null,
    candidates: null,
    stats: { results: 0, pages: 0, adHooks: 0 },
    activity: [],
  };

  for (const log of logs) {
    const m = (log.message || "").match(TAG_RE);
    if (!m) continue;
    const [, tag, rest] = m;

    const stage = STAGE_OF_TAG[tag];
    if (stage !== undefined) progress.stageIndex = Math.max(progress.stageIndex, stage);

    if (tag === "TAVILY_SEARCH") {
      progress.stats.results += num(rest.match(/returned (\d+) results/)?.[1]);
    } else if (tag === "DEEP_SEARCH") {
      progress.stats.pages += num(rest.match(/Scraped (\d+)\//)?.[1]);
    } else if (tag === "AD_INTELLIGENCE") {
      progress.stats.adHooks += num(rest.match(/Collected (\d+) real ad hooks/)?.[1]);
    } else if (tag === "COMPETITOR_LIST") {
      const list = rest.match(/on:\s*(.+)$/)?.[1];
      if (list) progress.shortlist = splitNames(list);
      const found = rest.match(/^(\d+) competitor/)?.[1];
      if (found) progress.candidates = num(found);
    } else if (tag === "DEEP_TARGETS" && progress.shortlist.length === 0) {
      // Servers older than the locked-shortlist pipeline only name rivals here.
      const list = rest.match(/competitor\(s\) \((.+)\)\s*$/)?.[1];
      if (list) progress.shortlist = splitNames(list);
    } else if (tag === "DISCOVERY") {
      const c = rest.match(/-> (\d+) candidates/)?.[1];
      if (c) progress.candidates = num(c);
    } else if (tag === "COMPETITOR_BENCH") {
      const r = rest.match(/(\d+) held in reserve/)?.[1];
      if (r) progress.reserveCount = num(r);
    }

    const text = describe(tag, rest);
    if (text && progress.activity[progress.activity.length - 1]?.text !== text) {
      progress.activity.push({ id: log.id, text, timestamp: log.timestamp });
    }
  }

  return progress;
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}
