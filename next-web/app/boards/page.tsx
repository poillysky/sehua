import { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { BoardsNavContent } from "@/components/BoardsNavContent";
import { FloatTool } from "@/components/FloatTool";
import { SearchInput } from "@/components/SearchInput";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { SiteLogoLink } from "@/components/SiteLogoLink";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations();

  return {
    title: t("Boards.title"),
  };
}

export default async function BoardsPage() {
  return (
    <section className="boards-page mx-auto flex w-full flex-col gap-4 md:max-w-3xl md:gap-5 md:py-6 lg:max-w-4xl md:px-3">
      <div className="boards-page-top sticky z-30 -mx-1 mb-1 border-b border-default-200/60 bg-background/85 px-1 pb-2 pt-2 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-950/80 md:static md:mx-0 md:mb-2 md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none dark:md:bg-transparent">
        <div className="flex items-center gap-1 md:mb-1">
          <SiteLogoLink />
          <SearchInput />
          <SettingsNavLink />
        </div>
      </div>

      <BoardsNavContent />
      <FloatTool />
    </section>
  );
}
