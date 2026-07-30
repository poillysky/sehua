import { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { BrowseLinkRow } from "@/components/BrowseLinkRow";
import { MakerGroupCard } from "@/components/MakerGroupCard";
import {
  boardBrowseHref,
  boardParentBrowseHref,
  findByFid,
  isGroupBoard,
  legacyFidRedirect,
  parentFid,
  type BoardNavChild,
} from "@/config/boards";

/** 板块导航几乎是静态配置；短 ISR，后退可走客户端缓存，避免每次重扫库 */
export const revalidate = 120;

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

  const { parent } = ctx;
  const nested = parent.boards || [];
  const isHub = isGroupBoard(parent);

  const useMakerGroups =
    !isHub &&
    parent.children.some((c) => Boolean(c.search_keyword)) &&
    new Set(parent.children.map((c) => c.board_name)).size > 1;
  const groups = useMakerGroups ? groupByMaker(parent.children) : null;

  return (
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
            <MakerGroupCard key={maker} maker={maker} items={items} />
          ))}
        </div>
      ) : parent.children.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-default-300/80 px-4 py-12 text-center text-sm text-default-500 dark:border-slate-600">
          {t("Boards.maker_board_empty")}
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
  );
}
