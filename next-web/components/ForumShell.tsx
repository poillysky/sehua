"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { BrowsePrefToggles } from "@/components/BrowsePrefToggles";
import { ForumBreadcrumb, type ForumCrumb } from "@/components/ForumBreadcrumb";
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

function SidebarLeaf({
  parent,
  categoryIndex,
  activeFid,
}: {
  parent: BoardNavParent;
  categoryIndex: number;
  activeFid?: string;
}) {
  const fid = parentFid(parent);
  const isBoardActive = Boolean(fid && activeFid === fid);
  const sole = parent.children.length === 1 && !parent.children[0]?.type_name;
  const child = parent.children[0];

  if (sole && child) {
    return (
      <Link
        className={`block truncate rounded-lg px-2.5 py-1.5 text-[13px] ${
          isBoardActive
            ? "bg-primary/15 font-medium text-primary"
            : "text-default-600 hover:bg-default-100 dark:text-slate-300 dark:hover:bg-slate-800"
        }`}
        href={boardBrowseHref(child)}
      >
        {parent.name}
      </Link>
    );
  }

  if (isPrefixBoard(parent)) {
    return (
      <Link
        className={`block truncate rounded-lg px-2.5 py-1.5 text-[13px] ${
          isBoardActive
            ? "bg-primary/15 font-medium text-primary"
            : "text-default-600 hover:bg-default-100 dark:text-slate-300 dark:hover:bg-slate-800"
        }`}
        href={fid ? boardPath(fid) : categoryHref(categoryIndex)}
      >
        {parent.name}
      </Link>
    );
  }

  return (
    <Link
      className={`block truncate rounded-lg px-2.5 py-1.5 text-[13px] ${
        isBoardActive
          ? "bg-primary/15 font-medium text-primary"
          : "text-default-600 hover:bg-default-100 dark:text-slate-300 dark:hover:bg-slate-800"
      }`}
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
}: {
  parent: BoardNavParent;
  categoryIndex: number;
  activeFid?: string;
  activeTypeid?: string;
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
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-default-400 hover:bg-default-100 dark:hover:bg-slate-800"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <ChevronRightIcon
              className={`transition-transform ${open ? "rotate-90" : ""}`}
              size={14}
            />
          </button>
          <Link
            className={`min-w-0 flex-1 truncate rounded-lg px-1.5 py-1.5 text-[13px] ${
              nestedActive
                ? "font-medium text-primary"
                : "text-default-700 hover:text-primary dark:text-slate-200"
            }`}
            href={boardParentBrowseHref(parent)}
          >
            {parent.name}
          </Link>
        </div>
        {open ? (
          <div className="ml-3 flex flex-col gap-0.5 border-l border-default-200 pl-2 dark:border-slate-700">
            {nested.map((n) => (
              <SidebarLeaf
                key={n.name}
                activeFid={activeFid}
                categoryIndex={categoryIndex}
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
        parent={parent}
      />
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-default-400 hover:bg-default-100 dark:hover:bg-slate-800"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronRightIcon
            className={`transition-transform ${open ? "rotate-90" : ""}`}
            size={14}
          />
        </button>
        <Link
          className={`min-w-0 flex-1 truncate rounded-lg px-1.5 py-1.5 text-[13px] ${
            isBoardActive && !activeTypeid
              ? "bg-primary/15 font-medium text-primary"
              : "text-default-700 hover:text-primary dark:text-slate-200"
          }`}
          href={fid ? boardPath(fid) : categoryHref(categoryIndex)}
        >
          {parent.name}
        </Link>
      </div>
      {open ? (
        <div className="ml-3 flex flex-col border-l border-default-200 pl-2 dark:border-slate-700">
          {parent.children.map((c) => {
            const active =
              isBoardActive && (!activeTypeid || c.typeid === activeTypeid);
            return (
              <Link
                key={c.key}
                className={`truncate rounded-md px-2 py-1 text-xs ${
                  active
                    ? "bg-primary/12 font-medium text-primary"
                    : "text-default-500 hover:text-primary"
                }`}
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

export function ForumShell({
  children,
  crumbs,
  activeFid,
  activeTypeid,
  activeCategoryIndex,
}: {
  children: React.ReactNode;
  crumbs: ForumCrumb[];
  activeFid?: string;
  activeTypeid?: string;
  activeCategoryIndex?: number;
}) {
  const t = useTranslations();
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const sidebar = useMemo(
    () => (
      <aside className="flex w-full flex-col gap-5">
        <div className="px-1.5">
          <p className="text-[11px] font-semibold tracking-[0.08em] text-default-400">
            {t("Boards.sidebar_title")}
          </p>
        </div>
        {BOARD_NAV.map((cat, ci) => {
          const catActive = activeCategoryIndex === ci;
          return (
            <div key={cat.category} className="flex flex-col gap-1">
              <Link
                className={`rounded-md px-1.5 py-1 text-[13px] font-semibold transition-colors ${
                  catActive
                    ? "text-primary"
                    : "text-default-600 hover:text-primary dark:text-slate-300"
                }`}
                href={categoryHref(ci)}
              >
                {cat.category}
              </Link>
              <div className="flex flex-col gap-0.5">
                {cat.boards.map((parent) => (
                  <SidebarParent
                    key={parent.name}
                    activeFid={activeFid}
                    activeTypeid={activeTypeid}
                    categoryIndex={ci}
                    parent={parent}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </aside>
    ),
    [activeCategoryIndex, activeFid, activeTypeid, t],
  );

  return (
    <div className="forum-shell mx-auto flex w-full flex-col gap-4 px-3 py-3 md:max-w-6xl md:gap-5 md:px-4 md:py-5 lg:max-w-7xl">
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <ForumBreadcrumb items={crumbs} />
          {isJapanBrowseContext(activeFid, activeTypeid) ? (
            <BrowsePrefToggles />
          ) : null}
        </div>
        <button
          type="button"
          className="inline-flex w-fit items-center gap-1.5 rounded-xl border border-default-200/80 bg-content1 px-3 py-1.5 text-xs font-medium text-default-600 transition-colors hover:border-primary/30 hover:text-primary md:hidden dark:border-slate-700"
          onClick={() => setMobileNavOpen((v) => !v)}
        >
          {mobileNavOpen ? t("Boards.hide_nav") : t("Boards.show_nav")}
        </button>
        {mobileNavOpen ? (
          <div className="rounded-2xl border border-default-200/80 bg-content1 p-3.5 md:hidden dark:border-slate-700 dark:bg-slate-900/50">
            {sidebar}
          </div>
        ) : null}
      </div>

      <div className="flex gap-5 lg:gap-7">
        <div className="hidden w-52 shrink-0 md:block lg:w-60">
          <div className="forum-sidebar sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl border border-default-200/70 bg-content1/95 p-3.5 shadow-sm dark:border-slate-700/70 dark:bg-slate-900/55">
            {sidebar}
          </div>
        </div>
        <div className="min-w-0 flex-1" key={pathname}>
          {children}
        </div>
      </div>
    </div>
  );
}
