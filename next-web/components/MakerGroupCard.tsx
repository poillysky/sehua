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

      <div className="grid grid-cols-2 gap-2.5 p-3 sm:grid-cols-3 sm:gap-3 sm:p-3.5 md:grid-cols-4 lg:grid-cols-5">
        {items.map((child) => {
          const code = child.type_name || child.name;
          const note = prefixNote(maker, code);
          return (
            <Link
              key={child.key}
              title={note || code}
              prefetch={false}
              className="group flex min-h-[5.25rem] flex-col justify-between rounded-xl border border-default-200/80 bg-default-50/60 p-3 shadow-sm transition-[border-color,box-shadow,transform,background-color] duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-content1 hover:shadow-md dark:border-slate-700/70 dark:bg-slate-800/40 dark:hover:border-primary/35 dark:hover:bg-slate-800/70"
              href={boardBrowseHref(child)}
            >
              <span className="text-[15px] font-semibold tracking-wide text-foreground group-hover:text-primary">
                {code}
              </span>
              {note ? (
                <span className="mt-2 line-clamp-2 text-[11px] leading-snug text-default-500 dark:text-slate-400">
                  {note}
                </span>
              ) : (
                <span className="mt-2 min-h-[1.375rem]" aria-hidden />
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
