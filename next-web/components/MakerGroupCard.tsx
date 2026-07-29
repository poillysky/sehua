import Link from "next/link";

import { boardBrowseHref, type BoardNavChild } from "@/config/boards";
import { makerDescription, prefixNote } from "@/config/av-makers";

export function MakerGroupCard({
  maker,
  items,
  prefixCountLabel,
}: {
  maker: string;
  items: BoardNavChild[];
  prefixCountLabel: string;
}) {
  const desc = makerDescription(maker);

  return (
    <section className="maker-card overflow-hidden rounded-2xl border border-default-200/70 bg-content1 dark:border-slate-700/70 dark:bg-slate-900/45">
      <div className="border-b border-default-100 px-4 py-3.5 dark:border-slate-800">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 className="min-w-0 flex-1 text-base font-semibold tracking-tight text-foreground">
            <span>{maker}</span>
            {desc ? (
              <span className="ml-2 text-[13px] font-normal leading-relaxed text-default-500 dark:text-slate-400">
                {desc}
              </span>
            ) : null}
          </h2>
          <span className="shrink-0 text-[11px] tabular-nums text-default-400">
            {prefixCountLabel}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-px bg-default-100 sm:grid-cols-2 dark:bg-slate-800/80">
        {items.map((child) => {
          const code = child.type_name || child.name;
          const note = prefixNote(maker, code);
          return (
            <Link
              key={child.key}
              title={note || code}
              className="group flex items-baseline justify-between gap-2 bg-content1 px-4 py-3 transition-colors hover:bg-primary/[0.04] dark:bg-slate-900/45 dark:hover:bg-primary/10"
              href={boardBrowseHref(child)}
            >
              <span className="shrink-0 text-sm font-semibold tracking-wide text-foreground group-hover:text-primary">
                {code}
              </span>
              {note ? (
                <span className="min-w-0 truncate text-right text-xs leading-relaxed text-default-400 group-hover:text-default-500">
                  {note}
                </span>
              ) : null}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
