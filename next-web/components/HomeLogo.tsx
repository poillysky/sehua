"use client";

import clsx from "clsx";
import { useState } from "react";

import { Ed2kLogo } from "@/components/icons";
import { siteConfig } from "@/config/site";
import { $env } from "@/utils";

export const HomeLogo = () => {
  const [isAnimating, setIsAnimating] = useState(false);

  const doClickAnimation = () => {
    if (!$env.isMobile) {
      return;
    }

    if (isAnimating) {
      return;
    }

    setIsAnimating(true);

    setTimeout(() => {
      setIsAnimating(false);
    }, 400);
  };

  return (
    <h1
      className="logo flex flex-col items-center justify-center gap-2"
      title={siteConfig.name}
      onPointerDown={() => doClickAnimation()}
    >
      <Ed2kLogo
        className={clsx(
          "block h-[148px] w-[148px] text-primary transition-all duration-400",
          "drop-shadow-[0_12px_32px_rgba(0,170,255,0.22)]",
          "dark:drop-shadow-[0_12px_36px_rgba(0,170,255,0.32)]",
          "hover:scale-[1.03] hover:drop-shadow-[0_16px_40px_rgba(0,170,255,0.3)]",
          isAnimating && "animate-pop",
        )}
      />
      <span className="text-2xl md:text-3xl font-semibold tracking-wide text-foreground">
        {siteConfig.name}
      </span>
      <span className="text-sm text-default-500">{siteConfig.description}</span>
    </h1>
  );
};
