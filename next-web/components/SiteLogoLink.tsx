import NextLink from "next/link";
import clsx from "clsx";

import { Ed2kLogo } from "@/components/icons";
import { siteConfig } from "@/config/site";

export function SiteLogoLink({
  size = "md",
}: {
  /** sm：吸顶浏览栏；md：搜索/详情等 */
  size?: "sm" | "md";
}) {
  return (
    <NextLink
      className={clsx(
        "inline-flex shrink-0 items-center justify-center leading-none",
        size === "sm" ? "mr-1.5" : "mb-[-2px] mr-1.5 md:mr-4",
      )}
      href="/"
      title={siteConfig.name}
    >
      <Ed2kLogo
        className={clsx(
          "block text-primary transition-transform duration-300 hover:scale-105",
          size === "sm"
            ? "h-8 w-8 md:h-9 md:w-9"
            : "h-9 w-9 md:h-[60px] md:w-[60px]",
        )}
      />
    </NextLink>
  );
}
