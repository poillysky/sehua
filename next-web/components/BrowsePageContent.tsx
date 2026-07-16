"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Pagination } from "@nextui-org/react";
import { useTranslations } from "next-intl";
import { useIsSSR } from "@react-aria/ssr";

import { BrowsePageToolbar } from "@/components/BrowsePageToolbar";
import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";
import { ResourceFeedItem } from "@/components/ResourceFeedItem";
import { Ed2kResourceProps } from "@/types";
import { $env } from "@/utils";
import { BROWSE_PAGE_MAX, BROWSE_PAGE_SIZE } from "@/config/constant";

async function fetchBrowsePage(page: number) {
  const response = await fetch(
    `/api/browse?p=${page}&ps=${BROWSE_PAGE_SIZE}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error("Failed to fetch browse resources");
  }

  const json = await response.json();

  return {
    resources: (json.data || []) as Ed2kResourceProps[],
    totalCount: Number(json.total_count || 0),
  };
}

function BrowseResourceList({
  resources,
}: {
  resources: Ed2kResourceProps[];
}) {
  const t = useTranslations();

  if (!resources.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-default-300 bg-default-50/60 px-4 py-14 text-center dark:border-slate-600 dark:bg-slate-900/40">
        <p className="text-sm text-default-500">{t("Browse.empty")}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3.5 md:gap-4">
      {resources.map((item) => (
        <ResourceFeedItem key={item.hash} item={item} />
      ))}
    </div>
  );
}

export function BrowsePageContent({
  initialResources = [],
  initialTotalCount = 0,
  initialPage = 1,
}: {
  initialResources?: Ed2kResourceProps[];
  initialTotalCount?: number;
  initialPage?: number;
}) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isSSR = useIsSSR();

  const page = Math.min(
    Math.max(Number(searchParams.get("p")) || initialPage || 1, 1),
    BROWSE_PAGE_MAX,
  );

  const [resources, setResources] = useState(initialResources);
  const [totalCount, setTotalCount] = useState(initialTotalCount);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const skipFirstFetch = useRef(true);
  const loadedPageRef = useRef(initialPage);

  const totalPages = Math.max(
    1,
    Math.min(Math.ceil(totalCount / BROWSE_PAGE_SIZE) || 1, BROWSE_PAGE_MAX),
  );

  const goToPage = useCallback(
    (nextPage: number) => {
      const safe = Math.min(Math.max(nextPage, 1), BROWSE_PAGE_MAX);
      const params = new URLSearchParams(searchParams.toString());

      if (safe <= 1) {
        params.delete("p");
      } else {
        params.set("p", String(safe));
      }

      const qs = params.toString();

      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: true });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    if (skipFirstFetch.current && page === loadedPageRef.current) {
      skipFirstFetch.current = false;

      return;
    }

    skipFirstFetch.current = false;
    let cancelled = false;

    setLoading(true);
    setFailed(false);

    fetchBrowsePage(page)
      .then((data) => {
        if (cancelled) return;
        setResources(data.resources);
        setTotalCount(data.totalCount);
        loadedPageRef.current = page;
        window.scrollTo({ top: 0, behavior: "smooth" });
      })
      .catch(() => {
        if (cancelled) return;
        setFailed(true);
        setResources([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [page]);

  const handleRefresh = () => {
    const jump =
      totalPages > 1 ? Math.floor(Math.random() * totalPages) + 1 : 1;

    if (jump === page) {
      skipFirstFetch.current = false;
      loadedPageRef.current = -1;
      goToPage(jump);
      setLoading(true);
      void fetchBrowsePage(jump)
        .then((data) => {
          setResources(data.resources);
          setTotalCount(data.totalCount);
          loadedPageRef.current = jump;
          window.scrollTo({ top: 0, behavior: "smooth" });
        })
        .catch(() => {
          setFailed(true);
          setResources([]);
        })
        .finally(() => setLoading(false));

      return;
    }

    goToPage(jump);
  };

  return (
    <div className="flex flex-col gap-4 md:gap-5">
      <BrowsePageToolbar
        loading={loading}
        totalCount={totalCount}
        onRefresh={handleRefresh}
      />

      {loading && !resources.length ? (
        <BrowseResourceListSkeleton />
      ) : failed ? (
        <div className="rounded-2xl border border-danger-200 bg-danger-50/50 px-4 py-10 text-center dark:border-danger-400/30 dark:bg-danger-400/10">
          <p className="text-sm text-danger">
            {t("ERROR_MESSAGE.INTERNAL_SERVER_ERROR")}
          </p>
        </div>
      ) : (
        <div
          className={
            loading
              ? "pointer-events-none opacity-55 transition-opacity"
              : "transition-opacity"
          }
        >
          <BrowseResourceList resources={resources} />
        </div>
      )}

      {!isSSR && totalPages > 1 ? (
        <div className="sticky bottom-3 z-20 mx-auto w-full max-w-xl">
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-default-200/90 bg-white/90 px-3 py-3 shadow-lg backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/90 md:px-4">
            <Pagination
              className="flex justify-center"
              classNames={{
                wrapper: "gap-x-1.5 md:gap-x-2",
                item: "bg-transparent shadow-none",
                cursor: "font-semibold",
              }}
              isDisabled={loading}
              page={page}
              showControls={$env.isDesktop}
              siblings={$env.isMobile ? 1 : 3}
              size={$env.isMobile ? "lg" : "md"}
              total={totalPages}
              onChange={goToPage}
            />
            <p className="text-[11px] text-default-400 md:text-xs">
              {t("Browse.page_of", { page, total: totalPages })}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function prefetchBrowseResources() {
  void fetchBrowsePage(1).catch(() => undefined);
}
