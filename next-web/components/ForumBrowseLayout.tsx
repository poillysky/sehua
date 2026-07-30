"use client";

import { useMemo } from "react";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { FloatTool } from "@/components/FloatTool";
import { ForumShell } from "@/components/ForumShell";
import { MobileViewportScroll } from "@/components/MobileViewportScroll";
import { resolveBrowseShellState } from "@/config/boards";

/**
 * 浏览区持久壳：侧栏/搜索吸顶不随路由重挂，避免点导航整页闪白。
 * 挂在 app/b、app/c 的 layout 上；页面只渲染内容区。
 */
export function ForumBrowseLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations();

  const shell = useMemo(() => {
    const state = resolveBrowseShellState(pathname || "/");
    if (!state) return null;
    const crumbs = state.crumbTailKey
      ? [...state.crumbs, { label: t(state.crumbTailKey) }]
      : state.crumbs;
    return { ...state, crumbs };
  }, [pathname, t]);

  if (!shell) {
    return <>{children}</>;
  }

  return (
    <>
      <MobileViewportScroll enabled={shell.fillMobile}>
        <ForumShell
          activeCategoryIndex={shell.activeCategoryIndex}
          activeFid={shell.activeFid}
          activeTypeid={shell.activeTypeid}
          crumbs={shell.crumbs}
          fillMobile={shell.fillMobile}
          japanPrefs={shell.japanPrefs}
        >
          {children}
        </ForumShell>
      </MobileViewportScroll>
      <FloatTool />
    </>
  );
}
