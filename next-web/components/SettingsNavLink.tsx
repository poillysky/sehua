import NextLink from "next/link";
import clsx from "clsx";

import { IconSvgProps } from "@/types";

function Cloud115Icon({ size = 16, ...props }: IconSvgProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.75"
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      <path d="M7.5 18a4.5 4.5 0 0 1-.9-8.91A6 6 0 0 1 18.7 10.2 3.8 3.8 0 0 1 19.5 18H7.5z" />
      <path d="M12 13v5" />
      <path d="m9.5 16.5 2.5 2.5 2.5-2.5" />
    </svg>
  );
}

/**
 * 115 设置入口
 * - noBg：首页右上角，与主题/语言按钮对齐
 * - 默认：搜索/浏览顶栏，紧凑芯片
 */
export function SettingsNavLink({ noBg = false }: { noBg?: boolean }) {
  return (
    <NextLink
      aria-label="115 网盘设置"
      className={clsx(
        "group inline-flex shrink-0 items-center justify-center gap-1 rounded-medium font-semibold transition-all",
        "text-stone-600 hover:text-primary dark:text-slate-300 dark:hover:text-primary",
        noBg
          ? "h-8 min-w-8 px-2 text-[11px] hover:bg-default-100/80 dark:hover:bg-slate-800/80"
          : "ml-2 h-9 px-2.5 text-xs border border-default-200/90 bg-gray-50/90 shadow-sm hover:border-primary/40 hover:bg-primary/5 md:ml-3 dark:border-slate-700 dark:bg-slate-800/80 dark:hover:bg-primary/10",
      )}
      href="/settings"
      title="115 网盘设置"
    >
      <Cloud115Icon
        className="shrink-0 opacity-80 transition-opacity group-hover:opacity-100"
        size={noBg ? 15 : 14}
      />
      <span className="leading-none tracking-wide">115</span>
    </NextLink>
  );
}
