"use client";

import { useEffect } from "react";
import clsx from "clsx";

const LOCK_CLASS = "prefix-mobile-scroll-lock";

/**
 * 手机前缀/女优页壳：铺满可视区（inset-0），上顶栏 / 中封面 / 下翻页。
 * 勿用单独 100dvh 高度：在 iOS 上易把顶栏顶出可视区。
 * 桌面 md:contents 透传。
 *
 * 番号浏览：直接放 ForumShell(fillMobile)，勿再叠 PageSearchHeader。
 * 女优：MobileShellHeader + PageSearchHeader(crumbs)。
 * enabled 只改 class，根节点稳定，避免浏览壳随路由重挂闪烁。
 */
export function MobileViewportScroll({
  children,
  className,
  enabled = true,
}: {
  children: React.ReactNode;
  className?: string;
  enabled?: boolean;
}) {
  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled]);

  return (
    <div
      className={clsx(
        enabled
          ? [
              "prefix-mobile-shell",
              "max-md:fixed max-md:inset-0 max-md:z-20",
              "max-md:flex max-md:flex-col max-md:overflow-hidden",
              "max-md:bg-[color:var(--chrome-light)] dark:max-md:bg-[color:var(--chrome-dark)]",
              "md:contents",
            ]
          : "contents",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 手机壳内顶栏包装：shrink-0，避免被 flex 子项挤出 */
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
        "relative z-30 w-full shrink-0",
        "max-md:sticky max-md:top-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
