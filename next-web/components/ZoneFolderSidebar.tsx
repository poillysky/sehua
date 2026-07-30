"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import Link from "next/link";
import clsx from "clsx";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import {
  folderAncestors,
  isSearchItem,
  listChildren,
  parseZoneActiveFid,
  type ZoneFolder,
  type ZoneFoldersStore,
  zoneFolderHref,
} from "@/lib/zoneFolderModel";

const ZoneFoldersCtx = createContext<ZoneFoldersStore | null>(null);

/** 服务端灌入的目录树，避免侧栏先空白 */
export function ZoneFoldersProvider({
  initial,
  children,
}: {
  initial: ZoneFoldersStore | null;
  children: React.ReactNode;
}) {
  return (
    <ZoneFoldersCtx.Provider value={initial}>{children}</ZoneFoldersCtx.Provider>
  );
}

function navItemClass(active: boolean, compact = false) {
  return clsx(
    "block truncate rounded-xl transition-colors",
    compact
      ? "min-h-10 px-3 py-2.5 text-[14px]"
      : "px-2.5 py-1.5 text-[13px]",
    active
      ? "bg-primary/12 font-semibold text-primary"
      : "text-default-600 hover:bg-primary/[0.06] hover:text-primary dark:text-slate-300 dark:hover:bg-primary/10",
  );
}

function ZoneSidebarNode({
  folder,
  folders,
  categoryIndex,
  activeFolderId,
  compact,
  depth,
}: {
  folder: ZoneFolder;
  folders: ZoneFolder[];
  categoryIndex: number;
  activeFolderId: string | null;
  compact: boolean;
  depth: number;
}) {
  // 侧栏只展示文件夹；搜索项只在网盘内容区出现
  const kids = listChildren(folders, folder.id).filter((k) => !isSearchItem(k));
  const ancestorIds = useMemo(() => {
    if (!activeFolderId) return new Set<string>();
    return new Set(folderAncestors(folders, activeFolderId).map((f) => f.id));
  }, [folders, activeFolderId]);
  const selfActive = activeFolderId === folder.id;
  const childActive = ancestorIds.has(folder.id) && !selfActive;
  // 当前路径上展开，离开后自动收起（与影视区侧栏一致）
  const pathOpen = selfActive || childActive;
  const [open, setOpen] = useState(pathOpen);

  useEffect(() => {
    setOpen(pathOpen);
  }, [pathOpen]);

  if (!kids.length) {
    return (
      <Link
        className={navItemClass(selfActive, compact)}
        href={zoneFolderHref(categoryIndex, folder.id)}
        style={depth ? { marginLeft: Math.min(depth, 3) * 8 } : undefined}
      >
        {folder.name}
      </Link>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className={clsx(
            "flex shrink-0 items-center justify-center rounded-lg text-default-400 hover:bg-primary/[0.06] hover:text-primary",
            compact ? "h-10 w-10" : "h-7 w-7",
          )}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronRightIcon
            className={`transition-transform ${open ? "rotate-90" : ""}`}
            size={compact ? 16 : 14}
          />
        </button>
        <Link
          className={clsx(
            "min-w-0 flex-1 truncate rounded-xl px-1.5 transition-colors",
            compact ? "py-2.5 text-[14px]" : "py-1.5 text-[13px]",
            selfActive || childActive
              ? "font-semibold text-primary"
              : "text-default-700 hover:text-primary dark:text-slate-200",
          )}
          href={zoneFolderHref(categoryIndex, folder.id)}
        >
          {folder.name}
        </Link>
      </div>
      {open ? (
        <div className="ml-3 flex flex-col gap-0.5 border-l border-primary/15 pl-2 dark:border-primary/20">
          {kids.map((k) => (
            <ZoneSidebarNode
              key={k.id}
              activeFolderId={activeFolderId}
              categoryIndex={categoryIndex}
              compact={compact}
              depth={depth + 1}
              folder={k}
              folders={folders}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ZoneFolderSidebar({
  categoryIndex,
  activeFid,
  compact = false,
}: {
  categoryIndex: number;
  activeFid?: string;
  compact?: boolean;
}) {
  const initial = useContext(ZoneFoldersCtx);
  const [store, setStore] = useState<ZoneFoldersStore | null>(initial);
  const activeFolderId = parseZoneActiveFid(activeFid);

  const reload = useCallback(async () => {
    try {
      const res = await fetch("/api/zone-folders", { cache: "no-store" });
      const json = await res.json();
      if (res.ok && json.status === 200) {
        setStore(json.data as ZoneFoldersStore);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (initial) setStore(initial);
  }, [initial]);

  useEffect(() => {
    void reload();
    const onChanged = () => void reload();
    window.addEventListener("zone-folders-changed", onChanged);
    return () => window.removeEventListener("zone-folders-changed", onChanged);
  }, [reload]);

  const roots = useMemo(
    () => listChildren(store?.folders || [], null).filter((f) => !isSearchItem(f)),
    [store],
  );

  if (!store) {
    return (
      <p className={clsx("px-2.5 text-default-400", compact ? "text-[13px]" : "text-[12px]")}>
        加载目录…
      </p>
    );
  }

  if (!roots.length) {
    return (
      <p className={clsx("px-2.5 text-default-400", compact ? "text-[13px]" : "text-[12px]")}>
        暂无内容
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      {roots.map((folder) => (
        <ZoneSidebarNode
          key={folder.id}
          activeFolderId={activeFolderId}
          categoryIndex={categoryIndex}
          compact={compact}
          depth={0}
          folder={folder}
          folders={store.folders}
        />
      ))}
    </div>
  );
}
