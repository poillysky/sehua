import Link from "next/link";

import { boardBrowseHref, type BoardNavChild } from "@/config/boards";
import { makerDescription, prefixNote } from "@/config/av-makers";

export function MakerGroupCard({
  maker,
  items,
}: {
  maker: string;
  items: BoardNavChild[];
}) {
  const desc = makerDescription(maker);

  return (
    <section className="maker-card overflow-hidden rounded-2xl border border-default-200/70 bg-content1 dark:border-slate-700/70 dark:bg-slate-900/45">
      <div className="border-b border-default-100 px-4 py-3.5 dark:border-slate-800">
        <h2 className="min-w-0 text-base font-semibold tracking-tight text-foreground">
          <span>{maker}</span>
          {desc ? (
            <span className="ml-2 text-[13px] font-normal leading-relaxed text-default-500 dark:text-slate-400">
              {desc}
            </span>
          ) : null}
        </h2>
      </div>

      <div className="grid grid-cols-3 gap-2 p-2.5 sm:gap-3 sm:p-3.5 md:grid-cols-4 lg:grid-cols-5">
        {items.map((child) => {
          const code = child.type_name || child.name;
          const note = prefixNote(maker, code);
          return (
            <Link
              key={child.key}
              title={note || code}
              prefetch={false}
              className="group flex min-h-[4.75rem] flex-col items-center justify-between rounded-2xl border border-default-200/60 bg-white/90 p-2 text-center shadow-soft transition-[border-color,box-shadow,transform,background-color] duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-card sm:min-h-[5.25rem] sm:items-stretch sm:p-3 sm:text-left dark:border-slate-600/50 dark:bg-slate-800/80 dark:hover:border-primary/35"
              href={boardBrowseHref(child)}
            >
              <span className="w-full text-[13px] font-semibold tracking-wide text-foreground group-hover:text-primary sm:text-[15px]">
                {code}
              </span>
              {note ? (
                <span className="mt-1.5 w-full line-clamp-2 text-[10px] leading-snug text-default-500 sm:mt-2 sm:text-[11px] dark:text-slate-400">
                  {note}
                </span>
              ) : (
                <span className="mt-1.5 min-h-[1.25rem] sm:mt-2 sm:min-h-[1.375rem]" aria-hidden />
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
