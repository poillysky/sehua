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
      className="flex flex-wrap items-center gap-1 text-xs text-default-500 md:gap-1.5 md:text-[13px]"
    >
      <Link
        className="rounded-md px-1 py-0.5 transition-colors hover:bg-default-100 hover:text-primary dark:hover:bg-slate-800"
        href="/"
      >
        {t("Boards.home")}
      </Link>
      {items.map((item, i) => (
        <span
          key={`${item.label}-${i}`}
          className="inline-flex items-center gap-1 md:gap-1.5"
        >
          <ChevronRightIcon className="text-default-300" size={12} />
          {item.href ? (
            <Link
              className="rounded-md px-1 py-0.5 transition-colors hover:bg-default-100 hover:text-primary dark:hover:bg-slate-800"
              href={item.href}
            >
              {item.label}
            </Link>
          ) : (
            <span className="rounded-md px-1 py-0.5 font-medium text-foreground">
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
