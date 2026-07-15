import NextLink from "next/link";

import { Ed2kLogo } from "@/components/icons";
import { siteConfig } from "@/config/site";

export function SiteLogoLink() {
  return (
    <NextLink
      className="mb-[-2px] mr-2 md:mr-4 inline-flex items-center justify-center shrink-0 leading-none"
      href="/"
      title={siteConfig.name}
    >
      <Ed2kLogo className="block h-[50px] w-[50px] md:h-[60px] md:w-[60px] text-primary transition-transform duration-300 hover:scale-105" />
    </NextLink>
  );
}
