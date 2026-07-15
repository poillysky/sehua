"use client";

import { useEffect } from "react";

/**
 * Marks <html> when launched from iOS Home Screen / installed PWA,
 * so CSS can apply safe-area and fullscreen tweaks.
 */
export function IosStandalone() {
  useEffect(() => {
    const root = document.documentElement;
    const nav = window.navigator as Navigator & { standalone?: boolean };
    const mq = window.matchMedia("(display-mode: standalone)");

    const apply = () => {
      const standalone = Boolean(nav.standalone) || mq.matches;

      root.classList.toggle("ios-standalone", standalone);
      root.dataset.standalone = standalone ? "true" : "false";
    };

    apply();
    mq.addEventListener?.("change", apply);

    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return null;
}
