"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { BrowsePrefToggles } from "@/components/BrowsePrefToggles";
import { ForumBreadcrumb, type ForumCrumb } from "@/components/ForumBreadcrumb";
import { SearchInput } from "@/components/SearchInput";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import {
  BOARD_NAV,
  boardBrowseHref,
  boardParentBrowseHref,
  boardPath,
  categoryHref,
  isGroupBoard,
  isJapanBrowseContext,
  isPrefixBoard,
  parentFid,
  type BoardNavParent,
} from "@/config/boards";
import { isZoneCustomCategory } from "@/lib/zoneFolderModel";
import { ZoneFolderSidebar } from "@/components/ZoneFolderSidebar";

function SearchFallback() {
  return (
    <div
      aria-hidden
      className="h-10 min-w-0 flex-1 rounded-full bg-white/70 ring-1 ring-default-200/50 sm:h-11 dark:bg-slate-800/50 dark:ring-slate-600/40"
    />
  );
}

function navItemClass(active: boolean, compact = false) {
  return clsx(
    "block truncate rounded-xl transition-colors",
    compact
      ? "min-h-10 px-3 py-2.5 text-[14px]"
      : "px-2.5 py-1.5 text-[13px]",
    active
      ? "bg-primary/12 font-semibold text-primary"
      : "text-default-600 hover:bg-primary/[0.06] hover:text-primary dark:text-slate-300 dark:hover:bg-primary/10",
  );
}

function SidebarLeaf({
  parent,
  categoryIndex,
  activeFid,
  compact = false,
}: {
  parent: BoardNavParent;
  categoryIndex: number;
  activeFid?: string;
  compact?: boolean;
}) {
  const fid = parentFid(parent);
  const isBoardActive = Boolean(fid && activeFid === fid);
  const sole = parent.children.length === 1 && !parent.children[0]?.type_name;
  const child = parent.children[0];

  if (sole && child) {
    return (
      <Link
        className={navItemClass(isBoardActive, compact)}
        href={boardBrowseHref(child)}
      >
        {parent.name}
      </Link>
    );
  }

  if (isPrefixBoard(parent)) {
    return (
      <Link
        className={navItemClass(isBoardActive, compact)}
        href={fid ? boardPath(fid) : categoryHref(categoryIndex)}
      >
        {parent.name}
      </Link>
    );
  }

  return (
    <Link
      className={navItemClass(isBoardActive, compact)}
      href={boardParentBrowseHref(parent)}
    >
      {parent.name}
    </Link>
  );
}

