import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatAction,
  ChatTurn,
  fetchChatOpening,
  SourceCheck,
  streamReportChat,
} from "@/lib/api-client";
import { countTokens, addLiveTokens } from "@/lib/tiktokenTracker";
import { RivalView } from "@/lib/rivalMetrics";
import { cn, safeHref } from "@/lib/utils";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Loader2,
  MessageSquare,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";

interface ChatWidgetProps {
  jobId: string;
  rivals: RivalView[];
  merchantName?: string;
  /** The workspace step the merchant is on; tailors context and available tools. */
  step?: string;
  /** The content asset currently open on screen, so "this" / "it" refers to it. */
  focusAssetId?: string;
  /** Optional controlled open state */
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Prefill or inject a draft into the chat */
  initialDraft?: string;
  onOpenRival: (index: number) => void;
  /** Runs a confirmed action against the API and resolves with a one-line result for the card. */
  onAction: (action: ChatAction) => Promise<string>;
}

type ActionState = ChatAction & { state: "pending" | "running" | "done" | "failed" | "dismissed"; result?: string };

interface Message extends ChatTurn {
  id: string;
  error?: boolean;
  /** Set on both the refused question and its refusal; neither is sent back as history. */
  offTopic?: boolean;
  /** Changes the assistant proposed; each runs only when the merchant confirms its card. */
  actions?: ActionState[];
  checks?: SourceCheck[];
  /** What a tool is doing right now, shown until the answer text arrives. */
  status?: string;
}

const MAX_STORED = 30;
const storageKey = (jobId: string) => `intelly-chat:${jobId}`;

function loadMessages(jobId: string): Message[] {
  try {
    const raw = window.localStorage.getItem(storageKey(jobId));
    const parsed = raw ? (JSON.parse(raw) as Message[]) : [];
    if (!Array.isArray(parsed)) return [];
    // An action still "running" when the page closed has an unknown outcome; offer it again.
    return parsed
      .filter((m) => m && typeof m.content === "string")
      .map((m) => ({
        ...m,
        status: undefined,
        actions: m.actions?.map((a) => (a.state === "running" ? { ...a, state: "pending" as const } : a)),
      }));
  } catch {
    return [];
  }
}

function saveMessages(jobId: string, messages: Message[]) {
  try {
    window.localStorage.setItem(storageKey(jobId), JSON.stringify(messages.slice(-MAX_STORED)));
  } catch {
    /* storage full or blocked: the conversation simply isn't remembered */
  }
}

