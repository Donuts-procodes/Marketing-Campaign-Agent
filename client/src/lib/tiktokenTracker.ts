/**
 * Client-side token tracking engine powered by js-tiktoken.
 * Tracks live token usage, prompt/response counts, and BYOK token rates.
 */

import { getEncoding, encodingForModel, type Tiktoken } from "js-tiktoken";
import { useEffect, useState } from "react";

const BYOK_STORAGE_KEY = "intelly.byok";

let cachedEncoder: Tiktoken | null = null;
let currentEncoderModel = "";

/**
 * Accurately encodes and counts tokens for a given string using tiktoken.
 */
export function countTokens(text: string, model: string = "gpt-4o"): number {
  if (!text) return 0;
  try {
    if (!cachedEncoder || currentEncoderModel !== model) {
      try {
        cachedEncoder = encodingForModel(model as any);
        currentEncoderModel = model;
      } catch {
        cachedEncoder = getEncoding("cl100k_base");
        currentEncoderModel = "cl100k_base";
      }
    }
    return cachedEncoder.encode(text).length;
  } catch {
    // Heuristic fallback: ~4 characters per token
    return Math.ceil(text.length / 4);
  }
}

export interface LiveTokenState {
  totalTokens: number;
  delta: number;
  direction: "up" | "down" | "idle";
  model: string;
  isByok: boolean;
  provider: string;
  estimatedCostUsd: number;
  lastUpdated: number;
}

// Global observable state for navbar and widgets
let globalTokenState: LiveTokenState = {
  totalTokens: 0,
  delta: 0,
  direction: "idle",
  model: "gpt-4o",
  isByok: false,
  provider: "openai",
  estimatedCostUsd: 0,
  lastUpdated: Date.now(),
};

const listeners = new Set<(state: LiveTokenState) => void>();

function notify() {
  listeners.forEach((listener) => listener({ ...globalTokenState }));
}

function calculateCost(tokens: number, model: string): number {
  // Approximate blended rate per 1K tokens
  let costPerThousand = 0.005; // default $5 / 1M = $0.005 / 1K
  if (model.includes("mini") || model.includes("haiku") || model.includes("flash")) {
    costPerThousand = 0.0003;
  } else if (model.includes("gpt-4o") || model.includes("sonnet")) {
    costPerThousand = 0.004;
  }
  return Number(((tokens / 1000) * costPerThousand).toFixed(4));
}

export function getSavedByokInfo(): { isByok: boolean; provider: string; model: string } {
  try {
    const raw = localStorage.getItem(BYOK_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.apiKey && parsed.apiKey.trim()) {
        return {
          isByok: true,
          provider: parsed.provider || "openai",
          model: parsed.model || "gpt-4o",
        };
      }
    }
  } catch {
    // ignore
  }
  return { isByok: false, provider: "openai", model: "gpt-4o" };
}

/**
 * Increment or set the live token usage.
 */
export function addLiveTokens(count: number, modelOverride?: string) {
  if (count <= 0) return;
  const byok = getSavedByokInfo();
  const model = modelOverride || byok.model;

  const prev = globalTokenState.totalTokens;
  const next = prev + count;

  globalTokenState = {
    totalTokens: next,
    delta: count,
    direction: "up",
    model,
    isByok: byok.isByok,
    provider: byok.provider,
    estimatedCostUsd: calculateCost(next, model),
    lastUpdated: Date.now(),
  };

  notify();

  // Reset direction indicator to idle after 1.8 seconds
  window.setTimeout(() => {
    if (globalTokenState.direction === "up" && Date.now() - globalTokenState.lastUpdated >= 1700) {
      globalTokenState.direction = "idle";
      globalTokenState.delta = 0;
      notify();
    }
  }, 1800);
}

/**
 * Explicitly sets the total token count (e.g. from backend telemetry or reset).
 */
export function setTotalTokens(total: number, modelOverride?: string) {
  const byok = getSavedByokInfo();
  const model = modelOverride || byok.model;
  const prev = globalTokenState.totalTokens;
  const delta = total - prev;

  globalTokenState = {
    totalTokens: Math.max(0, total),
    delta: Math.abs(delta),
    direction: delta > 0 ? "up" : delta < 0 ? "down" : "idle",
    model,
    isByok: byok.isByok,
    provider: byok.provider,
    estimatedCostUsd: calculateCost(total, model),
    lastUpdated: Date.now(),
  };

  notify();

  if (globalTokenState.direction !== "idle") {
    window.setTimeout(() => {
      globalTokenState.direction = "idle";
      globalTokenState.delta = 0;
      notify();
    }, 1800);
  }
}

/**
 * React hook subscribing to live tiktoken updates.
 */
export function useLiveTokenTracker(): LiveTokenState {
  const [state, setState] = useState<LiveTokenState>(() => {
    const byok = getSavedByokInfo();
    return {
      ...globalTokenState,
      isByok: byok.isByok,
      model: byok.model,
      provider: byok.provider,
    };
  });

  useEffect(() => {
    const handler = (s: LiveTokenState) => setState(s);
    listeners.add(handler);

    // Refresh BYOK info on mount
    const byok = getSavedByokInfo();
    if (byok.isByok !== globalTokenState.isByok || byok.model !== globalTokenState.model) {
      globalTokenState.isByok = byok.isByok;
      globalTokenState.model = byok.model;
      globalTokenState.provider = byok.provider;
      notify();
    }

    return () => {
      listeners.delete(handler);
    };
  }, []);

  return state;
}