function SidebarParent({
  parent,
  categoryIndex,
  activeFid,
  activeTypeid,
  compact = false,
}: {
  parent: BoardNavParent;
  categoryIndex: number;
  activeFid?: string;
  activeTypeid?: string;
  compact?: boolean;
}) {
  const nested = parent.boards || [];
  const nestedActive = nested.some((n) => {
    const nf = parentFid(n);
    return Boolean(nf && nf === activeFid);
  });
  const fid = parentFid(parent);
  const isBoardActive = Boolean(fid && activeFid === fid);
  const isLeafLike =
    isPrefixBoard(parent) ||
    (parent.children.length === 1 && !parent.children[0]?.type_name);
  const [open, setOpen] = useState(nestedActive || isBoardActive);

  if (isGroupBoard(parent)) {
    return (
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            className={clsx(
              "flex shrink-0 items-center justify-center rounded-lg text-default-400 hover:bg-primary/[0.06] hover:text-primary",
              compact ? "h-10 w-10" : "h-7 w-7",
            )}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <ChevronRightIcon
              className={`transition-transform ${open ? "rotate-90" : ""}`}
              size={compact ? 16 : 14}
            />
          </button>
          <Link
            className={clsx(
              "min-w-0 flex-1 truncate rounded-xl px-1.5 transition-colors",
              compact ? "py-2.5 text-[14px]" : "py-1.5 text-[13px]",
              nestedActive
                ? "font-semibold text-primary"
                : "text-default-700 hover:text-primary dark:text-slate-200",
            )}
            href={boardParentBrowseHref(parent)}
          >
            {parent.name}
          </Link>
        </div>
        {open ? (
          <div className="ml-3 flex flex-col gap-0.5 border-l border-primary/15 pl-2 dark:border-primary/20">
            {nested.map((n) => (
              <SidebarLeaf
                key={n.name}
                activeFid={activeFid}
                categoryIndex={categoryIndex}
                compact={compact}
                parent={n}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  if (isLeafLike) {
    return (
      <SidebarLeaf
        activeFid={activeFid}
        categoryIndex={categoryIndex}
        compact={compact}
        parent={parent}
      />
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className={clsx(
            "flex shrink-0 items-center justify-center rounded-lg text-default-400 hover:bg-primary/[0.06] hover:text-primary",
            compact ? "h-10 w-10" : "h-7 w-7",
          )}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronRightIcon
            className={`transition-transform ${open ? "rotate-90" : ""}`}
            size={compact ? 16 : 14}
          />
        </button>
        <Link
          className={clsx(
            "min-w-0 flex-1 truncate rounded-xl px-1.5 transition-colors",
            compact ? "py-2.5 text-[14px]" : "py-1.5 text-[13px]",
            isBoardActive && !activeTypeid
              ? "bg-primary/12 font-semibold text-primary"
              : "text-default-700 hover:text-primary dark:text-slate-200",
          )}
          href={fid ? boardPath(fid) : categoryHref(categoryIndex)}
        >
          {parent.name}
        </Link>
      </div>
      {open ? (
        <div className="ml-3 flex flex-col gap-0.5 border-l border-primary/15 pl-2 dark:border-primary/20">
          {parent.children.map((c) => {
            const active =
              isBoardActive && (!activeTypeid || c.typeid === activeTypeid);
            return (
              <Link
                key={c.key}
                className={clsx(
                  "truncate rounded-lg px-2.5 transition-colors",
                  compact ? "min-h-9 py-2 text-[13px]" : "py-1 text-xs",
                  active
                    ? "bg-primary/12 font-semibold text-primary"
                    : "text-default-500 hover:bg-primary/[0.06] hover:text-primary",
                )}
                href={boardBrowseHref(c)}
              >
                {c.type_name || c.name}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ForumNavTree({
  activeCategoryIndex,
  activeFid,
  activeTypeid,
  compact = false,
}: {
  activeCategoryIndex?: number;
  activeFid?: string;
  activeTypeid?: string;
  compact?: boolean;
}) {
  const t = useTranslations();

  return (
    <aside className={clsx("flex w-full flex-col", compact ? "gap-4" : "gap-5")}>
      <div className="flex items-center gap-2 px-1">
        <span
          aria-hidden
          className="h-4 w-1 rounded-full bg-primary"
        />
        <p className="text-[11px] font-semibold tracking-wide text-default-500">
          {t("Boards.sidebar_title")}
        </p>
      </div>

      {compact ? (
        <div className="flex flex-wrap gap-1.5 px-0.5">
          {BOARD_NAV.map((cat, ci) => {
            const catActive = activeCategoryIndex === ci;
            return (
              <Link
                key={cat.category}
                className={clsx(
                  "inline-flex min-h-8 items-center rounded-full px-3 text-[12px] font-medium transition-colors",
                  catActive
                    ? "bg-primary text-primary-foreground shadow-soft"
                    : "bg-default-100 text-default-600 hover:bg-primary/10 hover:text-primary dark:bg-slate-800 dark:text-slate-300",
                )}
                href={categoryHref(ci)}
              >
                {cat.category}
              </Link>
            );
          })}
        </div>
      ) : null}

      {BOARD_NAV.map((cat, ci) => {
        const catActive = activeCategoryIndex === ci;
        return (
          <div key={cat.category} className="flex flex-col gap-1">
            <Link
              className={clsx(
                "rounded-xl px-2.5 font-semibold transition-colors",
                compact ? "py-2 text-[14px]" : "py-1 text-[13px]",
                catActive
                  ? "bg-primary/10 text-primary"
                  : "text-default-700 hover:bg-primary/[0.06] hover:text-primary dark:text-slate-200",
              )}
              href={categoryHref(ci)}
            >
              {cat.category}
            </Link>
            <div className="flex flex-col gap-0.5">
              {isZoneCustomCategory(cat.category) ? (
                <ZoneFolderSidebar
                  activeFid={activeFid}
                  categoryIndex={ci}
                  compact={compact}
                />
              ) : (
                cat.boards.map((parent) => (
                  <SidebarParent
                    key={parent.name}
                    activeFid={activeFid}
                    activeTypeid={activeTypeid}
                    categoryIndex={ci}
                    compact={compact}
                    parent={parent}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </aside>
  );
}

export function ForumShell({
  children,
  crumbs,
  activeFid,
  activeTypeid,
  activeCategoryIndex,
  /** 手机：占满 MobileViewportScroll 剩余高度，供封面内滚 + 底栏翻页 */
  fillMobile,
  japanPrefs = false,
}: {
  children: React.ReactNode;
  crumbs: ForumCrumb[];
  activeFid?: string;
  activeTypeid?: string;
  activeCategoryIndex?: number;
  fillMobile?: boolean;
  japanPrefs?: boolean;
}) {
  const t = useTranslations();
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const chromeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  // 浏览页唯一写入 --page-search-h（搜索/详情用 PageSearchHeader，互不叠用）
  useEffect(() => {
    const el = chromeRef.current;
    if (!el) return;
    const sync = () => {
      document.documentElement.style.setProperty(
        "--page-search-h",
        `${Math.ceil(el.getBoundingClientRect().height)}px`,
      );
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.removeProperty("--page-search-h");
    };
  }, [mobileNavOpen]);

  // 勿用 useMemo 包一层新元素：activeFid 一变会整树重挂，综合区展开态会丢
  const showJapanPrefs =
    japanPrefs || isJapanBrowseContext(activeFid, activeTypeid);

  return (
    <div
      className={`forum-shell mx-auto flex w-full flex-col gap-4 px-3 pb-3 pt-0 md:max-w-6xl md:gap-5 md:px-4 md:pb-5 lg:max-w-7xl ${
        fillMobile
          ? "max-md:min-h-0 max-md:flex-1 max-md:gap-2 max-md:overflow-hidden max-md:pb-0"
          : ""
      }`}
    >
      <div
        ref={chromeRef}
        className={clsx(
          "forum-chrome-sticky sticky z-30 -mx-3 flex shrink-0 flex-col md:-mx-4",
          "bg-white shadow-[0_1px_0_rgba(15,23,42,0.06)]",
          "dark:bg-slate-900 dark:shadow-[0_1px_0_rgba(255,255,255,0.08)]",
          fillMobile ? "top-0" : "top-[max(0px,var(--safe-top))]",
        )}
      >
        <div className="flex w-full min-w-0 items-center gap-1 overflow-x-clip px-3 pt-2 pb-2 md:gap-1.5 md:px-4 md:pt-2.5 md:pb-2">
          <SiteLogoLink size="sm" />
          <Suspense fallback={<SearchFallback />}>
            <SearchInput japanPrefs={showJapanPrefs} />
          </Suspense>
          <SettingsNavLink />
        </div>

        <div className="flex flex-col gap-1.5 px-3 pb-2.5 pt-1.5 shadow-[inset_0_1px_0_rgba(15,23,42,0.06)] md:px-4 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
          <div className="flex min-w-0 items-center justify-between gap-2">
            <ForumBreadcrumb items={crumbs} />
            <div className="flex shrink-0 items-center gap-1.5">
              {showJapanPrefs ? <BrowsePrefToggles /> : null}
              <button
                type="button"
                aria-expanded={mobileNavOpen}
                className={clsx(
                  "inline-flex min-h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium transition-colors md:hidden",
                  mobileNavOpen
                    ? "bg-primary text-primary-foreground shadow-soft"
                    : "border border-default-200/70 bg-white text-default-600 shadow-soft hover:border-primary/30 hover:text-primary dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300",
                )}
                onClick={() => setMobileNavOpen((v) => !v)}
              >
                {mobileNavOpen ? t("Boards.hide_nav") : t("Boards.show_nav")}
              </button>
            </div>
          </div>
          {mobileNavOpen ? (
            <div className="forum-mobile-nav max-h-[min(62vh,28rem)] overflow-y-auto rounded-2xl border border-default-200/50 bg-slate-50/90 p-3 shadow-soft md:hidden dark:border-slate-700/60 dark:bg-slate-800/90">
              <ForumNavTree
                activeCategoryIndex={activeCategoryIndex}
                activeFid={activeFid}
                activeTypeid={activeTypeid}
                compact
              />
            </div>
          ) : null}
        </div>
      </div>

      <div
        className={`flex gap-5 lg:gap-7 ${
          fillMobile ? "max-md:min-h-0 max-md:flex-1 max-md:overflow-hidden" : ""
        }`}
      >
        <div className="hidden w-52 shrink-0 md:block lg:w-60">
          <div
            className="forum-sidebar sticky max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl border border-default-200/50 bg-white p-3.5 shadow-soft dark:border-slate-700/60 dark:bg-slate-900"
            style={{
              top: "calc(max(0px, var(--safe-top)) + var(--page-search-h, 7rem) + 0.75rem)",
            }}
          >
            <ForumNavTree
              activeCategoryIndex={activeCategoryIndex}
              activeFid={activeFid}
              activeTypeid={activeTypeid}
            />
          </div>
        </div>
        <div
          className={`min-w-0 flex-1 ${
            fillMobile
              ? "max-md:flex max-md:min-h-0 max-md:flex-col max-md:overflow-hidden"
              : ""
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
