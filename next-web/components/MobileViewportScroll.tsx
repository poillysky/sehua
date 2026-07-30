"use client";

import { useEffect } from "react";
import clsx from "clsx";

const LOCK_CLASS = "prefix-mobile-scroll-lock";

/**
 * 手机前缀/女优页壳：铺满可视区（inset-0），上搜索 / 中封面 / 下翻页。
 * 勿用单独 100dvh 高度：在 iOS 上易把顶栏顶出可视区。
 * 桌面 md:contents 透传。
 */
export function MobileViewportScroll({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  useEffect(() => {
    const root = document.documentElement;
    const mq = window.matchMedia("(max-width: 767px)");
    const sync = () => {
      if (mq.matches) root.classList.add(LOCK_CLASS);
      else root.classList.remove(LOCK_CLASS);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => {
      mq.removeEventListener("change", sync);
      root.classList.remove(LOCK_CLASS);
    };
  }, []);

  return (
    <div
      className={clsx(
        "prefix-mobile-shell",
        "max-md:fixed max-md:inset-0 max-md:z-20",
        "max-md:flex max-md:flex-col max-md:overflow-hidden max-md:bg-background",
        "md:contents",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 手机壳内顶栏：搜索等，保证不被下面 flex 子项挤出视口 */
export function MobileShellHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "relative z-30 w-full shrink-0 bg-background",
        "max-md:border-b max-md:border-default-200/60 dark:max-md:border-slate-800",
        className,
      )}
    >
      {children}
    </div>
  );
}
