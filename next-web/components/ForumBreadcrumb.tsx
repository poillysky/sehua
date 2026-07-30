"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { ChevronRightIcon } from "@/components/BrowseIcons";

export type ForumCrumb = {
  label: string;
  href?: string;
};

export function ForumBreadcrumb({ items }: { items: ForumCrumb[] }) {
  const t = useTranslations();

  return (
    <nav
      aria-label="breadcrumb"
      className="flex min-w-0 flex-wrap items-center gap-0.5 text-[11px] text-default-500 sm:gap-1 sm:text-xs md:text-[13px]"
    >
      <Link
        className="rounded-md px-0.5 py-0.5 transition-colors hover:bg-primary/10 hover:text-primary sm:px-1"
        href="/"
      >
        {t("Boards.home")}
      </Link>
      {items.map((item, i) => (
        <span
          key={`${item.label}-${i}`}
          className="inline-flex min-w-0 items-center gap-0.5 sm:gap-1"
        >
          <ChevronRightIcon className="shrink-0 text-default-300" size={11} />
          {item.href ? (
            <Link
              className="truncate rounded-md px-0.5 py-0.5 transition-colors hover:bg-primary/10 hover:text-primary sm:px-1"
              href={item.href}
            >
              {item.label}
            </Link>
          ) : (
            <span className="truncate rounded-md px-0.5 py-0.5 font-medium text-foreground sm:px-1">
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
