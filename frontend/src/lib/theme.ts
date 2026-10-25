/** Light / dark / system theme. The choice lives in this browser only; index.html applies it before first paint. */
import { useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "ingather.theme";
const media = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null);

export function storedTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch { return "system"; }
}

export function resolved(theme: Theme): "light" | "dark" {
  return theme === "system" ? (media()?.matches ? "dark" : "light") : theme;
}

export function applyTheme(theme: Theme): void {
  const mode = resolved(theme);
  document.documentElement.dataset.theme = mode;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", mode === "dark" ? "#0f1016" : "#fafafc");
}

/** Current theme, a setter that persists it, and live updates when the system setting changes. */
export function useTheme(): [Theme, (t: Theme) => void, "light" | "dark"] {
  const [theme, setTheme] = useState<Theme>(storedTheme);
  const [, rerender] = useState(0);
  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system") return;
    const m = media();
    const onChange = () => { applyTheme("system"); rerender((n) => n + 1); };
    m?.addEventListener("change", onChange);
    return () => m?.removeEventListener("change", onChange);
  }, [theme]);
  const set = (t: Theme) => {
    try { if (t === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, t); } catch { /* storage unavailable: still applies */ }
    setTheme(t);
  };
  return [theme, set, resolved(theme)];
}
