"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";

import { CHROME_DARK, CHROME_LIGHT } from "@/config/chrome";

function resolveScheme(
  theme: string | undefined,
): "light" | "dark" {
  if (theme === "dark") return "dark";
  if (theme === "light") return "light";
  if (typeof window !== "undefined") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  return "light";
}

function syncThemeColor(scheme: "light" | "dark") {
  const color = scheme === "dark" ? CHROME_DARK : CHROME_LIGHT;
  const metas = document.querySelectorAll('meta[name="theme-color"]');

  if (!metas.length) {
    const meta = document.createElement("meta");

    meta.setAttribute("name", "theme-color");
    meta.setAttribute("content", color);
    document.head.appendChild(meta);

    return;
  }

  metas.forEach((meta) => {
    meta.setAttribute("content", color);
    meta.removeAttribute("media");
  });
}

/**
 * Marks <html> for Home Screen / PWA, syncs theme-color, and
 * exposes data-chrome-scheme for CSS (status-bar backdrop, body tint).
 */
export function IosStandalone() {
  const { theme, resolvedTheme } = useTheme();

  useEffect(() => {
    const root = document.documentElement;
    const nav = window.navigator as Navigator & { standalone?: boolean };
    const mq = window.matchMedia("(display-mode: standalone)");

    const applyStandalone = () => {
      const standalone = Boolean(nav.standalone) || mq.matches;

      root.classList.toggle("ios-standalone", standalone);
      root.dataset.standalone = standalone ? "true" : "false";
    };

    applyStandalone();
    mq.addEventListener?.("change", applyStandalone);

    return () => mq.removeEventListener?.("change", applyStandalone);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const scheme = resolveScheme(resolvedTheme || theme);

    root.dataset.chromeScheme = scheme;
    root.classList.toggle("chrome-light", scheme === "light");
    root.classList.toggle("chrome-dark", scheme === "dark");
    syncThemeColor(scheme);

    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = () => {
        const next = mq.matches ? "dark" : "light";

        root.dataset.chromeScheme = next;
        root.classList.toggle("chrome-light", next === "light");
        root.classList.toggle("chrome-dark", next === "dark");
        syncThemeColor(next);
      };

      mq.addEventListener?.("change", onChange);

      return () => mq.removeEventListener?.("change", onChange);
    }
  }, [theme, resolvedTheme]);

  return (
    <div
      aria-hidden
      className="ios-status-backdrop"
    />
  );
}
