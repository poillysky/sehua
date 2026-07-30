"use client";

import { Suspense, useCallback, useMemo } from "react";
import NextLink from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@nextui-org/react";
import clsx from "clsx";

import { SiteLogoLink } from "@/components/SiteLogoLink";
import { P115SettingsPanel } from "@/components/P115SettingsPanel";
import { ScrapeSettingsPanel } from "@/components/ScrapeSettingsPanel";

type TabKey = "115" | "scrape";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "115", label: "115 网盘" },
  { key: "scrape", label: "刮削" },
];

function parseTab(raw: string | null): TabKey {
  return raw === "scrape" ? "scrape" : "115";
}

function SettingsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = useMemo(
    () => parseTab(searchParams.get("tab")),
    [searchParams],
  );

  const setTab = useCallback(
    (next: TabKey) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === "115") {
        params.delete("tab");
      } else {
        params.set("tab", next);
      }
      const qs = params.toString();
      router.replace(qs ? `/settings?${qs}` : "/settings", { scroll: false });
    },
    [router, searchParams],
  );

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-3 py-4 md:py-8">
      <header className="flex items-center gap-3">
        <SiteLogoLink />
        <h1 className="min-w-0 flex-1 text-lg font-semibold text-foreground">
          设置
        </h1>
        <Button
          as={NextLink}
          className="shrink-0"
          href="/"
          radius="sm"
          size="sm"
          variant="light"
        >
          首页
        </Button>
      </header>

      <div className="flex gap-1 rounded-full border border-default-200/60 bg-white/70 p-1 shadow-soft backdrop-blur-md dark:border-slate-600/50 dark:bg-slate-800/70">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={clsx(
              "flex-1 rounded-full px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "bg-primary text-primary-foreground shadow-soft"
                : "text-default-600 hover:text-foreground",
            )}
            type="button"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "115" ? <P115SettingsPanel /> : <ScrapeSettingsPanel />}
    </section>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <section className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-3 py-4 md:py-8">
          <p className="text-sm text-default-400">加载设置…</p>
        </section>
      }
    >
      <SettingsPageInner />
    </Suspense>
  );
}
