import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { BOARD_NAV, categoryHref } from "@/config/boards";

export async function HomeZones() {
  const t = await getTranslations();

  return (
    <section className="home-zones relative z-[1] flex min-h-0 w-full flex-col">
      <div className="home-zones__panel flex min-h-0 flex-1 flex-col overflow-hidden">
        {BOARD_NAV.map((cat, index) => {
          const previewShort = cat.boards
            .slice(0, 2)
            .map((b) => b.name)
            .join(" · ");
          const previewFull = cat.boards
            .slice(0, 4)
            .map((b) => b.name)
            .join(" · ");

          return (
            <Link
              key={cat.category}
              className="home-zone-row group relative flex min-h-0 flex-1 items-center gap-3 transition-colors active:bg-primary/10 md:gap-5"
              href={categoryHref(index)}
              style={{ animationDelay: `${0.08 + index * 0.05}s` }}
            >
              <span
                aria-hidden
                className="home-zone-row__index shrink-0 tabular-nums font-light leading-none tracking-tight text-primary/55 transition-colors group-hover:text-primary group-active:text-primary"
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold tracking-wide text-foreground transition-colors group-hover:text-primary group-active:text-primary">
                  {cat.category}
                </h3>
                <p className="home-zone-row__meta mt-0.5 truncate text-default-500">
                  <span className="text-default-400">
                    {t("Boards.category_subtitle", {
                      count: cat.boards.length,
                    })}
                  </span>
                  {previewShort ? (
                    <span className="home-zone-row__preview-sm">
                      <span className="mx-1.5 text-default-300">·</span>
                      <span>{previewShort}</span>
                    </span>
                  ) : null}
                  {previewFull ? (
                    <span className="home-zone-row__preview-md">
                      <span className="mx-1.5 text-default-300">·</span>
                      <span>{previewFull}</span>
                    </span>
                  ) : null}
                </p>
              </div>
              <ChevronRightIcon
                className="shrink-0 text-default-300 transition-transform duration-300 group-hover:translate-x-1 group-hover:text-primary group-active:translate-x-1 group-active:text-primary"
                size={18}
              />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
