"use client";

import clsx from "clsx";
import { Suspense, useState, type ReactNode } from "react";

import { ToggleTheme, SwitchLanguage } from "@/components/FloatTool";
import { Ed2kLogo } from "@/components/icons";
import { SearchInput } from "@/components/SearchInput";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { siteConfig } from "@/config/site";
import { $env } from "@/utils";

function SearchFallback() {
  return (
    <div
      aria-hidden
      className="home-search-fallback h-12 w-full rounded-xl bg-default-100/80 ring-1 ring-default-200/50 dark:bg-slate-800/50 dark:ring-slate-600/40"
    />
  );
}

export function HomeHero({
  brandCorner,
}: {
  /** 品牌区右下角（如收录条数） */
  brandCorner?: ReactNode;
}) {
  const [isAnimating, setIsAnimating] = useState(false);

  const doClickAnimation = () => {
    if (!$env.isMobile || isAnimating) return;
    setIsAnimating(true);
    window.setTimeout(() => setIsAnimating(false), 400);
  };

  return (
    <header className="home-hero relative z-[1] flex w-full flex-col">
      <div className="home-hero__stage relative flex min-h-0 flex-1 flex-col">
        <span aria-hidden className="home-hero__brand-bg" />
        <span aria-hidden className="home-hero__grain" />

        <div className="home-hero__tools relative z-[2] flex w-full shrink-0 items-center justify-end gap-0.5">
          <SettingsNavLink noBg />
          <SwitchLanguage noBg />
          <ToggleTheme noBg />
        </div>

        <div className="home-hero__brand relative z-[1] flex min-h-0 flex-1 flex-col items-center justify-center text-center">
          <button
            type="button"
            className="home-hero__brand-btn group relative z-[1] inline-flex flex-row items-center gap-3 outline-none sm:gap-3.5"
            title={siteConfig.name}
            onPointerDown={doClickAnimation}
          >
            <span className="home-hero__mark relative inline-flex shrink-0">
              <Ed2kLogo
                className={clsx(
                  "home-hero__logo relative block transition-transform duration-400",
                  "group-hover:scale-[1.03]",
                  isAnimating && "animate-pop",
                )}
              />
            </span>
            <h1 className="home-brand-title font-bold leading-[1.05] text-ink">
              {siteConfig.shortName}
            </h1>
          </button>
          {brandCorner}
        </div>
      </div>

      <div className="home-hero__search relative z-[1] mx-auto w-full shrink-0">
        <Suspense fallback={<SearchFallback />}>
          <SearchInput variant="hero" />
        </Suspense>
      </div>
    </header>
  );
}
