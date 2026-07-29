"use client";

import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import { PrevIcon } from "@/components/icons";
import { resolveSectionParentHref } from "@/config/boards";

export const DETAIL_RETURN_URL_KEY = "ed2k-detail-return-url";

export function saveDetailReturnUrl() {
  if (typeof window === "undefined") {
    return;
  }

  sessionStorage.setItem(
    DETAIL_RETURN_URL_KEY,
    `${window.location.pathname}${window.location.search}`,
  );
}

/** 分区层级后退；详情优先回到进入前的列表页 */
export function goBackOrHome(
  router: ReturnType<typeof useRouter>,
  pathname?: string,
) {
  const path =
    pathname ||
    (typeof window !== "undefined" ? window.location.pathname : "/");

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

/** 全局悬浮后退：除首页外默认展示；按分区层级上溯 */
export function GlobalBackButton() {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations();

  if (!pathname || pathname === "/") {
    return null;
  }

  return (
    <button
      type="button"
      aria-label={t("Nav.back")}
      title={t("Nav.back")}
      className={clsx(
        "safe-fixed-fab-back fixed z-30 flex h-11 w-11 items-center justify-center rounded-full",
        "border border-default-200/80 bg-content1/95 text-default-700 shadow-md backdrop-blur-md",
        "transition-colors hover:border-primary/35 hover:text-primary",
        "dark:border-slate-700/80 dark:bg-slate-900/90 dark:text-slate-200",
      )}
      onClick={() => goBackOrHome(router, pathname)}
    >
      <PrevIcon size={18} />
    </button>
  );
}
