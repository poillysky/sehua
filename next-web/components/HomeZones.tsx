import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { BOARD_NAV, categoryHref } from "@/config/boards";

export async function HomeZones() {
  const t = await getTranslations();

  return (
    <section className="home-zones relative z-[1] mt-6 flex flex-col gap-3 md:mt-8 md:gap-4">
      <div className="grid grid-cols-1 gap-3 md:gap-4">
        {BOARD_NAV.map((cat, index) => (
          <Link
            key={cat.category}
            className="home-zone-card group relative flex min-h-[5.25rem] items-center gap-4 overflow-hidden rounded-2xl border border-default-200/70 bg-content1/90 px-4 py-4 transition-colors hover:border-primary/40 hover:bg-primary/[0.04] dark:border-slate-700/70 dark:bg-slate-900/55 dark:hover:border-primary/35 md:px-5 md:py-5"
            href={categoryHref(index)}
          >
            <span
              aria-hidden
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-sm font-bold tabular-nums text-primary dark:bg-primary/20"
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="text-[1.05rem] font-semibold text-foreground group-hover:text-primary md:text-lg">
                {cat.category}
              </h3>
              <p className="mt-0.5 text-xs text-default-500 md:text-sm">
                {t("Boards.category_subtitle", { count: cat.boards.length })}
              </p>
            </div>
            <ChevronRightIcon
              className="shrink-0 text-default-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
              size={18}
            />
          </Link>
        ))}
      </div>
    </section>
  );
}
