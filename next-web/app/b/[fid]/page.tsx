import { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ForumShell } from "@/components/ForumShell";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import { ChevronRightIcon } from "@/components/BrowseIcons";
import {
  boardBrowseHref,
  boardParentBrowseHref,
  categoryHref,
  findByFid,
  isGroupBoard,
  legacyFidRedirect,
  parentFid,
  type BoardNavChild,
} from "@/config/boards";
import { makerDescription, prefixNote } from "@/config/av-makers";

export const dynamic = "force-dynamic";

function groupByMaker(children: BoardNavChild[]): { maker: string; items: BoardNavChild[] }[] {
  const map = new Map<string, BoardNavChild[]>();
  for (const ch of children) {
    const maker = (ch.board_name || "").trim() || "其他";
    const list = map.get(maker) || [];
    list.push(ch);
    map.set(maker, list);
  }
  return Array.from(map.entries()).map(([maker, items]) => ({ maker, items }));
}

export async function generateMetadata({
  params,
}: {
  params: { fid: string };
}): Promise<Metadata> {
  const ctx = findByFid(decodeURIComponent(params.fid));
  const t = await getTranslations();
  return {
    title: ctx
      ? `${ctx.parent.name} · ${t("Boards.title")}`
      : t("Boards.title"),
  };
}

export default async function BoardPage({
  params,
}: {
  params: { fid: string };
}) {
  const t = await getTranslations();
  const fid = decodeURIComponent(params.fid);
  const legacy = legacyFidRedirect(fid);
  if (legacy) redirect(legacy);
  const ctx = findByFid(fid);
  if (!ctx) notFound();

  const { category, categoryIndex, parent, group } = ctx;
  const nested = parent.boards || [];
  const isHub = isGroupBoard(parent);

  const useMakerGroups =
    !isHub &&
    parent.children.some((c) => Boolean(c.search_keyword)) &&
    new Set(parent.children.map((c) => c.board_name)).size > 1;
  const groups = useMakerGroups ? groupByMaker(parent.children) : null;

  const crumbs = [
    { label: category.category, href: categoryHref(categoryIndex) },
    ...(group
      ? [{ label: group.name, href: boardParentBrowseHref(group) }]
      : []),
    { label: parent.name },
  ];

  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-3 md:px-4 lg:max-w-7xl">
        <SiteLogoLink />
        <SearchInput />
        <SettingsNavLink />
      </div>
      <ForumShell
        activeCategoryIndex={categoryIndex}
        activeFid={fid}
        crumbs={crumbs}
      >
        <div className="flex flex-col gap-4">
          <header className="rounded-2xl border border-default-200/70 bg-content1 px-4 py-5 dark:border-slate-700/70">
            <h1 className="text-lg font-semibold text-foreground md:text-xl">
              {parent.name}
            </h1>
            <p className="mt-1 text-xs text-default-500 md:text-sm">
              {isHub
                ? t("Boards.category_subtitle", { count: nested.length })
                : useMakerGroups
                  ? t("Boards.maker_subtitle", {
                      makers: groups?.length || 0,
                      count: parent.children.length,
                    })
                  : t("Boards.board_subtitle", {
                      count: parent.children.length,
                    })}
            </p>
            {useMakerGroups ? (
              <p className="mt-2 text-xs leading-relaxed text-default-400 md:text-sm">
                {t("Boards.maker_guide")}
              </p>
            ) : null}
          </header>

          {isHub ? (
            <div className="flex flex-col gap-2">
              {nested.map((n) => {
                const nf = parentFid(n);
                return (
                  <Link
                    key={n.name}
                    className="group flex min-h-14 items-center gap-3 rounded-2xl border border-default-200/80 bg-content1 px-4 py-3.5 active:bg-primary/10 dark:border-slate-700/80"
                    href={boardParentBrowseHref(n)}
                  >
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-[15px] font-semibold text-foreground group-active:text-primary">
                        {n.name}
                      </h2>
                      <p className="mt-0.5 text-xs text-default-400">
                        {nf
                          ? t("Boards.subtype_count", {
                              count: n.children.length,
                            })
                          : t("Boards.whole_board")}
                      </p>
                    </div>
                    <ChevronRightIcon
                      className="shrink-0 text-default-300"
                      size={18}
                    />
                  </Link>
                );
              })}
            </div>
          ) : groups ? (
            <div className="flex flex-col gap-5">
              {groups.map(({ maker, items }) => {
                const desc = makerDescription(maker);
                return (
                  <section
                    key={maker}
                    className="rounded-2xl border border-default-200/70 bg-content1/80 px-3.5 py-3.5 dark:border-slate-700/70"
                  >
                    <div className="mb-2.5 px-0.5">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <h2 className="text-sm font-semibold text-foreground">
                          <span className="mr-1.5 text-[11px] font-medium uppercase tracking-wide text-default-400">
                            {t("Boards.maker_label")}
                          </span>
                          {maker}
                        </h2>
                        <span className="text-xs text-default-400">
                          {t("Boards.prefix_count", { count: items.length })}
                        </span>
                      </div>
                      {desc ? (
                        <p className="mt-1.5 text-[13px] leading-relaxed text-default-600 dark:text-slate-300">
                          {desc}
                        </p>
                      ) : null}
                    </div>
                    <p className="mb-1.5 px-0.5 text-[11px] font-medium text-default-400">
                      {t("Boards.prefix_label")}
                    </p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {items.map((child) => {
                        const code = child.type_name || child.name;
                        const note = prefixNote(maker, code);
                        return (
                          <Link
                            key={child.key}
                            title={note || code}
                            className="group flex flex-col rounded-xl border border-default-200/80 bg-background/60 px-3.5 py-2.5 transition-colors hover:border-primary/40 dark:border-slate-700/80"
                            href={boardBrowseHref(child)}
                          >
                            <span className="text-sm font-semibold text-foreground group-hover:text-primary">
                              {code}
                            </span>
                            {note ? (
                              <span className="mt-1 text-xs leading-relaxed text-default-500 group-hover:text-default-600">
                                {note}
                              </span>
                            ) : null}
                          </Link>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {parent.children.map((child) => (
                <Link
                  key={child.key}
                  className="group flex min-h-12 items-center gap-3 rounded-2xl border border-default-200/80 bg-content1 px-4 py-3 active:bg-primary/10 dark:border-slate-700/80"
                  href={boardBrowseHref(child)}
                >
                  <span className="min-w-0 flex-1 truncate text-[15px] text-foreground group-active:text-primary">
                    {child.type_name || child.name}
                  </span>
                  <ChevronRightIcon
                    className="shrink-0 text-default-300"
                    size={16}
                  />
                </Link>
              ))}
            </div>
          )}
        </div>
      </ForumShell>
      <FloatTool />
    </>
  );
}
