import { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { BrowseLinkRow } from "@/components/BrowseLinkRow";
import { ForumShell } from "@/components/ForumShell";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import {
  boardParentBrowseHref,
  findCategory,
  isGroupBoard,
  parentFid,
} from "@/config/boards";

export const dynamic = "force-dynamic";

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
        <div className="flex flex-col gap-2.5">
          {cat.boards.map((parent) => {
            let subtitle: string;
            if (isGroupBoard(parent)) {
              subtitle = t("Boards.category_subtitle", {
                count: parent.boards?.length || 0,
              });
            } else {
              const fid = parentFid(parent);
              subtitle = fid
                ? t("Boards.subtype_count", {
                    count: parent.children.length,
                  })
                : t("Boards.whole_board");
            }
            return (
              <BrowseLinkRow
                key={parent.name}
                href={boardParentBrowseHref(parent)}
                title={parent.name}
                subtitle={subtitle}
              />
            );
          })}
        </div>
      </ForumShell>
      <FloatTool />
    </>
  );
}
