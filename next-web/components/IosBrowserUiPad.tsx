"use client";

import { useEffect } from "react";

/**
 * iOS Safari 底栏高度不计入 env(safe-area-inset-bottom)。
 * 用 visualViewport 算出被浏览器 UI 挡住的底部像素，写入 CSS 变量，
 * 供页底 spacer 使用，保证文档流末尾的翻页能滚进可视区。
 *
 * @see https://github.com/mantinedev/mantine/issues/8326
 * @see https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API
 */
export function useIosBrowserUiBottomVar() {
  useEffect(() => {
    const root = document.documentElement;

    const sync = () => {
      const vv = window.visualViewport;
      if (!vv) {
        root.style.setProperty("--ios-browser-ui-bottom", "0px");
        return;
      }
      // layout 视口底部被浏览器 UI（底栏等）盖住的高度
      const covered = Math.max(
        0,
        window.innerHeight - vv.height - vv.offsetTop,
      );
      root.style.setProperty(
        "--ios-browser-ui-bottom",
        `${Math.ceil(covered)}px`,
      );
    };

    sync();
    window.visualViewport?.addEventListener("resize", sync);
    window.visualViewport?.addEventListener("scroll", sync);
    window.addEventListener("resize", sync);
    window.addEventListener("orientationchange", sync);

    return () => {
      window.visualViewport?.removeEventListener("resize", sync);
      window.visualViewport?.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      window.removeEventListener("orientationchange", sync);
    };
  }, []);
}

/** 页底占位：跟在翻页后面，把翻页顶进可视区（不悬浮、不盖图） */
export function IosBrowserUiPad() {
  useIosBrowserUiBottomVar();

  return <div aria-hidden className="ios-browser-ui-pad" />;
}