/** Inline **bold** only; everything stays text, so model output can never inject markup. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    )
  );
}

function RichText({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2">
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim());
        if (lines.length && lines.every((l) => /^\s*([-*•]|\d+\.)\s+/.test(l))) {
          return (
            <ul key={i} className="space-y-1">
              {lines.map((l, j) => (
                <li key={j} className="flex gap-2">
                  <span className="mt-[7px] w-1 h-1 rounded-full bg-ink-faint shrink-0" />
                  <span>{inline(l.replace(/^\s*([-*•]|\d+\.)\s+/, ""))}</span>
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {inline(block)}
          </p>
        );
      })}
    </div>
  );
}

function suggestionsFor(rivals: RivalView[], merchantName?: string): string[] {
  const out: string[] = [];
  if (rivals.some((r) => r.priceValue != null)) out.push("Who has the lowest price, and how does it compare?");
  const mostComplained = [...rivals].sort((a, b) => b.complaints.length - a.complaints.length)[0];
  if (mostComplained?.complaints.length) out.push(`What do customers complain about at ${mostComplained.name}?`);
  if (rivals.length > 0) {
    out.push("Which rivals are advertising right now, and what do their ads say?");
    out.push(merchantName ? `Where is the gap ${merchantName} could own?` : "Where is the gap in this market?");
  } else {
    out.push("Summarize the current run progress and reasoning");
    out.push("Update our campaign goal");
    out.push("Show human-in-the-loop pending items");
  }
  if (rivals.length > 1) out.push(`How is ${rivals[0].name} different from ${rivals[1].name}?`);
  return out.slice(0, 4);
}

export function ChatWidget({
  jobId,
  rivals,
  merchantName,
  step,
  focusAssetId,
  isOpen,
  onOpenChange,
  initialDraft,
  onOpenRival,
  onAction,
}: ChatWidgetProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isOpen !== undefined ? isOpen : internalOpen;
  const setOpen = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      const val = typeof next === "function" ? next(open) : next;
      setInternalOpen(val);
      onOpenChange?.(val);
    },
    [open, onOpenChange]
  );
  const [messages, setMessages] = useState<Message[]>(() => loadMessages(jobId));
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (initialDraft) {
      setDraft(initialDraft);
    }
  }, [initialDraft]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const suggestions = useMemo(() => suggestionsFor(rivals, merchantName), [rivals, merchantName]);

  // Fetch step-aware opening message when the chat opens empty on a new step.
  const [opener, setOpener] = useState<{ message: string; suggestions: string[] } | null>(null);
  const lastOpenerStep = useRef<string | undefined>();
  useEffect(() => {
    if (!open || messages.length > 0 || !step || step === lastOpenerStep.current) return;
    lastOpenerStep.current = step;
    fetchChatOpening(jobId, step)
      .then(setOpener)
      .catch(() => {});
  }, [open, jobId, step, messages.length]);

  useEffect(() => {
    if (!streaming) saveMessages(jobId, messages);
  }, [jobId, messages, streaming]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const ask = useCallback(
    async (question: string, base: Message[] = messages) => {
      const text = question.trim().slice(0, 4000);
      if (!text || streaming) return;
      const user: Message = { id: `u-${Date.now()}`, role: "user", content: text };
      const replyId = `a-${Date.now()}`;
      // Failed and refused exchanges are shown but never sent back as conversation history.
      const history: ChatTurn[] = [...base.filter((m) => !m.error && !m.offTopic), user].map(({ role, content }) => ({
        role,
        content,
      }));

      setMessages([...base, user, { id: replyId, role: "assistant", content: "" }]);
      setDraft("");
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      // Track user prompt tokens live
      const promptTokens = countTokens(user.content);
      if (promptTokens > 0) {
        addLiveTokens(promptTokens);
      }

      const patch = (fn: (m: Message) => Message) =>
        setMessages((all) => all.map((m) => (m.id === replyId ? fn(m) : m)));

      try {
        const { offTopic } = await streamReportChat(
          jobId,
          history.slice(-12),
          {
            onDelta: (delta) => {
              const deltaTokens = countTokens(delta);
              if (deltaTokens > 0) {
                addLiveTokens(deltaTokens);
              }
              patch((m) => ({ ...m, content: m.content + delta, status: undefined }));
            },
            onStatus: (status) => patch((m) => ({ ...m, status })),
            onCheck: (check) => patch((m) => ({ ...m, status: undefined, checks: [...(m.checks ?? []), check] })),
            onAction: (action) =>
              patch((m) => ({ ...m, actions: [...(m.actions ?? []), { ...action, state: "pending" }] })),
          },
          controller.signal,
          step,
          focusAssetId,
        );
        if (offTopic) {
          setMessages((all) => all.map((m) => (m.id === replyId || m.id === user.id ? { ...m, offTopic: true } : m)));
        }
      } catch (err) {
        if (controller.signal.aborted) {
          patch((m) => (m.content ? m : { ...m, content: "Stopped.", error: true }));
        } else {
          const msg = err instanceof Error ? err.message : "The assistant could not answer.";
          patch((m) => ({ ...m, content: m.content ? `${m.content}\n\n(${msg})` : msg, error: true }));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        patch((m) => ({ ...m, status: undefined }));
      }
    },
    [jobId, messages, streaming]
  );

  const anyRunning = messages.some((m) => m.actions?.some((a) => a.state === "running"));

  const setActionState = (messageId: string, actionId: string, change: Partial<ActionState>) =>
    setMessages((all) =>
      all.map((m) =>
        m.id === messageId
          ? { ...m, actions: m.actions?.map((a) => (a.id === actionId ? { ...a, ...change } : a)) }
          : m
      )
    );

  const confirmAction = async (messageId: string, action: ActionState) => {
    if (anyRunning) return;
    setActionState(messageId, action.id, { state: "running", result: undefined });
    try {
      const result = await onAction(action);
      setActionState(messageId, action.id, { state: "done", result });
    } catch (err) {
      setActionState(messageId, action.id, {
        state: "failed",
        result: err instanceof Error ? err.message : "It did not run.",
      });
    }
  };

  const retryLast = () => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    // Re-ask from the conversation as it stood before the failed question.
    ask(lastUser.content, messages.slice(0, messages.findIndex((m) => m.id === lastUser.id)));
  };

  const mentioned = (text: string) => {
    const low = text.toLowerCase();
    return rivals.filter((r) => low.includes(r.name.toLowerCase()));
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="no-print fixed bottom-5 right-5 z-[55] inline-flex items-center gap-2.5 px-4 py-3 rounded-full bg-ink text-white shadow-2xl hover:scale-105 transition-all duration-200 border border-white/20 cursor-pointer animate-fade-up"
        aria-label="Open AI Assistant & HITL Chat"
      >
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
        </span>
        <Sparkles className="w-4 h-4 text-emerald-300" />
        <span className="text-xs sm:text-sm font-bold tracking-tight">AI Assistant & HITL</span>
        {messages.length > 0 && (
          <span className="ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-white/20 text-white">
            {messages.length}
          </span>
        )}
      </button>
    );
  }

  const last = messages[messages.length - 1];
  return (
    <div
      role="dialog"
      aria-label="Research assistant"
      className="no-print fixed z-[55] inset-x-2 bottom-2 top-16 sm:inset-x-auto sm:top-auto sm:right-5 sm:bottom-5 sm:w-[400px] sm:h-[min(620px,calc(100vh-6rem))] flex flex-col rounded-2xl bg-canvas border border-line shadow-2xl overflow-hidden animate-fade-up"
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-3 bg-ink text-white">
        <span className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-emerald-300" />
        </span>
        <div className="flex-1 min-w-0">
         <div className="text-sm font-bold">Campaign assistant</div>
          <div className="text-[11px] text-zinc-400">
            {step ? `Step: ${step}` : "Answers only from this report"}
          </div>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={() => {
              abortRef.current?.abort();
              setMessages([]);
            }}
            className="p-1.5 rounded-lg hover:bg-white/10 text-zinc-300"
            aria-label="Clear conversation"
            title="Clear conversation"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
        <button type="button" onClick={() => setOpen(false)} className="p-1.5 rounded-lg hover:bg-white/10 text-zinc-300" aria-label="Close assistant">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Conversation */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-3 animate-fade-up">
            <div className="rounded-2xl bg-white border border-line p-3.5 text-[13px] text-ink-soft leading-relaxed">
              {opener?.message ? (
                <RichText text={opener.message} />
              ) : rivals.length > 0 ? (
                <>
                  Ask anything about the {rivals.length} rivals in this report — prices, what customers say, their ads, or where{" "}
                  {merchantName || "you"} could stand out. I only use what the research found.
                </>
              ) : (
                <>
                  Ask for run progress summaries, reasoning, or propose updates to your campaign goal and initial merchant parameters. I also serve as your Human-in-the-Loop decision partner.
                </>
              )}
            </div>
            <div className="space-y-1.5">
              {(opener?.suggestions ?? suggestions).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => ask(s)}
                  className="w-full flex items-center justify-between gap-2 text-left rounded-xl border border-line bg-white px-3 py-2 text-xs font-medium text-ink hover:border-ink/30 hover:shadow-card transition"
                >
                  <span>{s}</span>
                  <ArrowRight className="w-3.5 h-3.5 text-ink-faint shrink-0" />
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ink text-white px-3.5 py-2 text-[13px] leading-relaxed whitespace-pre-wrap">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={m.id} className="flex justify-start">
              <div
                className={cn(
                  "max-w-[92%] rounded-2xl rounded-bl-md border px-3.5 py-2.5 text-[13px] leading-relaxed",
                  m.error
                    ? "bg-rose-50 border-rose-200 text-rose-900"
                    : m.offTopic
                      ? "bg-amber-50 border-amber-200 text-amber-950"
                      : "bg-white border-line text-ink-soft"
                )}
              >
                {m.content ? (
                  <RichText text={m.content} />
                ) : m.status ? (
                  <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-faint italic">
                    <Loader2 className="w-3.5 h-3.5 animate-spin not-italic" /> {m.status}
                  </span>
                ) : !m.actions?.length && !m.checks?.length ? (
                  <span className="inline-flex gap-1 py-1" aria-label="Thinking">
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="w-1.5 h-1.5 rounded-full bg-ink-faint animate-bounce" style={{ animationDelay: `${i * 120}ms` }} />
                    ))}
                  </span>
                ) : null}
                {m.content && m.status && (
                  <div className="mt-1.5 inline-flex items-center gap-1.5 text-[11px] text-ink-faint italic">
                    <Loader2 className="w-3 h-3 animate-spin" /> {m.status}
                  </div>
                )}

                {m.checks?.map((c, i) => (
                  <div
                    key={i}
                    className={cn(
                      "mt-2 flex items-start gap-2 rounded-lg px-2.5 py-2 text-[12px] border",
                      c.verdict === "confirmed" ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-amber-50 border-amber-200 text-amber-950"
                    )}
                  >
                    {c.verdict === "confirmed" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="font-semibold">
                        {c.verdict === "confirmed"
                          ? "Confirmed on their page just now"
                          : c.verdict === "not_found"
                            ? `Not found on ${c.pages_checked} page${c.pages_checked === 1 ? "" : "s"} checked just now`
                            : c.verdict === "unreachable"
                              ? "Their pages could not be reached"
                              : "No source pages recorded for this rival"}
                      </div>
                      {c.url && safeHref(c.url) && (
                        <a href={safeHref(c.url)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline truncate max-w-full">
                          {c.url.replace(/^https?:\/\/(www\.)?/, "")} <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}

                {m.actions?.map((a) => (
                  <div key={a.id} className="mt-2.5 rounded-xl border border-ink/15 bg-canvas p-3 space-y-2" role="group" aria-label={a.title}>
                    <div>
                      <div className="text-[12px] font-bold text-ink">{a.title}</div>
                      <div className="text-[12px] text-ink-soft leading-relaxed">{a.detail}</div>
                    </div>
                    {a.state === "pending" && (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => confirmAction(m.id, a)}
                          disabled={anyRunning}
                          className="px-3 py-1.5 rounded-lg bg-ink text-white text-[12px] font-semibold disabled:opacity-40"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => setActionState(m.id, a.id, { state: "dismissed" })}
                          className="px-3 py-1.5 rounded-lg border border-line bg-white text-[12px] font-semibold text-ink-soft hover:text-ink"
                        >
                          Dismiss
                        </button>
                      </div>
                    )}
                    {a.state === "running" && (
                      <div className="inline-flex items-center gap-1.5 text-[12px] text-ink-soft">
                        {a.kind === "refresh"
                          ? "Re-running the research — this takes a few minutes…"
                          : a.kind === "rewrite_asset" || a.kind === "regenerate_content"
                            ? "Rewriting copy with your instructions…"
                            : a.kind === "customize_strategy"
                              ? "Updating campaign strategy…"
                              : a.kind === "channel_approval"
                                ? "Updating channel approvals…"
                                : a.kind === "reschedule"
                                  ? "Updating schedule…"
                                  : "Working on it…"}
                      </div>
                    )}
                    {a.state === "done" && (
                      <div className="inline-flex items-start gap-1.5 text-[12px] text-emerald-800">
                        <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span>{a.result || "Done."}</span>
                      </div>
                    )}
                    {a.state === "failed" && (
                      <div className="space-y-1.5">
                        <div className="inline-flex items-start gap-1.5 text-[12px] text-rose-800">
                          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span>{a.result}</span>
                        </div>
                        <button type="button" onClick={() => confirmAction(m.id, a)} disabled={anyRunning} className="block text-[11px] font-semibold text-rose-800 hover:underline disabled:opacity-40">
                          Try again
                        </button>
                      </div>
                    )}
                    {a.state === "dismissed" && <div className="text-[11px] text-ink-faint">Dismissed — nothing was changed.</div>}
                  </div>
                ))}
                {m.offTopic && m.id === last?.id && !streaming && (
                  <div className="mt-2.5 pt-2 border-t border-amber-200 space-y-1">
                    {suggestions.slice(0, 3).map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => ask(s)}
                        className="w-full flex items-center justify-between gap-2 text-left rounded-lg bg-white/70 hover:bg-white px-2.5 py-1.5 text-[12px] font-medium text-ink transition"
                      >
                        <span>{s}</span>
                        <ArrowRight className="w-3 h-3 text-ink-faint shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
                {!m.error && !m.offTopic && m.content && !(streaming && m.id === last?.id) && mentioned(m.content).length > 0 && (
                  <div className="mt-2.5 pt-2 border-t border-line flex flex-wrap gap-1.5">
                    {mentioned(m.content).map((r) => (
                      <button
                        key={r.key}
                        type="button"
                        onClick={() => onOpenRival(r.index)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-canvas text-[11px] font-semibold text-ink hover:bg-[#EDE7D8] transition"
                      >
                        {r.name} <ArrowRight className="w-3 h-3" />
                      </button>
                    ))}
                  </div>
                )}
                {m.error && m.id === last?.id && !streaming && (
                  <button type="button" onClick={retryLast} className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-rose-800 hover:underline">
                    <RotateCcw className="w-3 h-3" /> Try again
                  </button>
                )}
              </div>
            </div>
          )
        )}
      </div>

      {/* Composer */}
      <form
        className="border-t border-line bg-white p-2.5 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <MessageSquare className="w-4 h-4 text-ink-faint mb-2.5 ml-1 shrink-0" />
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(draft);
            }
          }}
          rows={Math.min(4, Math.max(1, draft.split("\n").length))}
          maxLength={4000}
          placeholder="Ask about prices, reviews, ads…"
          aria-label="Your question"
          className="flex-1 resize-none bg-transparent text-[13px] leading-relaxed py-1.5 outline-none placeholder:text-ink-faint"
        />
        {streaming ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="w-9 h-9 rounded-xl bg-ink text-white flex items-center justify-center shrink-0"
            aria-label="Stop answering"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!draft.trim()}
            className="w-9 h-9 rounded-xl bg-ink text-white flex items-center justify-center shrink-0 disabled:opacity-30 transition"
            aria-label="Send"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        )}
      </form>
    </div>
  );
}
