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
      className="h-10 w-full rounded-md bg-default-100/80 ring-1 ring-default-200/60 dark:bg-slate-800/60 dark:ring-slate-600/50"
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
    <header className="home-bar relative w-full overflow-hidden">
      <div aria-hidden className="home-bar__wash" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent"
      />

      <div className="home-bar__row relative z-[1] flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 md:gap-5">
        <button
          type="button"
          className="home-bar__brand group inline-flex shrink-0 items-center gap-2.5 self-start outline-none sm:self-auto"
          title={siteConfig.name}
          onPointerDown={doClickAnimation}
        >
          <Ed2kLogo
            className={clsx(
              "block h-9 w-9 shrink-0 text-primary transition-transform duration-400 md:h-10 md:w-10",
              "group-hover:scale-[1.05]",
              isAnimating && "animate-pop",
            )}
          />
          <span className="home-brand-title text-lg font-bold tracking-[0.04em] text-foreground md:text-xl">
            {siteConfig.name}
          </span>
        </button>

        <div className="home-bar__search min-w-0 flex-1">
          <Suspense fallback={<SearchFallback />}>
            <SearchInput variant="hero" />
          </Suspense>
        </div>

        <div className="home-bar__tools flex shrink-0 items-center justify-end gap-0.5 self-end sm:self-auto">
          <SettingsNavLink noBg />
          <SwitchLanguage noBg />
          <ToggleTheme noBg />
        </div>
      </div>
    </header>
  );
}
