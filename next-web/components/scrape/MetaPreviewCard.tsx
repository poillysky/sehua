"use client";

import { useEffect, useState } from "react";

import {
  KIND_LABEL,
  STATUS_LABEL,
  type ScrapePayload,
} from "@/components/scrape/types";
import { isFullCoverCode } from "@/utils/av-code";

const shell =
  "overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900";

function preferLandscapeKind(kind?: string, code?: string): boolean {
  if (
    kind === "uncensored" ||
    kind === "chinese" ||
    kind === "fc2" ||
    kind === "western"
  ) {
    return true;
  }
  return Boolean(code && isFullCoverCode(code));
}

function CoverThumb({
  code,
  cacheKey,
  kind,
}: {
  code: string;
  cacheKey?: string;
  kind?: string;
}) {
  const bust = encodeURIComponent(cacheKey || "1");
  const nextSrc = `/api/scrape/cover/${encodeURIComponent(code)}?v=${bust}`;
  const [src, setSrc] = useState(nextSrc);
  const [failed, setFailed] = useState(false);
  // 先按类型/番号猜，onload 后按真实宽高比纠正
  const [landscape, setLandscape] = useState(() =>
    preferLandscapeKind(kind, code),
  );

  useEffect(() => {
    setLandscape(preferLandscapeKind(kind, code));
    setFailed(false);
    if (nextSrc === src) return;
    const img = new Image();
    img.onload = () => setSrc(nextSrc);
    img.onerror = () => {
      const fallback = `/covers/${encodeURIComponent(code)}.jpg?v=${bust}`;
      const img2 = new Image();
      img2.onload = () => setSrc(fallback);
      img2.onerror = () => setFailed(true);
      img2.src = fallback;
    };
    img.src = nextSrc;
  }, [nextSrc, code, bust, src, kind]);

  const box = landscape ? "h-24 w-40" : "h-36 w-24";

  if (failed) {
    return (
      <div
        className={`flex shrink-0 items-center justify-center rounded bg-gray-100 text-[10px] text-gray-400 dark:bg-slate-800 ${box}`}
      >
        加载失败
      </div>
    );
  }

  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded bg-gray-100 dark:bg-slate-800 ${box}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        alt={code}
        className={`h-full w-full object-cover ${
          landscape ? "object-center" : "object-right"
        }`}
        decoding="async"
        loading="eager"
        src={src}
        onLoad={(e) => {
          const el = e.currentTarget;
          if (el.naturalWidth > 0 && el.naturalHeight > 0) {
            setLandscape(el.naturalWidth >= el.naturalHeight);
          }
        }}
      />
    </div>
  );
}

export function MetaPreviewCard({
  payload,
  loading,
  emptyHint,
}: {
  payload: ScrapePayload | null;
  loading?: boolean;
  emptyHint?: string;
}) {
  if (loading && !payload?.code) {
    return (
      <div className={`${shell} flex gap-3 p-4`}>
        <div className="h-36 w-24 shrink-0 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
        <div className="flex flex-1 flex-col justify-center gap-2">
          <div className="h-3 w-24 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
          <div className="h-4 w-3/4 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-gray-100 dark:bg-slate-800" />
        </div>
      </div>
    );
  }
  if (!payload?.code) {
    if (!emptyHint) return null;
    return (
      <div className={`${shell} px-4 py-6 text-center text-xs text-gray-400`}>
        {emptyHint}
      </div>
    );
  }
  const title = (
    payload.title_zh ||
    payload.title ||
    payload.title_ja ||
    ""
  ).trim();
  const actresses = payload.actresses || [];
  const actressText = actresses.length ? actresses.join("、") : "—";
  const coverBust = payload.cover_path || "1";
  return (
    <div className={`${shell} flex gap-3 p-4`}>
      {payload.cover_path ? (
        <CoverThumb
          cacheKey={coverBust}
          code={payload.code}
          kind={payload.kind}
        />
      ) : (
        <div
          className={`flex shrink-0 items-center justify-center rounded bg-gray-100 text-[10px] text-gray-400 dark:bg-slate-800 ${
            preferLandscapeKind(payload.kind, payload.code)
              ? "h-24 w-40"
              : "h-36 w-24"
          }`}
        >
          无封面
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-2">
        <p className="font-mono text-xs text-gray-500">
          {payload.code}
          {payload.kind
            ? ` · ${KIND_LABEL[payload.kind] || payload.kind}`
            : ""}
          {payload.status
            ? ` · ${STATUS_LABEL[payload.status] || payload.status}`
            : ""}
        </p>
        <p className="text-sm leading-snug text-gray-900 dark:text-white">
          <span className="mr-1.5 text-[11px] font-medium text-gray-400">
            片名
          </span>
          <span className="font-medium">{title || "—"}</span>
        </p>
        <p className="text-xs leading-snug text-gray-600 dark:text-slate-300">
          <span className="mr-1.5 text-[11px] font-medium text-gray-400">
            女优
          </span>
          {actressText}
        </p>
        {payload.error ? (
          <p className="text-xs text-rose-500">{payload.error}</p>
        ) : null}
      </div>
    </div>
  );
}
