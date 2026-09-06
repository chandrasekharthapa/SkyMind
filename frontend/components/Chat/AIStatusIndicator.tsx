"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, Sparkles, Database, ShieldCheck } from "lucide-react";

export type AIStage =
  | "understanding"
  | "planning"
  | "searching"
  | "verifying"
  | "generating"
  | "complete";

interface AIStatusIndicatorProps {
  stage: AIStage;
  isVisible: boolean;
}

const STAGE_CONFIG: Record<AIStage, { label: string; icon: React.ElementType }> = {
  understanding: { label: "Understanding your request...", icon: Sparkles },
  planning: { label: "Planning search strategy...", icon: Loader2 },
  searching: { label: "Querying live flight feeds...", icon: Database },
  verifying: { label: "Verifying fare integrity...", icon: ShieldCheck },
  generating: { label: "Preparing response...", icon: Loader2 },
  complete: { label: "Response ready", icon: CheckCircle2 },
};

export const AIStatusIndicator: React.FC<AIStatusIndicatorProps> = ({ stage, isVisible }) => {
  if (!isVisible || stage === "complete") return null;

  const config = STAGE_CONFIG[stage] || STAGE_CONFIG.understanding;
  const IconComponent = config.icon;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.2 }}
        className="ai-status-indicator"
        role="log"
        aria-live="polite"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 12px",
          margin: "4px 0",
          background: "rgba(220, 38, 38, 0.04)",
          border: "1px solid rgba(220, 38, 38, 0.12)",
          borderRadius: "16px",
          fontSize: "0.78rem",
          color: "var(--red, #dc2626)",
          fontWeight: 500,
          width: "fit-content"
        }}
      >
        <IconComponent className="animate-spin" size={14} style={{ animationDuration: "1.5s" }} />
        <span>{config.label}</span>
      </motion.div>
    </AnimatePresence>
  );
};
