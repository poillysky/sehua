"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import { PrevIcon } from "@/components/icons";
import { resolveSectionParentHref } from "@/config/boards";

export const DETAIL_RETURN_URL_KEY = "ed2k-detail-return-url";

/** BrowsePageContent 挂载时设置，仅资源流 sticky 底栏页隐藏全局返回 */
export const HIDE_GLOBAL_BACK_ATTR = "data-hide-global-back";

export function saveDetailReturnUrl() {
  if (typeof window === "undefined") {
    return;
  }

  sessionStorage.setItem(
    DETAIL_RETURN_URL_KEY,
    `${window.location.pathname}${window.location.search}`,
  );
}

/** 当前会话内是否还能浏览器后退（Next App Router 会写 history.state.idx） */
function canUseHistoryBack(): boolean {
  if (typeof window === "undefined") return false;
  const state = window.history.state as { idx?: number } | null;
  if (typeof state?.idx === "number") {
    return state.idx > 0;
  }
  try {
    if (document.referrer) {
      return new URL(document.referrer).origin === window.location.origin;
    }
  } catch {
    /* ignore */
  }
  return false;
}

/**
 * 优先浏览器历史后退；无历史时：
 * - 详情 → sessionStorage 列表页 → 首页
 * - 其它 → 分区父级路径
 */
export function goBackOrHome(
  router: ReturnType<typeof useRouter>,
  pathname?: string,
) {
  const path =
    pathname ||
    (typeof window !== "undefined" ? window.location.pathname : "/");

  if (canUseHistoryBack()) {
    router.back();
    return;
  }

  if (path.startsWith("/detail")) {
    if (typeof window !== "undefined") {
      const returnUrl = sessionStorage.getItem(DETAIL_RETURN_URL_KEY);
      const current = `${window.location.pathname}${window.location.search}`;
      if (returnUrl && returnUrl !== current) {
        router.push(returnUrl);
        return;
      }
    }
    router.push("/");
    return;
  }

  router.push(resolveSectionParentHref(path));
}

/** 页面内联返回（详情等） */
export function DetailBackButton() {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations();

  return (
    <button
      type="button"
      className="inline-flex w-fit items-center gap-1.5 rounded-full bg-default-100/80 px-3 py-1.5 text-sm text-default-700 transition-colors hover:bg-default-200/80 dark:bg-slate-800/80 dark:text-slate-200 dark:hover:bg-slate-700"
      onClick={() => goBackOrHome(router, pathname || undefined)}
    >
      <PrevIcon size={14} />
      {t("Detail.back")}
    </button>
  );
}

/** 全局悬浮后退：除首页外默认展示；资源流 sticky 分页页由 BrowsePageContent 声明隐藏 */
export function GlobalBackButton() {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations();
  const [hideForSticky, setHideForSticky] = useState(false);

  useEffect(() => {
    const sync = () => {
      setHideForSticky(
        document.documentElement.getAttribute(HIDE_GLOBAL_BACK_ATTR) === "1",
      );
    };
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [HIDE_GLOBAL_BACK_ATTR],
    });
    return () => mo.disconnect();
  }, [pathname]);

  if (!pathname || pathname === "/") {
    return null;
  }

  if (hideForSticky) {
    return null;
  }

  return (
    <button
      type="button"
      aria-label={t("Nav.back")}
      title={t("Nav.back")}
      className={clsx(
        "safe-fixed-fab-back fixed z-30 flex h-11 w-11 items-center justify-center overflow-hidden rounded-full",
        /* 勿用 backdrop-blur / ring-inset：iOS 易出黑色发丝线 */
        "bg-white text-default-700 shadow-[0_2px_10px_rgba(15,23,42,0.1)]",
        "transition-[color,box-shadow,background-color] hover:bg-white hover:text-primary hover:shadow-[0_4px_14px_rgba(15,23,42,0.14)]",
        "dark:bg-slate-800 dark:text-slate-200 dark:shadow-[0_2px_10px_rgba(0,0,0,0.45)]",
        "focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_rgba(44,133,255,0.28)]",
        "[-webkit-tap-highlight-color:transparent]",
      )}
      onClick={() => goBackOrHome(router, pathname)}
    >
      <PrevIcon className="relative -ml-0.5" size={18} />
    </button>
  );
}
