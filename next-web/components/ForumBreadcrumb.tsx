"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export type ForumCrumb = {
  label: string;
  href?: string;
};

export function ForumBreadcrumb({ items }: { items: ForumCrumb[] }) {
  const t = useTranslations();

  return (
    <nav
      aria-label="breadcrumb"
      className="flex flex-wrap items-center gap-1.5 text-xs text-default-500 md:text-sm"
    >
      <Link className="hover:text-primary" href="/">
        {t("Boards.home")}
      </Link>
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="inline-flex items-center gap-1.5">
          <span className="text-default-300" aria-hidden>
            /
          </span>
          {item.href ? (
            <Link className="hover:text-primary" href={item.href}>
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-foreground">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
