import { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ForumShell } from "@/components/ForumShell";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import { ChevronRightIcon } from "@/components/BrowseIcons";
import {
  boardParentBrowseHref,
  findCategory,
  isGroupBoard,
  parentFid,
  type BoardNavParent,
} from "@/config/boards";

export const dynamic = "force-dynamic";

function BoardRow({
  parent,
  subtitle,
}: {
  parent: BoardNavParent;
  subtitle: string;
}) {
  return (
    <Link
      className="group flex min-h-14 items-center gap-3 rounded-2xl border border-default-200/80 bg-content1 px-4 py-3.5 active:bg-primary/10 dark:border-slate-700/80"
      href={boardParentBrowseHref(parent)}
    >
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-[15px] font-semibold text-foreground group-active:text-primary">
          {parent.name}
        </h2>
        <p className="mt-0.5 text-xs text-default-400">{subtitle}</p>
      </div>
      <ChevronRightIcon className="shrink-0 text-default-300" size={18} />
    </Link>
  );
}

export async function generateMetadata({
  params,
}: {
  params: { category: string };
}): Promise<Metadata> {
  const index = Number(params.category);
  const cat = findCategory(index);
  const t = await getTranslations();
  return {
    title: cat ? `${cat.category} · ${t("Boards.title")}` : t("Boards.title"),
  };
}

export default async function CategoryPage({
  params,
}: {
  params: { category: string };
}) {
  const t = await getTranslations();
  const index = Number(params.category);
  const cat = findCategory(index);
  if (!cat) notFound();

  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-3 md:px-4 lg:max-w-7xl">
        <SiteLogoLink />
        <SearchInput />
        <SettingsNavLink />
      </div>
      <ForumShell
        activeCategoryIndex={index}
        crumbs={[{ label: cat.category }]}
      >
        <div className="flex flex-col gap-4">
          <header className="rounded-2xl border border-default-200/70 bg-content1 px-4 py-5 dark:border-slate-700/70">
            <h1 className="text-lg font-semibold text-foreground md:text-xl">
              {cat.category}
            </h1>
            <p className="mt-1 text-xs text-default-500 md:text-sm">
              {t("Boards.category_subtitle", { count: cat.boards.length })}
            </p>
          </header>
          <div className="flex flex-col gap-3">
            {cat.boards.map((parent) => {
              if (isGroupBoard(parent)) {
                const nested = parent.boards || [];
                return (
                  <section key={parent.name} className="flex flex-col gap-2">
                    <Link
                      className="group flex items-center gap-2 px-0.5"
                      href={boardParentBrowseHref(parent)}
                    >
                      <h2 className="text-sm font-semibold text-foreground group-hover:text-primary">
                        {parent.name}
                      </h2>
                      <ChevronRightIcon
                        className="text-default-300 group-hover:text-primary"
                        size={14}
                      />
                    </Link>
                    <div className="flex flex-col gap-2 pl-0 sm:pl-1">
                      {nested.map((n) => {
                        const fid = parentFid(n);
                        return (
                          <BoardRow
                            key={n.name}
                            parent={n}
                            subtitle={
                              fid
                                ? t("Boards.subtype_count", {
                                    count: n.children.length,
                                  })
                                : t("Boards.whole_board")
                            }
                          />
                        );
                      })}
                    </div>
                  </section>
                );
              }

              const fid = parentFid(parent);
              return (
                <BoardRow
                  key={parent.name}
                  parent={parent}
                  subtitle={
                    fid
                      ? t("Boards.subtype_count", {
                          count: parent.children.length,
                        })
                      : t("Boards.whole_board")
                  }
                />
              );
            })}
          </div>
        </div>
      </ForumShell>
      <FloatTool />
    </>
  );
}
