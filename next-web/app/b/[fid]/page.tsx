import { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { BrowseLinkRow } from "@/components/BrowseLinkRow";
import { ForumShell } from "@/components/ForumShell";
import { MakerGroupCard } from "@/components/MakerGroupCard";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import {
  boardBrowseHref,
  boardParentBrowseHref,
  categoryHref,
  findByFid,
  isGroupBoard,
  isJapanBrowseContext,
  legacyFidRedirect,
  parentFid,
  type BoardNavChild,
} from "@/config/boards";

export const dynamic = "force-dynamic";

function groupByMaker(
  children: BoardNavChild[],
): { maker: string; items: BoardNavChild[] }[] {
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
  const japanPrefs = isJapanBrowseContext(fid);

  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-3 md:px-4 lg:max-w-7xl">
        <SiteLogoLink />
        <SearchInput japanPrefs={japanPrefs} />
        <SettingsNavLink />
      </div>
      <ForumShell
        activeCategoryIndex={categoryIndex}
        activeFid={fid}
        crumbs={crumbs}
      >
        <div className="flex flex-col gap-3 md:gap-4">
          {isHub ? (
            <div className="flex flex-col gap-2.5">
              {nested.map((n) => {
                const nf = parentFid(n);
                return (
                  <BrowseLinkRow
                    key={n.name}
                    href={boardParentBrowseHref(n)}
                    title={n.name}
                    subtitle={
                      nf
                        ? t("Boards.subtype_count", {
                            count: n.children.length,
                          })
                        : t("Boards.whole_board")
                    }
                  />
                );
              })}
            </div>
          ) : groups ? (
            <div className="flex flex-col gap-3.5 md:gap-4">
              {groups.map(({ maker, items }) => (
                <MakerGroupCard
                  key={maker}
                  maker={maker}
                  items={items}
                  prefixCountLabel={t("Boards.prefix_count", {
                    count: items.length,
                  })}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {parent.children.map((child) => (
                <BrowseLinkRow
                  key={child.key}
                  compact
                  href={boardBrowseHref(child)}
                  title={child.type_name || child.name}
                />
              ))}
            </div>
          )}
        </div>
      </ForumShell>
      <FloatTool />
    </>
  );
}
