"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Button,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Select,
  SelectItem,
} from "@nextui-org/react";
import clsx from "clsx";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import {
  collectDescendantIds,
  folderAncestors,
  isFolderItem,
  isSearchItem,
  listChildren,
  type ZoneFolder,
  type ZoneFoldersStore,
  type ZoneItemKind,
  zoneFolderHref,
} from "@/lib/zoneFolderModel";
import { Toast } from "@/utils/Toast";

type DialogMode =
  | { type: "create"; kind: ZoneItemKind }
  | { type: "rename"; folder: ZoneFolder }
  | { type: "keyword"; folder: ZoneFolder }
  | { type: "delete"; folder: ZoneFolder }
  | { type: "move"; folder: ZoneFolder }
  | null;

async function fetchStore(): Promise<ZoneFoldersStore> {
  const res = await fetch("/api/zone-folders", { cache: "no-store" });
  const json = await res.json();
  if (!res.ok || json.status !== 200) {
    throw new Error(json.message || "加载目录失败");
  }
  return json.data as ZoneFoldersStore;
}

function notifyChanged() {
  window.dispatchEvent(new Event("zone-folders-changed"));
}

/** 目录浏览：只渲染文件夹内容列表；当前若是搜索项则只显示工具条 */
export function ZoneFolderPanel({
  categoryIndex,
  folderId = null,
  searchMode = false,
}: {
  categoryIndex: number;
  folderId?: string | null;
  searchMode?: boolean;
}) {
  const router = useRouter();
  const importRef = useRef<HTMLInputElement>(null);
  const [store, setStore] = useState<ZoneFoldersStore | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [moveParentId, setMoveParentId] = useState<string>("__root__");
  const [menuId, setMenuId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  useEffect(() => {
    if (!menuId) return;
    const onDoc = () => setMenuId(null);
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, [menuId]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setStore(await fetchStore());
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const folders = store?.folders || [];
  const current = folderId
    ? folders.find((f) => f.id === folderId)
    : undefined;
  const children = useMemo(
    () => listChildren(folders, folderId ?? null),
    [folders, folderId],
  );
  const crumbs = useMemo(() => {
    if (!folderId) return [];
    return folderAncestors(folders, folderId).filter(
      (c) => isFolderItem(c) || c.id === folderId,
    );
  }, [folders, folderId]);

  const moveTargets = useMemo(() => {
    if (!dialog || dialog.type !== "move") return [];
    const blocked = collectDescendantIds(folders, dialog.folder.id);
    blocked.add(dialog.folder.id);
    return folders.filter((f) => isFolderItem(f) && !blocked.has(f.id));
  }, [dialog, folders]);

  const missing = Boolean(folderId && store && !current);

  useEffect(() => {
    if (missing) {
      router.replace(zoneFolderHref(categoryIndex));
    }
  }, [missing, router, categoryIndex]);

  const openCreate = (kind: ZoneItemKind) => {
    setNameDraft("");
    setKeywordDraft("");
    setDialog({ type: "create", kind });
  };

  const openRename = (folder: ZoneFolder) => {
    setMenuId(null);
    setNameDraft(folder.name);
    setDialog({ type: "rename", folder });
  };

  const openKeyword = (folder: ZoneFolder) => {
    setMenuId(null);
    setKeywordDraft(folder.searchKeyword);
    setDialog({ type: "keyword", folder });
  };

  const openDelete = (folder: ZoneFolder) => {
    setMenuId(null);
    setDialog({ type: "delete", folder });
  };

  const openMove = (folder: ZoneFolder) => {
    setMenuId(null);
    setMoveParentId(folder.parentId || "__root__");
    setDialog({ type: "move", folder });
  };

  const submitDialog = async () => {
    if (!dialog || busy) return;
    setBusy(true);
    try {
      if (dialog.type === "create") {
        const name = nameDraft.trim();
        if (!name) {
          Toast.error(dialog.kind === "search" ? "请输入名称" : "请输入文件夹名称");
          return;
        }
        if (dialog.kind === "search" && !keywordDraft.trim()) {
          Toast.error("请填写搜索关键词");
          return;
        }
        const res = await fetch("/api/zone-folders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            parentId: folderId ?? null,
            kind: dialog.kind,
            searchKeyword: dialog.kind === "search" ? keywordDraft.trim() : "",
          }),
        });
        const json = await res.json();
        if (!res.ok || json.status !== 200) throw new Error(json.message || "创建失败");
        setStore(json.data.store);
        Toast.success(dialog.kind === "search" ? "已创建搜索" : "已创建文件夹");
        setDialog(null);
        notifyChanged();
        return;
      }

      if (dialog.type === "rename") {
        const name = nameDraft.trim();
        if (!name) {
          Toast.error("请输入名称");
          return;
        }
        const res = await fetch(`/api/zone-folders/${dialog.folder.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        const json = await res.json();
        if (!res.ok || json.status !== 200) throw new Error(json.message || "重命名失败");
        setStore(json.data.store);
        Toast.success("已重命名");
        setDialog(null);
        notifyChanged();
        return;
      }

      if (dialog.type === "keyword") {
        const kw = keywordDraft.trim();
        if (!kw) {
          Toast.error("请填写搜索关键词");
          return;
        }
        const res = await fetch(`/api/zone-folders/${dialog.folder.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ searchKeyword: kw }),
        });
        const json = await res.json();
        if (!res.ok || json.status !== 200) throw new Error(json.message || "保存失败");
        setStore(json.data.store);
        Toast.success("已更新关键词");
        setDialog(null);
        notifyChanged();
        router.refresh();
        return;
      }

      if (dialog.type === "delete") {
        const res = await fetch(`/api/zone-folders/${dialog.folder.id}`, {
          method: "DELETE",
        });
        const json = await res.json();
        if (!res.ok || json.status !== 200) throw new Error(json.message || "删除失败");
        setStore(json.data.store);
        Toast.success("已删除");
        setDialog(null);
        notifyChanged();
        if (folderId === dialog.folder.id) {
          router.push(zoneFolderHref(categoryIndex, dialog.folder.parentId));
        } else {
          router.refresh();
        }
        return;
      }

      if (dialog.type === "move") {
        const parentId = moveParentId === "__root__" ? null : moveParentId;
        if (parentId === dialog.folder.parentId) {
          setDialog(null);
          return;
        }
        const res = await fetch(`/api/zone-folders/${dialog.folder.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ parentId }),
        });
        const json = await res.json();
        if (!res.ok || json.status !== 200) throw new Error(json.message || "移动失败");
        setStore(json.data.store);
        Toast.success("已移动");
        setDialog(null);
        notifyChanged();
      }
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const persistOrder = async (ordered: ZoneFolder[]) => {
    const orderedIds = ordered.map((f) => f.id);
    const optimistic = folders.map((f) => {
      const idx = orderedIds.indexOf(f.id);
      return idx >= 0 ? { ...f, sortOrder: idx } : f;
    });
    setStore((prev) =>
      prev ? { ...prev, folders: optimistic } : prev,
    );
    try {
      const res = await fetch("/api/zone-folders/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parentId: folderId ?? null,
          orderedIds,
        }),
      });
      const json = await res.json();
      if (!res.ok || json.status !== 200) throw new Error(json.message || "排序失败");
      setStore(json.data.store);
      notifyChanged();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "排序失败");
      void reload();
    }
  };

  const onDropReorder = (targetId: string) => {
    if (!dragId || dragId === targetId) {
      setDragId(null);
      setOverId(null);
      return;
    }
    const next = children.slice();
    const from = next.findIndex((f) => f.id === dragId);
    const to = next.findIndex((f) => f.id === targetId);
    if (from < 0 || to < 0) {
      setDragId(null);
      setOverId(null);
      return;
    }
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setDragId(null);
    setOverId(null);
    void persistOrder(next);
  };

  const exportTree = () => {
    if (!store) return;
    const blob = new Blob([JSON.stringify(store, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `zone-folders-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    Toast.success("已导出");
  };

  const onImportFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as { folders?: unknown[] } | unknown[];
      const foldersRaw = Array.isArray(parsed)
        ? parsed
        : Array.isArray((parsed as { folders?: unknown[] }).folders)
          ? (parsed as { folders: unknown[] }).folders
          : null;
      if (!foldersRaw) throw new Error("文件格式不对");
      if (
        !window.confirm(
          `导入将覆盖当前 ${folders.length} 项目录，确定继续？`,
        )
      ) {
        return;
      }
      setBusy(true);
      const res = await fetch("/api/zone-folders", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folders: foldersRaw }),
      });
      const json = await res.json();
      if (!res.ok || json.status !== 200) throw new Error(json.message || "导入失败");
      setStore(json.data);
      Toast.success(json.message || "已导入");
      notifyChanged();
      router.push(zoneFolderHref(categoryIndex));
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const dialogTitle =
    dialog?.type === "create"
      ? dialog.kind === "search"
        ? "新建搜索"
        : "新建文件夹"
      : dialog?.type === "rename"
        ? "重命名"
        : dialog?.type === "keyword"
          ? "修改关键词"
          : dialog?.type === "delete"
            ? "确认删除"
            : dialog?.type === "move"
              ? "移动到"
              : "";

  const pathCrumbs = crumbs.filter((c) => isFolderItem(c));

  const renderItemMenu = (item: ZoneFolder) => (
    <div
      className="absolute right-0 top-9 z-30 min-w-[8.75rem] overflow-hidden rounded-xl border border-default-200/80 bg-white/95 py-1 shadow-card backdrop-blur-md dark:border-slate-600 dark:bg-slate-800/95"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="block w-full px-3 py-2 text-left text-[13px] hover:bg-primary/10"
        onClick={() => openRename(item)}
      >
        重命名
      </button>
      {isSearchItem(item) ? (
        <button
          type="button"
          className="block w-full px-3 py-2 text-left text-[13px] hover:bg-primary/10"
          onClick={() => openKeyword(item)}
        >
          改关键词
        </button>
      ) : null}
      <button
        type="button"
        className="block w-full px-3 py-2 text-left text-[13px] hover:bg-primary/10"
        onClick={() => openMove(item)}
      >
        移动到…
      </button>
      <button
        type="button"
        className="block w-full px-3 py-2 text-left text-[13px] text-danger hover:bg-danger/10"
        onClick={() => openDelete(item)}
      >
        删除
      </button>
    </div>
  );

  return (
    <div className="zone-drive">
      <div
        className={clsx(
          "zone-drive__shell overflow-hidden rounded-2xl border border-default-200/55 bg-white/88 shadow-soft backdrop-blur-md",
          "dark:border-slate-700/55 dark:bg-slate-900/75",
          searchMode && "zone-drive__shell--search",
        )}
      >
        <div className="zone-drive__toolbar flex flex-wrap items-center justify-between gap-2 border-b border-default-100/90 px-3 py-2.5 sm:gap-3 sm:px-3.5 dark:border-slate-700/50">
          <nav
            aria-label="目录路径"
            className="zone-drive__path flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto text-[13px]"
          >
            <Link
              className={clsx(
                "zone-drive__crumb shrink-0 rounded-lg px-2 py-1 transition-colors",
                !folderId
                  ? "bg-primary/12 font-semibold text-primary"
                  : "text-default-500 hover:bg-default-100/80 hover:text-foreground dark:hover:bg-slate-800",
              )}
              href={zoneFolderHref(categoryIndex)}
            >
              全部
            </Link>
            {pathCrumbs.map((c) => (
              <span key={c.id} className="inline-flex min-w-0 shrink-0 items-center gap-0.5">
                <ChevronRightIcon className="shrink-0 text-default-300/80" size={13} />
                <Link
                  className={clsx(
                    "zone-drive__crumb max-w-[9rem] truncate rounded-lg px-2 py-1 transition-colors",
                    c.id === folderId
                      ? "bg-primary/12 font-semibold text-primary"
                      : "text-default-500 hover:bg-default-100/80 hover:text-foreground dark:hover:bg-slate-800",
                  )}
                  href={zoneFolderHref(categoryIndex, c.id)}
                >
                  {c.name}
                </Link>
              </span>
            ))}
            {current && isSearchItem(current) ? (
              <span className="inline-flex min-w-0 shrink-0 items-center gap-0.5">
                <ChevronRightIcon className="shrink-0 text-default-300/80" size={13} />
                <span className="max-w-[10rem] truncate rounded-lg bg-sky-500/12 px-2 py-1 font-semibold text-sky-700 dark:bg-sky-400/15 dark:text-sky-300">
                  {current.name}
                </span>
              </span>
            ) : null}
            {!searchMode && !loading && children.length > 0 ? (
              <span className="ml-1.5 hidden shrink-0 rounded-full bg-default-100/90 px-2 py-0.5 text-[11px] tabular-nums text-default-400 dark:bg-slate-800 sm:inline">
                {children.length}
              </span>
            ) : null}
          </nav>

          <div className="zone-drive__actions flex shrink-0 flex-wrap items-center gap-1 sm:gap-1.5">
            {searchMode && current && isSearchItem(current) ? (
              <div className="relative">
                <button
                  type="button"
                  aria-label="更多操作"
                  className="zone-drive__icon-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuId((id) => (id === current.id ? null : current.id));
                  }}
                >
                  <MoreGlyph />
                </button>
                {menuId === current.id ? renderItemMenu(current) : null}
              </div>
            ) : null}

            {!searchMode ? (
              <>
                <div className="zone-drive__action-group hidden items-center sm:flex">
                  <button
                    type="button"
                    className="zone-drive__text-btn"
                    disabled={busy || loading || !store}
                    onClick={exportTree}
                  >
                    导出
                  </button>
                  <span aria-hidden className="zone-drive__action-sep" />
                  <button
                    type="button"
                    className="zone-drive__text-btn"
                    disabled={busy || loading}
                    onClick={() => importRef.current?.click()}
                  >
                    导入
                  </button>
                </div>
                <input
                  ref={importRef}
                  type="file"
                  accept="application/json,.json"
                  className="hidden"
                  onChange={(e) => void onImportFile(e.target.files?.[0])}
                />
                {current && isFolderItem(current) ? (
                  <div className="relative">
                    <button
                      type="button"
                      aria-label="文件夹操作"
                      className="zone-drive__icon-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuId((id) => (id === current.id ? null : current.id));
                      }}
                    >
                      <MoreGlyph />
                    </button>
                    {menuId === current.id ? renderItemMenu(current) : null}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="zone-drive__btn zone-drive__btn--ghost"
                  disabled={busy || loading}
                  onClick={() => openCreate("search")}
                >
                  <SearchGlyph />
                  <span>新建搜索</span>
                </button>
                <button
                  type="button"
                  className="zone-drive__btn zone-drive__btn--primary"
                  disabled={busy || loading}
                  onClick={() => openCreate("folder")}
                >
                  <FolderGlyph />
                  <span>新建文件夹</span>
                </button>
              </>
            ) : null}
          </div>
        </div>

        {searchMode ? null : loading ? (
          <div className="zone-drive__panel flex flex-col">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-3.5 py-3"
                style={{ opacity: 1 - i * 0.18 }}
              >
                <span className="h-9 w-9 shrink-0 animate-pulse rounded-xl bg-default-200/60 dark:bg-slate-700/60" />
                <span className="h-3 max-w-[36%] flex-1 animate-pulse rounded-md bg-default-200/60 dark:bg-slate-700/60" />
              </div>
            ))}
          </div>
        ) : children.length === 0 ? (
          <div className="zone-drive__empty flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
            <span className="zone-drive__empty-icon flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 ring-1 ring-inset ring-primary/15">
              <FolderGlyph />
            </span>
            <div className="max-w-xs space-y-1">
              <p className="text-sm font-semibold text-foreground">
                {folderId ? "此文件夹是空的" : "还没有内容"}
              </p>
              <p className="text-xs leading-relaxed text-default-400">
                {folderId
                  ? "新建子文件夹分类，或新建搜索一点即查。"
                  : "文件夹用来分类，搜索用来直达结果；可拖拽排序。"}
              </p>
            </div>
            <div className="mt-1 flex gap-2">
              <button
                type="button"
                className="zone-drive__btn zone-drive__btn--ghost"
                onClick={() => openCreate("search")}
              >
                <SearchGlyph />
                <span>新建搜索</span>
              </button>
              <button
                type="button"
                className="zone-drive__btn zone-drive__btn--primary"
                onClick={() => openCreate("folder")}
              >
                <FolderGlyph />
                <span>新建文件夹</span>
              </button>
            </div>
          </div>
        ) : (
          <ul className="zone-drive__panel list-none">
            {children.map((item, index) => {
              const isSearch = isSearchItem(item);
              const childCount = isSearch
                ? 0
                : listChildren(folders, item.id).length;
              const subtitle = isSearch
                ? null
                : childCount > 0
                  ? `${childCount} 项`
                  : "空";

              return (
                <li
                  key={item.id}
                  draggable
                  className={clsx(
                    "zone-drive__row group relative",
                    dragId === item.id && "zone-drive__row--dragging",
                    overId === item.id && "zone-drive__row--over",
                  )}
                  style={{ animationDelay: `${index * 0.028}s` }}
                  onDragStart={(e) => {
                    setDragId(item.id);
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", item.id);
                  }}
                  onDragEnd={() => {
                    setDragId(null);
                    setOverId(null);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (dragId && dragId !== item.id) setOverId(item.id);
                  }}
                  onDragLeave={() => {
                    if (overId === item.id) setOverId(null);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    onDropReorder(item.id);
                  }}
                >
                  <Link
                    className="zone-drive__link flex min-h-[3.15rem] items-center gap-2 py-2 pl-2 pr-11 sm:gap-2.5 sm:pl-2.5 sm:pr-12"
                    href={zoneFolderHref(categoryIndex, item.id)}
                    onClick={(e) => {
                      if (dragId) e.preventDefault();
                    }}
                  >
                    <span
                      aria-hidden
                      className="zone-drive__grip"
                      title="拖拽排序"
                    >
                      <GripGlyph />
                    </span>
                    <span
                      aria-hidden
                      className={clsx(
                        "zone-drive__icon",
                        isSearch
                          ? "zone-drive__icon--search"
                          : "zone-drive__icon--folder",
                      )}
                    >
                      {isSearch ? <SearchGlyph /> : <FolderGlyph />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="zone-drive__name truncate text-[14px] font-semibold tracking-wide text-foreground sm:text-[15px]">
                        {item.name}
                      </h2>
                      {subtitle ? (
                        <p className="zone-drive__meta mt-0.5 truncate text-[11px] text-default-400 sm:text-xs">
                          {subtitle}
                        </p>
                      ) : null}
                    </div>
                    <ChevronRightIcon
                      className="zone-drive__chevron mr-0.5 shrink-0 text-default-300"
                      size={15}
                    />
                  </Link>

                  <div className="absolute right-1.5 top-1/2 z-10 -translate-y-1/2 sm:right-2">
                    <button
                      type="button"
                      aria-label="更多操作"
                      aria-expanded={menuId === item.id}
                      className={clsx(
                        "zone-drive__icon-btn zone-drive__more",
                        menuId === item.id && "zone-drive__icon-btn--active",
                      )}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setMenuId((id) => (id === item.id ? null : item.id));
                      }}
                    >
                      <MoreGlyph />
                    </button>
                    {menuId === item.id ? renderItemMenu(item) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <Modal
        isOpen={Boolean(dialog)}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        placement="center"
        size="sm"
      >
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader className="text-sm">{dialogTitle}</ModalHeader>
              <ModalBody className="gap-3">
                {dialog?.type === "delete" ? (
                  <p className="text-sm text-default-600">
                    {isSearchItem(dialog.folder)
                      ? `删除搜索「${dialog.folder.name}」？`
                      : `删除「${dialog.folder.name}」及其全部内容？此操作不可恢复。`}
                  </p>
                ) : null}
                {dialog?.type === "move" ? (
                  <Select
                    label="目标文件夹"
                    labelPlacement="outside"
                    selectedKeys={[moveParentId]}
                    size="sm"
                    onChange={(e) => setMoveParentId(e.target.value || "__root__")}
                  >
                    <SelectItem key="__root__">全部（根目录）</SelectItem>
                    {moveTargets.map((f) => (
                      <SelectItem key={f.id}>{f.name}</SelectItem>
                    ))}
                  </Select>
                ) : null}
                {dialog?.type === "create" || dialog?.type === "rename" ? (
                  <Input
                    autoFocus
                    label={
                      dialog.type === "create" && dialog.kind === "search"
                        ? "显示名称"
                        : "名称"
                    }
                    labelPlacement="outside"
                    placeholder={
                      dialog.type === "create" && dialog.kind === "search"
                        ? "例如：麻豆合集"
                        : "例如：合集精选"
                    }
                    size="sm"
                    value={nameDraft}
                    onValueChange={setNameDraft}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submitDialog();
                    }}
                  />
                ) : null}
                {(dialog?.type === "create" && dialog.kind === "search") ||
                dialog?.type === "keyword" ? (
                  <Input
                    autoFocus={dialog?.type === "keyword"}
                    label="搜索关键词"
                    labelPlacement="outside"
                    description="点击该项后按此关键词搜索资源库"
                    placeholder="例如：麻豆 或 FC2"
                    size="sm"
                    value={keywordDraft}
                    onValueChange={setKeywordDraft}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submitDialog();
                    }}
                  />
                ) : null}
              </ModalBody>
              <ModalFooter>
                <Button size="sm" variant="light" onPress={onClose}>
                  取消
                </Button>
                <Button
                  size="sm"
                  color={dialog?.type === "delete" ? "danger" : "primary"}
                  isLoading={busy}
                  onPress={() => void submitDialog()}
                >
                  {dialog?.type === "delete" ? "删除" : "确定"}
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>
    </div>
  );
}

