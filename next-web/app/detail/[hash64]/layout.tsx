import { FloatTool } from "@/components/FloatTool";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";

export default function DetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col justify-center gap-4 px-3 py-3 md:py-8">
      <div className="flex items-center mb-4">
        <SiteLogoLink />
        <SearchInput />
        <SettingsNavLink />
      </div>
      {children}
      <FloatTool />
    </section>
  );
}
