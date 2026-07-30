import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { BOARD_NAV, categoryHref } from "@/config/boards";
import { isZoneCustomCategory } from "@/lib/zoneFolderModel";
import { readZoneFolders } from "@/lib/zoneFolders";

const ZONE_MARKS = ["片", "综", "影", "区", "栏"] as const;

export async function HomeZones() {
  const t = await getTranslations();
  const zoneStore = await readZoneFolders();
  const zoneFolderCount = zoneStore.folders.length;

  return (
    <section className="home-zones relative z-[1] flex min-h-0 w-full flex-col">
      <div className="home-zones__head shrink-0">
        <h2 className="home-zones__title">{t("Home.browse_boards")}</h2>
      </div>
      <div className="home-zones__panel flex min-h-0 flex-1 flex-col overflow-hidden">
        {BOARD_NAV.map((cat, index) => {
          const isZone = isZoneCustomCategory(cat.category);
          const previewShort = isZone
            ? ""
            : cat.boards
                .slice(0, 2)
                .map((b) => b.name)
                .join(" · ");
          const previewFull = isZone
            ? ""
            : cat.boards
                .slice(0, 4)
                .map((b) => b.name)
                .join(" · ");
          const mark = ZONE_MARKS[index] || String(index + 1);
          const countLabel = isZone
            ? t("Boards.zone_folder_count", { count: zoneFolderCount })
            : t("Boards.category_subtitle", { count: cat.boards.length });

          return (
            <Link
              key={cat.category}
              className="home-zone-row group relative flex min-h-0 flex-1 items-center gap-3.5 transition-[background-color,transform] duration-300 active:bg-black/[0.03] dark:active:bg-white/[0.04] md:gap-5"
              data-zone={index}
              href={categoryHref(index)}
              style={{ animationDelay: `${0.06 + index * 0.06}s` }}
            >
              <span aria-hidden className="home-zone-row__rail" />
              <span
                aria-hidden
                className="home-zone-row__mark shrink-0 font-semibold leading-none tracking-wide"
              >
                {mark}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="home-zone-row__name font-semibold tracking-wide text-foreground transition-colors duration-300 group-hover:text-[var(--zone-accent)] group-active:text-[var(--zone-accent)]">
                  {cat.category}
                </h3>
                <p className="home-zone-row__meta mt-1 truncate text-default-500">
                  <span className="text-default-400">{countLabel}</span>
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
                  {isZone ? (
                    <span className="home-zone-row__preview-md">
                      <span className="mx-1.5 text-default-300">·</span>
                      <span>{t("Boards.zone_mode_hint")}</span>
                    </span>
                  ) : null}
                </p>
              </div>
              <ChevronRightIcon
                className="home-zone-row__chevron shrink-0 text-default-300 transition-transform duration-300 group-hover:translate-x-1 group-hover:text-[var(--zone-accent)] group-active:translate-x-1 group-active:text-[var(--zone-accent)]"
                size={18}
              />
            </Link>
          );
        })}
      </div>
    </section>
  );
}
