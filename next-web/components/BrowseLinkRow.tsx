import Link from "next/link";

import { ChevronRightIcon } from "@/components/BrowseIcons";

export function BrowseLinkRow({
  href,
  title,
  subtitle,
  compact,
}: {
  href: string;
  title: string;
  subtitle?: string;
  compact?: boolean;
}) {
  return (
    <Link
      className={`browse-link-row group flex items-center gap-3 rounded-2xl border border-default-200/60 bg-white/90 shadow-soft backdrop-blur-md transition-colors hover:border-primary/35 hover:bg-primary/[0.04] active:bg-primary/10 dark:border-slate-600/50 dark:bg-slate-800/80 dark:hover:border-primary/30 ${
        compact
          ? "min-h-12 rounded-xl px-3.5 py-2.5"
          : "min-h-14 rounded-2xl px-4 py-3.5"
      }`}
      href={href}
    >
      <div className="min-w-0 flex-1">
        <h2
          className={`truncate font-semibold text-foreground group-hover:text-primary ${
            compact ? "text-sm" : "text-[15px]"
          }`}
        >
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-0.5 truncate text-xs text-default-400">{subtitle}</p>
        ) : null}
      </div>
      <ChevronRightIcon
        className="shrink-0 text-default-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
        size={compact ? 16 : 18}
      />
    </Link>
  );
}
