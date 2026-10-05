"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

export type ThemePreference = Theme | "system";

interface ThemeContextType {
  theme: Theme;
  /** What the person chose: a fixed theme, or follow the system setting. */
  preference: ThemePreference;
  toggleTheme: () => void;
  setPreference: (p: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
const STORAGE_KEY = "skymind-theme";

/**
 * Runs in <head> before the page paints (see app/layout.tsx), so the first
 * frame is already in the right theme instead of flashing light first.
 * A saved choice wins; otherwise the system setting decides.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t)}catch(e){}})();`;

function readSaved(): Theme | null {
  try {
    const t = localStorage.getItem(STORAGE_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  const [preference, setPref] = useState<ThemePreference>("system");

  // Pick up whatever the head script already applied.
  useEffect(() => {
    const applied = document.documentElement.getAttribute("data-theme");
    if (applied === "dark" || applied === "light") setTheme(applied);
    setPref(readSaved() ?? "system");
  }, []);

  // Until the person picks a theme themselves, follow the system setting as
  // it changes (e.g. the OS switching to dark in the evening).
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => {
      if (readSaved()) return;
      const next: Theme = e.matches ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      setTheme(next);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggleTheme = () => {
    setTheme(prev => {
      const next: Theme = prev === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem(STORAGE_KEY, next); } catch { /* private mode */ }
      setPref(next);
      return next;
    });
  };

  const setPreference = (p: ThemePreference) => {
    const next: Theme = p === "system"
      ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : p;
    try {
      if (p === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, p);
    } catch { /* private mode */ }
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
    setPref(p);
  };

  return (
    <ThemeContext.Provider value={{ theme, preference, toggleTheme, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
