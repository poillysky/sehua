"use client";

import { useEffect, useState } from "react";

import {
  buildImageProxyUrl,
  coverHostPriority,
  isUnreliableCoverHost,
  landscapeUrlHint,
} from "@/lib/imageProxy";

type PreviewImageProps = {
  src?: string | null;
  /** 多候选：优先展示能加载成功的（按数组顺序） */
  srcs?: string[];
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
  preferProxy?: boolean;
  /** 多候选时优先宽>高的横图（FC2 等） */
  preferLandscape?: boolean;
};

type LoadState = "loading" | "ok" | "fail";

type ProbeOk = { url: string; w: number; h: number };

function resolveAttempts(url: string, preferProxy: boolean): string[] {
  const proxied = buildImageProxyUrl(url);
  if (isUnreliableCoverHost(url)) {
    return [url];
  }
  if (preferProxy) {
    return [proxied, url];
  }
  return [url, proxied];
}

function probeImage(url: string, timeoutMs = 8_000): Promise<ProbeOk | null> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve(null);
      return;
    }
    const img = new Image();
    let settled = false;
    const finish = (hit: ProbeOk | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      img.onload = null;
      img.onerror = null;
      resolve(hit);
    };
    const timer = window.setTimeout(() => finish(null), timeoutMs);
    img.onload = () =>
      finish({
        url,
        w: img.naturalWidth || 0,
        h: img.naturalHeight || 0,
      });
    img.onerror = () => finish(null);
    img.referrerPolicy = "strict-origin-when-cross-origin";
    img.src = url;
  });
}

async function pickFirstLoadable(
  candidates: string[],
  preferProxy: boolean,
  preferLandscape: boolean,
  signal: { cancelled: boolean },
): Promise<string | null> {
  if (!candidates.length) return null;

  const loaded: Array<ProbeOk & { index: number }> = [];

  await Promise.all(
    candidates.map(async (raw, index) => {
      for (const attempt of resolveAttempts(raw, preferProxy)) {
        if (signal.cancelled) return;
        const hit = await probeImage(attempt);
        if (signal.cancelled) return;
        if (hit) {
          loaded.push({ ...hit, index });
          return;
        }
      }
    }),
  );

  if (signal.cancelled || !loaded.length) return null;

  loaded.sort((a, b) => a.index - b.index);

  if (preferLandscape) {
    const landscape = loaded.filter((x) => x.w > 0 && x.h > 0 && x.w >= x.h);
    if (landscape.length) return landscape[0].url;
  }

  return loaded[0].url;
}

export function PreviewImage({
  src,
  srcs,
  alt,
  className,
  loading = "lazy",
  preferProxy = false,
  preferLandscape = false,
}: PreviewImageProps) {
  const candidates = (
    srcs && srcs.length > 0 ? srcs.filter(Boolean) : src ? [src] : []
  ).sort((a, b) => {
    const byHost = coverHostPriority(b) - coverHostPriority(a);
    if (byHost) return byHost;
    if (preferLandscape) return landscapeUrlHint(b) - landscapeUrlHint(a);
    return 0;
  });
  const candidatesKey = candidates.join("|");
  const [imgSrc, setImgSrc] = useState("");
  const [state, setState] = useState<LoadState>(
    candidates.length ? "loading" : "fail",
  );

  useEffect(() => {
    if (!candidates.length) {
      setImgSrc("");
      setState("fail");
      return;
    }

    const signal = { cancelled: false };
    setImgSrc("");
    setState("loading");

    pickFirstLoadable(
      candidates,
      preferProxy,
      preferLandscape,
      signal,
    ).then((picked) => {
      if (signal.cancelled) return;
      if (picked) {
        setImgSrc(picked);
        setState("ok");
      } else {
        setImgSrc("");
        setState("fail");
      }
    });

    return () => {
      signal.cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidatesKey, preferProxy, preferLandscape]);

  if (state === "loading") {
    return <span className="block h-full w-full" aria-hidden />;
  }

  if (state === "fail" || !imgSrc) {
    return (
      <span className="flex h-full w-full items-center justify-center text-[10px] text-default-300">
        —
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt}
      className={className}
      loading={loading}
      referrerPolicy="strict-origin-when-cross-origin"
      src={imgSrc}
      onError={() => {
        setState("fail");
        setImgSrc("");
      }}
    />
  );
}
