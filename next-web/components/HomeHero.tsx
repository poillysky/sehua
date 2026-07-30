"use client";

import clsx from "clsx";
import { Suspense, useState } from "react";

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
      className="home-search-fallback h-12 w-full rounded-2xl bg-default-100/80 ring-1 ring-default-200/60 dark:bg-slate-800/60 dark:ring-slate-600/50"
    />
  );
}

export function HomeHero() {
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

        <div className="home-hero__tools relative z-[2] flex w-full shrink-0 items-center justify-end gap-0.5">
          <SettingsNavLink noBg />
          <SwitchLanguage noBg />
          <ToggleTheme noBg />
        </div>

        <div className="home-hero__brand relative z-[1] flex min-h-0 flex-1 flex-col items-center justify-center text-center">
          <button
            type="button"
            className="group relative z-[1] inline-flex flex-row items-center gap-2.5 outline-none sm:gap-3.5"
            title={siteConfig.name}
            onPointerDown={doClickAnimation}
          >
            <span className="home-hero__mark relative inline-flex shrink-0">
              <Ed2kLogo
                className={clsx(
                  "home-hero__logo relative block text-primary transition-transform duration-400",
                  "group-hover:scale-[1.04]",
                  isAnimating && "animate-pop",
                )}
              />
            </span>
            <h1 className="home-brand-title text-left font-bold leading-none tracking-[0.04em] text-foreground">
              {siteConfig.name}
            </h1>
          </button>
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
