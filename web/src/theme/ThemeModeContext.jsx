// Light/dark mode — defaults to the OS preference (prefers-color-scheme),
// overridable via the header toggle, persisted per browser. Sets the
// `data-theme` attribute that web/src/index.css's custom properties key off
// of (see :root[data-theme="dark"] / [data-theme="light"] overrides there).
import { createContext, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "seerr-dashboard:theme-mode";

function systemPrefersDark() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function readStored() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // fall through to system preference
  }
  return systemPrefersDark() ? "dark" : "light";
}

const ThemeModeContext = createContext(null);

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = useState(readStored);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", mode);
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // best-effort persistence only
    }
  }, [mode]);

  const toggle = () => setMode((m) => (m === "dark" ? "light" : "dark"));

  return <ThemeModeContext.Provider value={{ mode, toggle }}>{children}</ThemeModeContext.Provider>;
}

export function useThemeMode() {
  const ctx = useContext(ThemeModeContext);
  if (!ctx) throw new Error("useThemeMode must be used within a ThemeModeProvider");
  return ctx;
}
