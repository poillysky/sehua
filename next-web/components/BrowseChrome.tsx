"use client";

import { usePathname } from "next/navigation";

import { ForumBrowseLayout } from "@/components/ForumBrowseLayout";
import { ZoneFoldersProvider } from "@/components/ZoneFolderSidebar";
import type { ZoneFoldersStore } from "@/lib/zoneFolderModel";

function isBrowsePath(pathname: string): boolean {
  return /^\/(b|c)(\/|$)/.test(pathname || "");
}

/**
 * 根布局挂载：/b、/c 共用同一 ForumBrowseLayout 实例，
 * 片区↔板块互切时侧栏/搜索不重挂，避免闪白。
 */
export function BrowseChrome({
  children,
  zoneFolders = null,
}: {
  children: React.ReactNode;
  zoneFolders?: ZoneFoldersStore | null;
}) {
  const pathname = usePathname() || "/";
  if (!isBrowsePath(pathname)) {
    return <>{children}</>;
  }
  return (
    <ZoneFoldersProvider initial={zoneFolders}>
      <ForumBrowseLayout>{children}</ForumBrowseLayout>
    </ZoneFoldersProvider>
  );
}
