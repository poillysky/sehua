"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { BoardsIcon, ChevronRightIcon } from "@/components/BrowseIcons";
import {
  BOARD_NAV,
  boardBrowseHref,
  boardParentBrowseHref,
  type BoardNavChild,
  type BoardNavParent,
} from "@/config/boards";

function ChildRow({ child }: { child: BoardNavChild }) {
  const label = child.type_name || child.name;

  return (
    <Link
      className="group flex min-h-11 items-center gap-3 border-b border-default-100 px-4 py-3 last:border-b-0 active:bg-primary/10 dark:border-slate-800/90 dark:active:bg-primary/15"
      href={boardBrowseHref(child)}
    >
      <span className="min-w-0 flex-1 truncate text-[15px] text-foreground group-active:text-primary">
        {label}
      </span>
      <ChevronRightIcon
        className="shrink-0 text-default-300 group-active:text-primary"
        size={16}
      />
    </Link>
  );
}

function ParentBlock({
  parent,
  index,
  open,
  onToggle,
}: {
  parent: BoardNavParent;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const t = useTranslations();
  const sole = parent.children.length === 1 && !parent.children[0]?.type_name;
  const singleTyped =
    parent.children.length === 1 && Boolean(parent.children[0]?.type_name);
  const child = parent.children[0];
  const subtypeCount = parent.children.length;
  const expandable = !sole;

  const subtitle = sole
    ? t("Boards.whole_board")
    : singleTyped && child?.type_name
      ? child.type_name
      : t("Boards.subtype_count", { count: subtypeCount });

  const headerInner = (
    <>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-default-100 text-xs font-semibold tabular-nums text-default-500 dark:bg-slate-800 dark:text-slate-400">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-[15px] font-semibold leading-snug tracking-tight text-foreground">
          {parent.name}
        </h3>
        <p className="mt-0.5 truncate text-xs leading-none text-default-400">
          {subtitle}
        </p>
      </div>
      {expandable ? (
        <Link
          className="inline-flex h-9 shrink-0 items-center rounded-lg px-2.5 text-xs font-medium text-primary active:bg-primary/10"
          href={boardParentBrowseHref(parent)}
          onClick={(e) => e.stopPropagation()}
        >
          {t("Boards.all_children")}
        </Link>
      ) : null}
      <ChevronRightIcon
        className={`shrink-0 text-default-400 transition-transform duration-200 ${
          expandable && open ? "rotate-90 text-primary" : ""
        }`}
        size={18}
      />
    </>
  );

  const headerClass =
    "flex min-h-14 w-full items-center gap-3 px-4 py-3.5 text-left active:bg-default-100/70 dark:active:bg-slate-800/60";

  if (sole && child) {
    return (
      <article className="overflow-hidden rounded-2xl border border-default-200/80 bg-content1 dark:border-slate-700/80 dark:bg-slate-900/60">
        <Link className={headerClass} href={boardBrowseHref(child)}>
          {headerInner}
        </Link>
      </article>
    );
  }

  return (
    <article className="overflow-hidden rounded-2xl border border-default-200/80 bg-content1 dark:border-slate-700/80 dark:bg-slate-900/60">
      <button
        type="button"
        className={`${headerClass} cursor-pointer ${
          open ? "border-b border-default-100 dark:border-slate-800" : ""
        }`}
        aria-expanded={open}
        onClick={onToggle}
      >
        {headerInner}
      </button>
      {open ? (
        <div className="flex flex-col">
          {parent.children.map((c) => (
            <ChildRow key={c.key} child={c} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function BoardsNavContent() {
  const t = useTranslations();
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const totalBoards = BOARD_NAV.reduce((n, cat) => n + cat.boards.length, 0);
  const totalSubtypes = BOARD_NAV.reduce(
    (n, cat) => n + cat.boards.reduce((m, b) => m + b.children.length, 0),
    0,
  );

  function toggleParent(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <div className="flex w-full flex-col gap-6 pb-2 md:gap-7">
      <header className="relative overflow-hidden rounded-2xl border border-default-200/70 bg-content1 shadow-sm dark:border-slate-700/70">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-primary/12 via-transparent to-transparent dark:from-primary/15"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent"
        />

        <div className="relative flex flex-col gap-3 px-4 py-5 md:px-5 md:py-6">
          <div className="flex items-center gap-3.5">
            <div className="relative shrink-0">
              <div
                aria-hidden
                className="absolute inset-0 rounded-2xl bg-primary/20 blur-md"
              />
              <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary-600 text-primary-foreground shadow-md shadow-primary/25">
                <BoardsIcon className="drop-shadow-sm" size={20} />
              </div>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-semibold tracking-tight text-foreground">
                  {t("Boards.title")}
                </h1>
                <span className="inline-flex items-center rounded-full border border-default-200/80 bg-background/70 px-2 py-0.5 text-[11px] font-medium tabular-nums text-default-600 dark:border-slate-600 dark:bg-slate-800/70 dark:text-slate-300">
                  {totalBoards} · {totalSubtypes}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-default-500">
                {t("Boards.subtitle")}
              </p>
            </div>
          </div>
        </div>
      </header>

      {BOARD_NAV.map((cat, catIndex) => (
        <section key={cat.category} className="flex flex-col gap-3">
          <div className="px-0.5">
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-[11px] font-bold leading-none tabular-nums text-primary dark:bg-primary/20"
              >
                {catIndex + 1}
              </span>
              <h2 className="text-sm font-semibold leading-6 tracking-wide text-foreground">
                {cat.category}
              </h2>
              <span className="text-xs leading-6 text-default-400">
                {cat.boards.length} {t("Boards.board_count")}
              </span>
            </div>
            <div
              aria-hidden
              className="mt-2 h-px w-full bg-gradient-to-r from-primary/25 via-default-200/80 to-transparent dark:via-slate-700/80"
            />
          </div>

          <div className="flex flex-col gap-3">
            {cat.boards.map((parent, i) => (
              <ParentBlock
                key={parent.name}
                index={i}
                open={expanded.has(parent.name)}
                parent={parent}
                onToggle={() => toggleParent(parent.name)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
