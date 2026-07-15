import { BrowseEntryButton } from "@/components/BrowseEntryButton";
import { HomeLogo } from "@/components/HomeLogo";
import { SearchInput } from "@/components/SearchInput";
import { ToggleTheme, SwitchLanguage } from "@/components/FloatTool";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { Stats } from "@/components/Stats";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <section className="mx-auto flex h-full w-4/5 flex-col items-center justify-center gap-4 pt-[max(3rem,10vh)] pb-[max(2rem,6vh)] md:w-3/5 md:pt-[max(2.5rem,8vh)] md:pb-[max(2rem,5vh)]">
      <HomeLogo />
      <SearchInput />
      <BrowseEntryButton />
      <div className="safe-fixed-bottom-right fixed invisible md:visible">
        <Stats />
      </div>
      <div className="safe-fixed-top fixed z-20 flex items-center gap-1.5">
        <SettingsNavLink noBg />
        <SwitchLanguage noBg />
        <ToggleTheme noBg />
      </div>
    </section>
  );
}