function FolderGlyph() {
  return (
    <svg
      className="zone-drive__folder-svg"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        className="zone-drive__folder-tab"
        d="M3.5 7.25c0-.97.78-1.75 1.75-1.75h4.1c.4 0 .78.14 1.08.4l1.34 1.15c.3.26.68.4 1.08.4h6.9c.97 0 1.75.78 1.75 1.75v.35H3.5V7.25Z"
      />
      <path
        className="zone-drive__folder-body"
        d="M3.5 9.1h17c.83 0 1.5.67 1.5 1.5v7.15c0 1.24-1.01 2.25-2.25 2.25H4.25A2.25 2.25 0 0 1 2 17.75V10.6c0-.83.67-1.5 1.5-1.5Z"
      />
      <path
        className="zone-drive__folder-shine"
        d="M4.2 10.35h15.6c.3 0 .55.25.55.55v1.05c0 .1-.03.2-.1.28l-1.15 1.35a.75.75 0 0 1-.57.27H5.9a.75.75 0 0 1-.57-.27L4.25 12.23a.45.45 0 0 1-.1-.28v-1.05c0-.3.25-.55.55-.55Z"
        opacity="0.55"
      />
    </svg>
  );
}

function SearchGlyph() {
  return (
    <svg
      className="zone-drive__search-svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle
        className="zone-drive__search-ring"
        cx="10.5"
        cy="10.5"
        r="6.25"
        strokeWidth="2"
      />
      <path
        className="zone-drive__search-handle"
        d="M15.4 15.4 20 20"
        strokeWidth="2.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoreGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="12" cy="5" r="1.75" />
      <circle cx="12" cy="12" r="1.75" />
      <circle cx="12" cy="19" r="1.75" />
    </svg>
  );
}

function GripGlyph() {
  return (
    <svg width="12" height="16" viewBox="0 0 12 16" fill="currentColor" aria-hidden>
      <circle cx="3.5" cy="3" r="1.2" />
      <circle cx="8.5" cy="3" r="1.2" />
      <circle cx="3.5" cy="8" r="1.2" />
      <circle cx="8.5" cy="8" r="1.2" />
      <circle cx="3.5" cy="13" r="1.2" />
      <circle cx="8.5" cy="13" r="1.2" />
    </svg>
  );
}
