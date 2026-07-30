/** 综合区自定义目录（纯模型，可给客户端用） */

export type ZoneItemKind = "folder" | "search";

export type ZoneFolder = {
  id: string;
  parentId: string | null;
  name: string;
  /** folder=可进入的目录；search=点击直接搜索 */
  kind: ZoneItemKind;
  /** search 项必填；folder 为空 */
  searchKeyword: string;
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
};

export type ZoneFoldersStore = {
  version: 1;
  folders: ZoneFolder[];
  updatedAt: string;
};

export function isSearchItem(item: Pick<ZoneFolder, "kind" | "searchKeyword">): boolean {
  return item.kind === "search" || Boolean(item.searchKeyword?.trim());
}

export function isFolderItem(item: Pick<ZoneFolder, "kind" | "searchKeyword">): boolean {
  return !isSearchItem(item);
}

export function listChildren(
  folders: ZoneFolder[],
  parentId: string | null,
): ZoneFolder[] {
  return folders
    .filter((f) => f.parentId === parentId)
    .sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name, "zh"));
}

export function findFolder(
  folders: ZoneFolder[],
  id: string,
): ZoneFolder | undefined {
  const needle = String(id || "").trim();
  if (!needle) return undefined;
  return folders.find((f) => f.id === needle);
}

/** 根 → 当前，含当前节点（路径上跳过 search 叶子的展示由调用方处理） */
export function folderAncestors(
  folders: ZoneFolder[],
  id: string,
): ZoneFolder[] {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const chain: ZoneFolder[] = [];
  let cur = byId.get(String(id || "").trim());
  const guard = new Set<string>();
  while (cur) {
    if (guard.has(cur.id)) break;
    guard.add(cur.id);
    chain.unshift(cur);
    cur = cur.parentId ? byId.get(cur.parentId) : undefined;
  }
  return chain;
}

export function collectDescendantIds(
  folders: ZoneFolder[],
  rootId: string,
): Set<string> {
  const kids = new Map<string | null, string[]>();
  for (const f of folders) {
    const key = f.parentId;
    const list = kids.get(key) || [];
    list.push(f.id);
    kids.set(key, list);
  }
  const out = new Set<string>();
  const stack = [rootId];
  while (stack.length) {
    const id = stack.pop()!;
    if (out.has(id)) continue;
    out.add(id);
    for (const child of kids.get(id) || []) stack.push(child);
  }
  return out;
}

export function zoneFolderHref(
  categoryIndex: number,
  folderId?: string | null,
): string {
  const base = `/c/${categoryIndex}`;
  const id = String(folderId || "").trim();
  return id ? `${base}/f/${encodeURIComponent(id)}` : base;
}

export function zoneFolderActiveFid(folderId: string): string {
  return `zone:${String(folderId || "").trim()}`;
}

export function parseZoneActiveFid(fid?: string | null): string | null {
  const s = String(fid || "").trim();
  if (!s.startsWith("zone:")) return null;
  return s.slice(5) || null;
}

/** 分区名是否综合区（自定义文件夹模式） */
export function isZoneCustomCategory(name: string): boolean {
  return String(name || "").trim() === "综合区";
}
