"use client";

import React, { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { X, Send, RotateCcw, Sparkles, Plane } from "lucide-react";
import { getApiBase } from "@/lib/api";
import { AIStatusIndicator, AIStage } from "./AIStatusIndicator";
import { ClarificationUI } from "./ClarificationUI";
import {
  TypingMessage,
  MarkdownMessage,
} from "./MessageComponents";

type Role = "user" | "assistant" | "system";

interface Message {
  role: Role;
  content: string;
  timestamp?: string;
}

const SUGGESTION_CHIPS = [
  "Should I book now?",
  "Compare fares",
  "Find cheaper dates",
  "Explain forecast",
  "Best airline"
];

function ChatbotContent() {
  const searchParams = useSearchParams();
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [aiStage, setAiStage] = useState<AIStage>("understanding");
  const [isAiStatusVisible, setIsAiStatusVisible] = useState(false);
  const [hasError, setHasError] = useState<boolean>(false);
  const [systemMessage, setSystemMessage] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Automatic Context Integration (Behind the scenes)
  const originParam = searchParams ? searchParams.get("origin") : null;
  const destParam = searchParams ? searchParams.get("destination") : null;
  const dateParam = searchParams ? searchParams.get("departure_date") : null;
  const cabinParam = searchParams ? searchParams.get("cabin_class") ?? "Economy" : "Economy";
  const adultsParam = searchParams ? searchParams.get("adults") ?? "1" : "1";
  const hasRouteContext = Boolean(originParam && destParam);

  // Session Recovery & Persistence
  useEffect(() => {
    let storedSession = localStorage.getItem("skymind_session_id");
    if (!storedSession) {
      storedSession = "sess_" + Math.random().toString(36).substring(2, 11);
      localStorage.setItem("skymind_session_id", storedSession);
    }
    setSessionId(storedSession);

    const savedChat = localStorage.getItem(`skymind_chat_${storedSession}`);
    if (savedChat) {
      try {
        setMessages(JSON.parse(savedChat));
      } catch (e) {
        console.error("Failed to parse saved chat session:", e);
      }
    }
  }, []);

  useEffect(() => {
    if (sessionId && messages.length > 0) {
      localStorage.setItem(`skymind_chat_${sessionId}`, JSON.stringify(messages));
    }
  }, [messages, sessionId]);

  // Keyboard Shortcuts (ESC closes, Cmd+K toggles)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Click Outside Listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (isOpen && panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const handleNewConversation = () => {
    const newSession = "sess_" + Math.random().toString(36).substring(2, 11);
    localStorage.setItem("skymind_session_id", newSession);
    localStorage.removeItem(`skymind_chat_${sessionId}`);
    setSessionId(newSession);
    setHasError(false);
    setMessages([]);
    setSystemMessage("");
    setInputValue("");
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, isLoading]);

  const handleSubmit = async (e?: React.FormEvent, customInput?: string) => {
    if (e) e.preventDefault();
    const queryText = customInput || inputValue;
    if (!queryText.trim() || isLoading) return;

    const userMessage: Message = {
      role: "user",
      content: queryText.trim()
    };
    const newMessages = [...messages, userMessage];

    setMessages(newMessages);
    if (!customInput) setInputValue("");
    setIsLoading(true);
    setHasError(false);
    setSystemMessage("");

    setIsAiStatusVisible(true);
    setAiStage("understanding");

    try {
      setAiStage("planning");
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          session_id: sessionId,
          route_context: hasRouteContext ? { origin: originParam, destination: destParam, departure_date: dateParam, cabin_class: cabinParam, adults: adultsParam } : null
        }),
      });

      setAiStage("searching");

      if (!response.ok) {
        setHasError(true);
        const text = await response.text();
        if (text && text.includes("SkyMind")) {
          setSystemMessage(text.trim());
        } else {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        setIsAiStatusVisible(false);
        return;
      }

      if (!response.body) {
        setHasError(true);
        throw new Error("No response body");
      }

      setAiStage("verifying");
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      setAiStage("generating");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });

        if (chunk && chunk.includes("SkyMind")) {
          setSystemMessage(chunk.trim());
          setMessages((prev) => prev.slice(0, -1));
          setIsAiStatusVisible(false);
          return;
        }
        setMessages((prev) => {
          const updated = [...prev];
          const lastIndex = updated.length - 1;
          const lastMsg = updated[lastIndex];
          if (lastMsg && lastMsg.role === "assistant") {
            updated[lastIndex] = {
              ...lastMsg,
              content: lastMsg.content + chunk,
            };
          }
          return updated;
        });
      }
    } catch (error) {
      console.error("Chat error:", error);
      setHasError(true);
      setMessages((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (updated[lastIndex]?.role === "assistant" && !updated[lastIndex]?.content) {
          updated[lastIndex] = {
            role: "assistant",
            content: "Sorry, I encountered an error processing your query. Please try again."
          };
        } else {
          updated.push({
            role: "assistant",
            content: "Sorry, I encountered an error processing your query. Please try again."
          });
        }
        return updated;
      });
    } finally {
      setIsLoading(false);
      setAiStage("complete");
      setIsAiStatusVisible(false);
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          aria-label="Open SkyMind Copilot"
          title="Open SkyMind Copilot (Ctrl+K)"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            zIndex: 9999,
            height: 48,
            padding: "0 20px",
            borderRadius: 12,
            background: "#111",
            color: "#fff",
            border: "1px solid rgba(255,255,255,0.12)",
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.16)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: 500
          }}
        >
          <Sparkles size={16} color="#E11D48" />
          <span>SkyMind Copilot</span>
          <span style={{ fontSize: "10px", color: "#888", background: "rgba(255,255,255,0.1)", padding: "2px 6px", borderRadius: 4 }}>Ctrl+K</span>
        </button>
      )}

      {/* SkyMind Copilot Assistant Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-label="SkyMind Copilot"
        style={{
          position: "fixed",
          bottom: isOpen ? 24 : -800,
          right: isOpen ? 24 : 24,
          width: "clamp(360px, 90vw, 500px)",
          height: "min(80vh, 720px)",
          background: "#FFFFFF",
          border: "1px solid #ECECEC",
          borderRadius: 16,
          boxShadow: "0 20px 48px rgba(0, 0, 0, 0.12)",
          zIndex: 10000,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? "auto" : "none",
          transition: "transform 180ms ease-out, opacity 180ms ease-out"
        }}
      >
        {/* Compact Header */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #ECECEC", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#fff" }}>
          <div style={{ fontSize: "18px", fontWeight: 600, color: "#111", letterSpacing: "-0.01em" }}>SkyMind Copilot</div>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={handleNewConversation}
              title="New Chat"
              aria-label="New Chat"
              style={{ width: 32, height: 32, borderRadius: 6, border: "none", background: "transparent", color: "#666", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <RotateCcw size={16} />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              title="Close (Esc)"
              aria-label="Close Copilot"
              style={{ width: 32, height: 32, borderRadius: 6, border: "none", background: "transparent", color: "#666", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Conversation Area */}
        <div
          role="log"
          aria-live="polite"
          style={{
            flex: 1,
            overflowY: messages.length > 0 ? "auto" : "hidden",
            scrollbarWidth: "thin",
            padding: messages.length > 0 ? "20px" : "0 20px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            justifyContent: messages.length === 0 ? "center" : "flex-start"
          }}
        >
          {systemMessage && (
            <div style={{ background: "rgba(224,49,49,0.05)", border: "1px solid rgba(224,49,49,0.15)", borderRadius: 8, padding: "10px 14px", fontSize: "12px", color: "#DC2626" }}>
              {systemMessage}
            </div>
          )}

          {/* Empty State Landing Experience */}
          {messages.length === 0 && (
            <div style={{ margin: "auto 0" }}>
              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: "20px", fontWeight: 600, color: "#111", marginBottom: 6 }}>SkyMind Copilot</div>
                <div style={{ fontSize: "14px", fontWeight: 500, color: "#444", marginBottom: 8 }}>Ask me about</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: "14px", color: "#666", lineHeight: 1.6 }}>
                  <li>Flight prices</li>
                  <li>Booking recommendations</li>
                  <li>Fare forecasts</li>
                  <li>Airlines</li>
                  <li>Airports</li>
                  <li>Travel planning</li>
                </ul>
              </div>

              {/* Suggestion Chips (Disappear after first message) */}
              <div>
                <div style={{ fontSize: "11px", fontWeight: 500, color: "#888", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 8 }}>SUGGESTED PROMPTS</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {SUGGESTION_CHIPS.map((chip, i) => (
                    <button
                      key={i}
                      onClick={() => handleSubmit(undefined, chip)}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 8,
                        background: "#FAFAFA",
                        border: "1px solid #ECECEC",
                        fontSize: "13px",
                        color: "#333",
                        cursor: "pointer",
                        fontWeight: 400,
                        transition: "background-color 0.15s, border-color 0.15s"
                      }}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Active Messages Stream */}
          {messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                gap: 4
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "82%",
                  flexDirection: msg.role === "user" ? "row-reverse" : "row"
                }}
              >
                {/* AI Identity Avatar */}
                {msg.role === "assistant" && (
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      background: "#FAFAFA",
                      border: "1px solid #ECECEC",
                      color: "#E11D48",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0
                    }}
                  >
                    <Plane size={14} />
                  </div>
                )}

                {/* Message Bubble */}
                <div
                  style={{
                    background: msg.role === "user" ? "rgba(225, 29, 72, 0.04)" : "#F9F9F9",
                    border: msg.role === "user" ? "1px solid rgba(225, 29, 72, 0.15)" : "1px solid #ECECEC",
                    borderRadius: 12,
                    padding: "14px 18px",
                    fontSize: "15px",
                    lineHeight: 1.6,
                    color: "#111",
                    fontWeight: 400
                  }}
                >
                  <MarkdownMessage content={msg.content} />
                  {/* An EvidenceDrawer used to be rendered under every
                      assistant message containing a "₹", asserting "Verified
                      Flight Intelligence", 95% confidence, "Just now", and the
                      sources ["Google Flights Stream", "SkyMind XGBoost
                      Inference"]. None of that came from the backend — the chat
                      API returns no provenance at all, and the trigger was a
                      currency symbol appearing in the text. Rendering a
                      verification panel for an unverified answer is worse than
                      rendering none, so it is gone until the backend returns
                      real citations, at which point pass them through. */}
                </div>
              </div>
            </div>
          ))}

          <AIStatusIndicator stage={aiStage} isVisible={isAiStatusVisible} />

          {messages.length > 0 &&
            !isLoading &&
            !hasError &&
            messages[messages.length - 1]?.role === "assistant" &&
            !messages[messages.length - 1]?.content.toLowerCase().includes("error") && (
              <ClarificationUI onSelect={(val) => handleSubmit(undefined, val)} type="date" />
            )}

          {isLoading && !isAiStatusVisible && <TypingMessage />}
          <div ref={messagesEndRef} />
        </div>

        {/* Compact Pinned Input */}
        <form onSubmit={handleSubmit} style={{ padding: "14px 16px", borderTop: "1px solid #ECECEC", background: "#fff", display: "flex", gap: 10, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Ask anything about flights..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={isLoading}
            style={{
              flex: 1,
              height: 48,
              padding: "0 16px",
              borderRadius: 12,
              border: "1px solid #ECECEC",
              fontSize: "15px",
              color: "#111",
              fontWeight: 400,
              outline: "none"
            }}
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isLoading}
            aria-label="Send Message"
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: inputValue.trim() && !isLoading ? "#E11D48" : "#F0F0F0",
              color: inputValue.trim() && !isLoading ? "#fff" : "#aaa",
              border: "none",
              cursor: inputValue.trim() && !isLoading ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "background-color 0.2s"
            }}
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </>
  );
}

export default function Chatbot() {
  return (
    <Suspense fallback={null}>
      <ChatbotContent />
    </Suspense>
  );
}
