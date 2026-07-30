import NextLink from "next/link";
import clsx from "clsx";

import { SettingsFilledIcon } from "@/components/icons";

/**
 * 设置入口（115 / 刮削后端等）
 * - noBg：首页右上角，与主题/语言按钮对齐（仅图标）
 * - 默认：搜索/浏览顶栏，紧凑芯片
 */
export function SettingsNavLink({ noBg = false }: { noBg?: boolean }) {
  return (
    <NextLink
      aria-label="设置"
      className={clsx(
        "group inline-flex shrink-0 items-center justify-center rounded-medium transition-all",
        "text-default-600 hover:text-primary dark:text-slate-300 dark:hover:text-primary",
        noBg
          ? "h-11 w-11 hover:bg-white/70 dark:hover:bg-slate-800/80 md:h-8 md:w-8"
          : "ml-1 h-9 w-9 shrink-0 border border-default-200/70 bg-white/90 shadow-soft hover:border-primary/40 hover:bg-primary/5 md:ml-3 dark:border-slate-600 dark:bg-slate-800/80 dark:hover:bg-primary/10",
      )}
      href="/settings"
      title="设置"
    >
      <SettingsFilledIcon
        className="block shrink-0 opacity-90 transition-opacity group-hover:opacity-100"
        size={noBg ? 24 : 20}
      />
    </NextLink>
  );
}
