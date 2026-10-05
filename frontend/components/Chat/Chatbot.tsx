"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { getApiBase } from "@/lib/api";
import { cityName } from "@/lib/places";
import { MarkdownMessage } from "./MessageComponents";

/*
 * SkyMind Assistant: the chat panel available on every page.
 *
 * The backend streams plain text from POST /api/chat. Fixed messages (rate
 * limit, off-topic redirect, message too long) come back with the header
 * X-SkyMind-Message-Type: notice and are shown as notices, not as answers.
 */

type Message =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; status: "streaming" | "done" | "stopped" | "error" }
  | { id: string; role: "notice"; content: string };

const ASSISTANT_NAME = "SkyMind Assistant";
const MAX_LEN = 1000;
const KEEP_MESSAGES = 60; // stored per session in this browser
const SLOW_AFTER_MS = 7000;
const ERROR_TEXT = "I couldn't get an answer just now. The server may be waking up; try again in a moment.";

const newId = () => Math.random().toString(36).slice(2, 10);

function formatDay(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

// The last assistant message asks for a date: offer quick answers.
function asksForDate(text: string): boolean {
  const t = text.trim();
  return /\?\s*$/.test(t) && /\b(date|when|which day|what day|travel on|departure)\b/i.test(t);
}

function ChatbotContent() {
  const searchParams = useSearchParams();
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [contextOn, setContextOn] = useState(true);
  const [atBottom, setAtBottom] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isMac, setIsMac] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const wasOpen = useRef(false);

  // Route on the current page (search results, forecast), sent as context.
  const origin = searchParams?.get("origin") || null;
  const destination = searchParams?.get("destination") || null;
  const date = searchParams?.get("departure_date") || null;
  const routeContext = origin && destination
    ? {
        origin, destination, departure_date: date,
        cabin_class: searchParams?.get("cabin_class") ?? "ECONOMY",
        adults: searchParams?.get("adults") ?? "1",
      }
    : null;
  const contextActive = Boolean(routeContext && contextOn);

  // ── Session ────────────────────────────────────────────────────────────
  useEffect(() => {
    setIsMac(/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent));
    try {
      let sid = localStorage.getItem("skymind_session_id");
      if (!sid) {
        sid = "sess_" + newId();
        localStorage.setItem("skymind_session_id", sid);
      }
      setSessionId(sid);
      const saved = localStorage.getItem(`skymind_chat_${sid}`);
      if (saved) {
        const parsed = JSON.parse(saved) as Array<Partial<Message> & { role: string; content: string }>;
        // Older saves have no id/status; anything that was mid-stream when the
        // page closed is shown as stopped.
        setMessages(parsed.map(m => {
          if (m.role === "assistant") {
            const st = (m as { status?: string }).status;
            return { id: m.id || newId(), role: "assistant", content: m.content, status: st === "error" ? "error" : st === "stopped" || st === "streaming" ? "stopped" : "done" };
          }
          if (m.role === "user") return { id: m.id || newId(), role: "user", content: m.content };
          return { id: m.id || newId(), role: "notice", content: m.content };
        }));
      }
    } catch {
      // Storage blocked (private mode): chat still works, it just isn't kept.
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    try {
      if (messages.length === 0) localStorage.removeItem(`skymind_chat_${sessionId}`);
      else localStorage.setItem(`skymind_chat_${sessionId}`, JSON.stringify(messages.slice(-KEEP_MESSAGES)));
    } catch { /* ignore */ }
  }, [messages, sessionId]);

  // ── Open / close, focus ───────────────────────────────────────────────
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (isOpen) {
      wasOpen.current = true;
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (wasOpen.current) {
      launcherRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen(o => !o);
      } else if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen]);

  // Full-screen on phones: stop the page behind from scrolling.
  useEffect(() => {
    if (!isOpen) return;
    const mq = window.matchMedia("(max-width: 640px)");
    if (!mq.matches) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [isOpen]);

  // ── Scrolling: follow new text only if the reader is at the bottom ─────
  const onScroll = () => {
    const el = logRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
  };
  const scrollToBottom = (smooth = true) => {
    const el = logRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  };
  useLayoutEffect(() => {
    if (isOpen && atBottom) scrollToBottom(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, isOpen, busy]);

  // ── Composer ───────────────────────────────────────────────────────────
  const autosize = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  };
  useEffect(autosize, [input]);

  const updateAssistant = (id: string, patch: (m: Extract<Message, { role: "assistant" }>) => Partial<Extract<Message, { role: "assistant" }>>) => {
    setMessages(prev => prev.map(m => (m.id === id && m.role === "assistant" ? { ...m, ...patch(m) } : m)));
  };

  const send = async (text: string, history?: Message[]) => {
    const query = text.trim().slice(0, MAX_LEN);
    if (!query || busy) return;

    const base = history ?? messages;
    const userMsg: Message = { id: newId(), role: "user", content: query };
    const assistantId = newId();
    const conversation = [...base, userMsg];
    setMessages([...conversation, { id: assistantId, role: "assistant", content: "", status: "streaming" }]);
    setInput("");
    setBusy(true);
    setSlow(false);
    setAtBottom(true);

    const slowTimer = window.setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`${getApiBase()}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          // Only real turns go to the model; notices are UI-only.
          messages: conversation
            .filter(m => m.role === "user" || (m.role === "assistant" && m.status !== "error" && m.content))
            .map(m => ({ role: m.role, content: m.content })),
          session_id: sessionId,
          route_context: contextActive ? routeContext : null,
        }),
      });

      if (res.headers.get("X-SkyMind-Message-Type") === "notice") {
        const notice = (await res.text()).trim() || "That message couldn't be handled. Try rephrasing it.";
        setMessages(prev => prev.map(m => (m.id === assistantId ? { id: assistantId, role: "notice", content: notice } : m)));
        return;
      }
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (chunk) updateAssistant(assistantId, m => ({ content: m.content + chunk }));
      }
      updateAssistant(assistantId, m => (m.content.trim() ? { status: "done" } : { status: "error", content: ERROR_TEXT }));
    } catch (err) {
      if ((err as Error)?.name === "AbortError") {
        updateAssistant(assistantId, () => ({ status: "stopped" }));
      } else {
        console.error("Chat request failed:", err);
        updateAssistant(assistantId, m => ({ status: "error", content: m.content || ERROR_TEXT }));
      }
    } finally {
      window.clearTimeout(slowTimer);
      abortRef.current = null;
      setBusy(false);
      setSlow(false);
    }
  };

  const stop = () => abortRef.current?.abort();

  // Retry the question that produced a failed or stopped answer.
  const retry = (assistantId: string) => {
    const idx = messages.findIndex(m => m.id === assistantId);
    const question = [...messages.slice(0, idx)].reverse().find(m => m.role === "user");
    if (!question) return;
    const qIdx = messages.indexOf(question);
    send(question.content, messages.slice(0, qIdx));
  };

  const newChat = () => {
    abortRef.current?.abort();
    const sid = "sess_" + newId();
    try {
      localStorage.removeItem(`skymind_chat_${sessionId}`);
      localStorage.setItem("skymind_session_id", sid);
    } catch { /* ignore */ }
    setSessionId(sid);
    setMessages([]);
    setInput("");
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const copy = async (m: Message) => {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopiedId(m.id);
      window.setTimeout(() => setCopiedId(c => (c === m.id ? null : c)), 1500);
    } catch { /* clipboard blocked */ }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(input);
    }
  };

  // ── Suggestions ────────────────────────────────────────────────────────
  const routeLabel = routeContext
    ? `${cityName(routeContext.origin)} to ${cityName(routeContext.destination)}`
    : null;
  const suggestions = contextActive && routeLabel
    ? [
        `Should I book ${routeLabel} now or wait?`,
        `What's the cheapest flight from ${routeLabel}?`,
        `Which airlines fly non-stop from ${routeLabel}?`,
      ]
    : [
        "Cheapest flight from Delhi to Mumbai this week",
        "Should I book Bengaluru to Goa now or wait?",
        "Which airlines fly non-stop from Kolkata to Chennai?",
      ];

  const last = messages[messages.length - 1];
  const showDateChips = !busy && last?.role === "assistant" && last.status === "done" && asksForDate(last.content);
  const shortcut = isMac ? "⌘K" : "Ctrl K";
  const dayLabel = formatDay(date);

  return (
    <>
      {!isOpen && (
        <button
          ref={launcherRef}
          type="button"
          className="sm-chat-launcher"
          onClick={open}
          aria-label={`Open ${ASSISTANT_NAME}`}
          aria-haspopup="dialog"
          title={`${ASSISTANT_NAME} (${shortcut})`}
        >
          <ChatMark size={18} />
          <span className="sm-chat-launcher-text">Ask SkyMind</span>
          <kbd className="sm-chat-launcher-kbd">{shortcut}</kbd>
        </button>
      )}

      {isOpen && (
        <section className="sm-chat" role="dialog" aria-labelledby="sm-chat-title" aria-describedby="sm-chat-sub">
          <header className="sm-chat-head">
            <span className="sm-chat-avatar" aria-hidden="true"><PlaneGlyph size={15} /></span>
            <div className="sm-chat-head-text">
              <h2 id="sm-chat-title">{ASSISTANT_NAME}</h2>
              <p id="sm-chat-sub">Fares, forecasts and airlines in India</p>
            </div>
            <div className="sm-chat-head-actions">
              <button type="button" className="sm-chat-icon-btn" onClick={newChat} disabled={messages.length === 0 && !busy} title="New chat" aria-label="Start a new chat">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
              </button>
              <button type="button" className="sm-chat-icon-btn" onClick={close} title="Close (Esc)" aria-label="Close chat">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
              </button>
            </div>
          </header>

          {routeContext && (
            <div className="sm-chat-context">
              {contextOn ? (
                <>
                  <span>
                    Using your search: <b>{routeContext.origin} → {routeContext.destination}</b>
                    {dayLabel ? `, ${dayLabel}` : ""}
                  </span>
                  <button type="button" onClick={() => setContextOn(false)}>Don&apos;t use</button>
                </>
              ) : (
                <>
                  <span>Not using your current search.</span>
                  <button type="button" onClick={() => setContextOn(true)}>Use it</button>
                </>
              )}
            </div>
          )}

          <div className="sm-chat-log" ref={logRef} onScroll={onScroll} role="log" aria-live="polite" aria-relevant="additions">
            {messages.length === 0 ? (
              <div className="sm-chat-empty">
                <div className="sm-chat-empty-mark" aria-hidden="true"><PlaneGlyph size={22} /></div>
                <h3>Where are you flying?</h3>
                <p>
                  Ask about fares on a route, whether to book now or wait, or which airlines fly where.
                  Answers come from the fares SkyMind collects every day.
                </p>
                <div className="sm-chat-label">Try asking</div>
                <div className="sm-chat-suggestions">
                  {suggestions.map(s => (
                    <button key={s} type="button" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map(m => {
                if (m.role === "user") {
                  return (
                    <div key={m.id} className="sm-msg sm-msg-user">
                      <div className="sm-msg-bubble">{m.content}</div>
                    </div>
                  );
                }
                if (m.role === "notice") {
                  return (
                    <div key={m.id} className="sm-msg-notice" role="status">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>
                      <span>{m.content}</span>
                    </div>
                  );
                }
                const waiting = m.status === "streaming" && !m.content;
                return (
                  <div key={m.id} className={`sm-msg sm-msg-bot${m.status === "error" ? " is-error" : ""}`}>
                    <span className="sm-chat-avatar sm-chat-avatar-sm" aria-hidden="true"><PlaneGlyph size={12} /></span>
                    <div className="sm-msg-body">
                      {waiting ? (
                        <div className="sm-typing" aria-label="SkyMind is typing">
                          <span /><span /><span />
                          {slow && <em>Looking up live fares. This can take up to 30 seconds.</em>}
                        </div>
                      ) : (
                        <MarkdownMessage content={m.content} />
                      )}
                      {m.status === "streaming" && m.content && <span className="sm-caret" aria-hidden="true" />}
                      {(m.status === "done" || m.status === "stopped" || m.status === "error") && (
                        <div className="sm-msg-actions">
                          {m.status === "stopped" && <span className="sm-msg-flag">Stopped</span>}
                          {m.status !== "error" && m.content && (
                            <button type="button" onClick={() => copy(m)}>{copiedId === m.id ? "Copied" : "Copy"}</button>
                          )}
                          {(m.status === "error" || m.status === "stopped") && !busy && (
                            <button type="button" onClick={() => retry(m.id)}>Try again</button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {showDateChips && (
              <div className="sm-chat-suggestions sm-chat-quick">
                {["Tomorrow", "This weekend", "Next week"].map(s => (
                  <button key={s} type="button" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}
          </div>

          {!atBottom && messages.length > 0 && (
            <button type="button" className="sm-chat-jump" onClick={() => { setAtBottom(true); scrollToBottom(); }}>
              Jump to latest
            </button>
          )}

          <form className="sm-chat-composer" onSubmit={e => { e.preventDefault(); send(input); }}>
            <div className="sm-chat-inputwrap">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                maxLength={MAX_LEN}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={contextActive ? `Ask about ${routeContext!.origin} → ${routeContext!.destination}…` : "Ask about fares, dates or airlines…"}
                aria-label="Message SkyMind Assistant"
              />
              {busy ? (
                <button type="button" className="sm-chat-send is-stop" onClick={stop} aria-label="Stop answering" title="Stop">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
                </button>
              ) : (
                <button type="submit" className="sm-chat-send" disabled={!input.trim()} aria-label="Send message" title="Send (Enter)">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
                </button>
              )}
            </div>
            <div className="sm-chat-foot">
              <span>Fares change often. Check the price before you book.</span>
              {input.length > MAX_LEN - 200 && <span className="sm-chat-count">{input.length}/{MAX_LEN}</span>}
            </div>
          </form>
        </section>
      )}
    </>
  );
}

function PlaneGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}

function ChatMark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
    </svg>
  );
}

export default function Chatbot() {
  return (
    <Suspense fallback={null}>
      <ChatbotContent />
    </Suspense>
  );
}
