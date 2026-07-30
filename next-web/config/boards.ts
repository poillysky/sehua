import boardsNavJson from "./boards.nav.json";

export type BoardNavChild = {
  key: string;
  fid: string;
  typeid: string;
  name: string;
  type_name: string;
  board_name: string;
  /** 网络标准番号前缀：走搜索，不按论坛 fid */
  search_keyword?: string;
};

export type BoardNavParent = {
  name: string;
  children: BoardNavChild[];
  /** 日本 → 有码/无码 等嵌套版块 */
  boards?: BoardNavParent[];
  /** 二级枢纽稳定 fid（可无 children，如国产有码空壳） */
  hub_fid?: string;
};

export type BoardNavCategory = {
  category: string;
  boards: BoardNavParent[];
};

export type BoardNavContext = {
  categoryIndex: number;
  category: BoardNavCategory;
  parent: BoardNavParent;
  /** 嵌套时的上层（如「日本」） */
  group?: BoardNavParent;
  child?: BoardNavChild;
};

/** 分区目录：仅本项目 `boards.nav.json`，与管理端无关 */
export const BOARD_NAV = boardsNavJson as BoardNavCategory[];

/** @deprecated 同 BOARD_NAV */
export const FALLBACK_BOARD_NAV = BOARD_NAV;

function asStr(v: unknown, fallback = ""): string {
  return String(v ?? fallback).trim();
}

function normalizeChild(
  ch: unknown,
  parentName: string,
): BoardNavChild | null {
  if (!ch || typeof ch !== "object") return null;
  let fid = asStr((ch as { fid?: unknown }).fid);
  let typeid = asStr((ch as { typeid?: unknown }).typeid);
  let key =
    asStr((ch as { key?: unknown }).key) ||
    (fid && typeid ? `${fid}:${typeid}` : "");
  const cname = asStr((ch as { name?: unknown }).name);
  if (!key || !cname) return null;
  if (key.includes(":") && (!fid || !typeid)) {
    const parts = key.split(":", 2);
    fid = fid || parts[0] || "";
    typeid = typeid || parts[1] || "";
  }
  return {
    key,
    fid,
    typeid,
    name: cname,
    type_name: asStr((ch as { type_name?: unknown }).type_name),
    board_name: asStr((ch as { board_name?: unknown }).board_name) || parentName,
    ...(asStr((ch as { search_keyword?: unknown }).search_keyword)
      ? {
          search_keyword: asStr(
            (ch as { search_keyword?: unknown }).search_keyword,
          ),
        }
      : {}),
  };
}

function normalizeParent(board: unknown): BoardNavParent | null {
  if (!board || typeof board !== "object") return null;
  const name = asStr((board as { name?: unknown }).name);
  if (!name) return null;

  const hubFid = asStr((board as { hub_fid?: unknown }).hub_fid);

  const childrenRaw = (board as { children?: unknown }).children;
  const children: BoardNavChild[] = [];
  if (Array.isArray(childrenRaw)) {
    for (const ch of childrenRaw) {
      const child = normalizeChild(ch, name);
      if (child) children.push(child);
    }
  }

  const nestedRaw = (board as { boards?: unknown }).boards;
  const nested: BoardNavParent[] = [];
  if (Array.isArray(nestedRaw)) {
    for (const nb of nestedRaw) {
      const parent = normalizeParent(nb);
      if (parent) nested.push(parent);
    }
  }

  // 允许空壳二级（如国产有码）仅靠 hub_fid 占位
  if (!children.length && !nested.length && !hubFid) return null;
  return {
    name,
    children,
    ...(nested.length ? { boards: nested } : {}),
    ...(hubFid ? { hub_fid: hubFid } : {}),
  };
}

/** 规范化分区目录；非法项丢弃。 */
export function normalizeBoardNav(raw: unknown): BoardNavCategory[] {
  let data = raw;
  if (typeof data === "string") {
    const text = data.trim();
    if (!text) return [];
    try {
      data = JSON.parse(text);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(data)) return [];

  const out: BoardNavCategory[] = [];
  for (const cat of data) {
    if (!cat || typeof cat !== "object") continue;
    const category = asStr((cat as { category?: unknown }).category);
    const boardsRaw = (cat as { boards?: unknown }).boards;
    if (!category || !Array.isArray(boardsRaw)) continue;

    const boards: BoardNavParent[] = [];
    for (const board of boardsRaw) {
      const parent = normalizeParent(board);
      if (parent) boards.push(parent);
    }
    // 允许空 boards（综合区=用户自定义文件夹，无静态版块）
    out.push({ category, boards });
  }
  return out;
}

/** 展开嵌套版块（保留 group 引用） */
export function walkParents(
  cat: BoardNavCategory,
  categoryIndex: number,
): Array<{ parent: BoardNavParent; group?: BoardNavParent; categoryIndex: number }> {
  const out: Array<{
    parent: BoardNavParent;
    group?: BoardNavParent;
    categoryIndex: number;
  }> = [];
  for (const board of cat.boards) {
    if (board.boards?.length) {
      for (const nested of board.boards) {
        out.push({ parent: nested, group: board, categoryIndex });
      }
    } else {
      out.push({ parent: board, categoryIndex });
    }
  }
  return out;
}

export function parseBoardKey(
  key: string,
): { fid: string; typeid: string } | null {
  const raw = (key || "").trim();
  if (!raw) return null;
  const idx = raw.indexOf(":");
  if (idx <= 0) return null;
  const fid = raw.slice(0, idx).trim();
  const typeid = raw.slice(idx + 1).trim();
  if (!fid || !typeid) return null;
  return { fid, typeid };
}

export function makeBoardKey(fid: string, typeid: string): string {
  return `${String(fid).trim()}:${String(typeid).trim()}`;
}

export function categoryPath(index: number): string {
  return `/c/${Math.max(0, Math.floor(index))}`;
}

export function boardPath(fid: string): string {
  return `/b/${encodeURIComponent(String(fid).trim())}`;
}

export function boardAllPath(fid: string): string {
  return `/b/${encodeURIComponent(String(fid).trim())}/all`;
}

export function subtypePath(fid: string, typeid: string): string {
  return `/b/${encodeURIComponent(String(fid).trim())}/t/${encodeURIComponent(String(typeid).trim())}`;
}

export function findCategory(
  index: number,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): BoardNavCategory | undefined {
  if (!Number.isFinite(index) || index < 0 || index >= nav.length) {
    return undefined;
  }
  return nav[index];
}

export function findCategoryIndexByName(
  name: string,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): number {
  const needle = (name || "").trim();
  if (!needle) return -1;
  return nav.findIndex((c) => c.category === needle);
}

export function findBoardChild(
  key: string,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): BoardNavChild | undefined {
  const needle = (key || "").trim();
  if (!needle) return undefined;
  for (let ci = 0; ci < nav.length; ci++) {
    for (const { parent } of walkParents(nav[ci], ci)) {
      const hit = parent.children.find((c) => c.key === needle);
      if (hit) return hit;
    }
  }
  return undefined;
}

/** 按版块 fid 找父版块（取第一个匹配；`107~三级` 可精确到父名）。 */
export function findByFid(
  fid: string,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): BoardNavContext | undefined {
  const raw = String(fid || "").trim();
  if (!raw) return undefined;
  const { baseFid: needle, parentName } = parseSharedParentFid(raw);
  if (!needle) return undefined;

  // 三大片区枢纽（同级）：日本 / 国产 / 欧美
  const regionHubName: Record<string, string> = {
    "mk-japan": "日本",
    "mk-china-hub": "国产",
    "mk-western-hub": "欧美",
  };
  const regionName = regionHubName[needle];
  if (regionName) {
    for (let ci = 0; ci < nav.length; ci++) {
      const cat = nav[ci];
      const hub = cat.boards.find((b) => b.name === regionName);
      if (hub) {
        return { categoryIndex: ci, category: cat, parent: hub };
      }
    }
  }

  for (let ci = 0; ci < nav.length; ci++) {
    const cat = nav[ci];
    for (const { parent, group } of walkParents(cat, ci)) {
      if (parent.hub_fid && parent.hub_fid === needle) {
        if (parentName && parent.name !== parentName) continue;
        return { categoryIndex: ci, category: cat, parent, group };
      }
      if (parent.children.some((c) => c.fid === needle)) {
        if (parentName && parent.name !== parentName) continue;
        return { categoryIndex: ci, category: cat, parent, group };
      }
    }
  }
  return undefined;
}

export function findSubtype(
  fid: string,
  typeid: string,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): BoardNavContext | undefined {
  const f = String(fid || "").trim();
  let t = String(typeid || "").trim();
  if (!f || !t) return undefined;

  // 无码旧别名入口 → 主前缀（收口冗余写法后保留书签兼容）
  if (f === "mk-uncensored") {
    const alias: Record<string, string> = {
      caribbean: "CARIB",
      caribbeancom: "CARIB",
      "1pondo": "1PON",
      pacopacomama: "PACO",
      "10musume": "10MU",
    };
    const mapped = alias[t.toLowerCase()];
    if (mapped) t = mapped;
  }

  const key = makeBoardKey(f, t);
  for (let ci = 0; ci < nav.length; ci++) {
    const cat = nav[ci];
    for (const { parent, group } of walkParents(cat, ci)) {
      const child = parent.children.find(
        (c) => c.key === key || (c.fid === f && c.typeid === t),
      );
      if (child) {
        return { categoryIndex: ci, category: cat, parent, group, child };
      }
    }
  }
  return undefined;
}

export function parentFid(
  parent: BoardNavParent,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): string {
  // 三大片区同级枢纽
  if (parent.name === "日本") return "mk-japan";
  if (parent.name === "国产") return "mk-china-hub";
  if (parent.name === "欧美") return "mk-western-hub";
  if (parent.hub_fid) return parent.hub_fid.trim();
  if (parent.boards?.length) {
    return "mk-japan";
  }
  const base = (parent.children[0]?.fid || "").trim();
  if (!base) return "";
  // 多个父版块共用同一论坛 fid（如三级/写真 → 107）时区分路径
  if (sharedForumFidCount(base, nav) > 1) {
    return `${base}${SHARED_FID_SEP}${parent.name}`;
  }
  return base;
}

export function isPrefixBoard(parent: BoardNavParent): boolean {
  return (
    parent.children.length > 0 &&
    parent.children.every((c) => Boolean(c.search_keyword))
  );
}

export function isGroupBoard(parent: BoardNavParent): boolean {
  return Boolean(parent.boards?.length);
}

/** 旧论坛 fid → 新导航（仅已撤出独立浏览入口的板） */
const LEGACY_FID_REDIRECT: Record<string, string> = {
  "2": "/b/mk-china-hub",
  "38": "/b/mk-western-hub",
  "36": "/b/mk-uncensored",
  "37": "/b/mk-censored",
  "104": "/b/mk-censored",
  // 103/39/151/160 已从影视区移除，旧书签回分区首页
  "103": "/c/2",
  "39": "/c/2",
  "151": "/c/2",
  "160": "/c/2",
  // 注意：107（三级/写真）必须可进 /b/107/t/...，勿再重定向到 /c/2
};

/** 同论坛 fid 被多个父版块共用时，父级路径用 `fid~父名` 区分 */
const SHARED_FID_SEP = "~";

export function forumBaseFid(fid: string): string {
  const needle = String(fid || "").trim();
  const i = needle.indexOf(SHARED_FID_SEP);
  return i >= 0 ? needle.slice(0, i) : needle;
}

function parseSharedParentFid(fid: string): { baseFid: string; parentName: string } {
  const needle = String(fid || "").trim();
  const i = needle.indexOf(SHARED_FID_SEP);
  if (i < 0) return { baseFid: needle, parentName: "" };
  return {
    baseFid: needle.slice(0, i),
    parentName: needle.slice(i + SHARED_FID_SEP.length),
  };
}

function sharedForumFidCount(
  forumFid: string,
  nav: BoardNavCategory[],
): number {
  const needle = String(forumFid || "").trim();
  if (!needle) return 0;
  let n = 0;
  for (const cat of nav) {
    for (const parent of cat.boards) {
      if (parent.children?.some((c) => c.fid === needle)) n += 1;
    }
  }
  return n;
}

export function legacyFidRedirect(fid: string): string | null {
  const needle = forumBaseFid(fid);
  if (!needle) return null;
  // 带 ~ 的父级路径不是旧书签
  if (String(fid || "").includes(SHARED_FID_SEP)) return null;
  return LEGACY_FID_REDIRECT[needle] || null;
}

/** 子类：论坛板走 /b/.../t/...；番号前缀走编号索引页 */
export function boardBrowseHref(child: BoardNavChild): string {
  return subtypePath(child.fid, child.typeid || child.key.split(":")[1] || "");
}

/** 番号前缀 → 精确搜索全部（索引页「搜索全部」用） */
export function prefixSearchAllHref(child: BoardNavChild): string {
  const kw = (child.search_keyword || child.type_name || "").trim();
  if (!kw) return boardBrowseHref(child);
  const params = new URLSearchParams();
  params.set("keyword", kw);
  params.set("matchMode", "exact");
  return `/search?${params.toString()}`;
}

/** 版块页（子类目录） */
export function boardParentBrowseHref(parent: BoardNavParent): string {
  const fid = parentFid(parent);
  if (fid) return boardPath(fid);
  const params = new URLSearchParams();
  params.set("board_parent", parent.name);
  return `/browse?${params.toString()}`;
}

/** 版块下全部：番号片商用片商名搜索 */
export function boardAllResourcesHref(parent: BoardNavParent): string {
  const first = parent.children[0];
  if (first?.search_keyword) {
    const params = new URLSearchParams();
    params.set("keyword", parent.name);
    return `/search?${params.toString()}`;
  }
  const fid = parentFid(parent);
  if (fid) return boardAllPath(fid);
  return boardParentBrowseHref(parent);
}

export function categoryHref(index: number): string {
  return categoryPath(index);
}

/**
 * 分区层级后退目标（非浏览器历史）：
 * 子类/前缀 → 版块 →（日本枢纽）→ 片区 → 首页
 */
export function resolveSectionParentHref(pathname: string): string {
  const raw = String(pathname || "/").split("?")[0].trim();
  const path = (raw.replace(/\/+$/, "") || "/") as string;
  if (path === "/") return "/";

  const cat = path.match(/^\/c\/(\d+)$/);
  if (cat) return "/";

  const subtype = path.match(/^\/b\/([^/]+)\/t\/([^/]+)$/);
  if (subtype) {
    return boardPath(decodeURIComponent(subtype[1]));
  }

  const all = path.match(/^\/b\/([^/]+)\/all$/);
  if (all) {
    return boardPath(decodeURIComponent(all[1]));
  }

  const board = path.match(/^\/b\/([^/]+)$/);
  if (board) {
    const fid = decodeURIComponent(board[1]);
    const ctx = findByFid(fid);
    if (!ctx) return "/";
    if (ctx.group) return boardParentBrowseHref(ctx.group);
    return categoryHref(ctx.categoryIndex);
  }

  return "/";
}

/** 是否日本分区（有码/无码/厂商前缀等）；中文·破解偏好仅此范围 */
export function isJapanBrowseContext(
  fid?: string | null,
  typeid?: string | null,
): boolean {
  const f = String(fid || "").trim();
  if (!f) return false;
  if (f === "mk-japan" || f === "mk-censored" || f === "mk-uncensored") {
    return true;
  }
  const t = String(typeid || "").trim();
  const ctx = t ? findSubtype(f, t) || findByFid(f) : findByFid(f);
  if (!ctx) return false;
  return ctx.parent.name === "日本" || ctx.group?.name === "日本";
}

/** 浏览壳：由 pathname 推导高亮 / 面包屑 / 手机铺满（壳放 layout 防闪） */
export type BrowseShellState = {
  crumbs: { label: string; href?: string }[];
  activeFid?: string;
  activeTypeid?: string;
  activeCategoryIndex?: number;
  fillMobile: boolean;
  japanPrefs: boolean;
  /** 末屑用 i18n key（如 Boards.all_children） */
  crumbTailKey?: string;
};

export function resolveBrowseShellState(
  pathname: string,
): BrowseShellState | null {
  const raw = String(pathname || "/").split("?")[0].trim();
  const path = (raw.replace(/\/+$/, "") || "/") as string;

  const catFolder = path.match(/^\/c\/(\d+)\/f\/([^/]+)$/);
  if (catFolder) {
    const index = Number(catFolder[1]);
    const category = findCategory(index);
    if (!category) return null;
    const folderId = decodeURIComponent(catFolder[2]);
    return {
      crumbs: [{ label: category.category, href: categoryHref(index) }],
      activeCategoryIndex: index,
      activeFid: `zone:${folderId}`,
      fillMobile: false,
      japanPrefs: false,
    };
  }

  const cat = path.match(/^\/c\/(\d+)$/);
  if (cat) {
    const index = Number(cat[1]);
    const category = findCategory(index);
    if (!category) return null;
    return {
      crumbs: [{ label: category.category }],
      activeCategoryIndex: index,
      fillMobile: false,
      japanPrefs: false,
    };
  }

  const all = path.match(/^\/b\/([^/]+)\/all$/);
  if (all) {
    const fid = decodeURIComponent(all[1]);
    const ctx = findByFid(fid);
    if (!ctx) return null;
    return {
      crumbs: [
        {
          label: ctx.category.category,
          href: categoryHref(ctx.categoryIndex),
        },
        ...(ctx.group
          ? [
              {
                label: ctx.group.name,
                href: boardParentBrowseHref(ctx.group),
              },
            ]
          : []),
        { label: ctx.parent.name, href: boardPath(fid) },
      ],
      crumbTailKey: "Boards.all_children",
      activeFid: fid,
      activeCategoryIndex: ctx.categoryIndex,
      fillMobile: false,
      japanPrefs: isJapanBrowseContext(fid),
    };
  }

  const subtype = path.match(/^\/b\/([^/]+)\/t\/([^/]+)$/);
  if (subtype) {
    const fid = decodeURIComponent(subtype[1]);
    const typeid = decodeURIComponent(subtype[2]);
    const ctx = findSubtype(fid, typeid);
    if (!ctx?.child) return null;
    const boardLabel = ctx.child.type_name || ctx.child.name;
    const parentKey = parentFid(ctx.parent);
    return {
      crumbs: [
        {
          label: ctx.category.category,
          href: categoryHref(ctx.categoryIndex),
        },
        ...(ctx.group
          ? [
              {
                label: ctx.group.name,
                href: boardParentBrowseHref(ctx.group),
              },
            ]
          : []),
        {
          label: ctx.parent.name,
          href: boardPath(parentKey || fid),
        },
        { label: boardLabel },
      ],
      activeFid: parentKey || fid,
      activeTypeid: typeid,
      activeCategoryIndex: ctx.categoryIndex,
      fillMobile: Boolean(ctx.child.search_keyword),
      japanPrefs: isJapanBrowseContext(fid, typeid),
    };
  }

  const board = path.match(/^\/b\/([^/]+)$/);
  if (board) {
    const fid = decodeURIComponent(board[1]);
    const ctx = findByFid(fid);
    if (!ctx) return null;
    const parentKey = parentFid(ctx.parent);
    return {
      crumbs: [
        {
          label: ctx.category.category,
          href: categoryHref(ctx.categoryIndex),
        },
        ...(ctx.group
          ? [
              {
                label: ctx.group.name,
                href: boardParentBrowseHref(ctx.group),
              },
            ]
          : []),
        { label: ctx.parent.name },
      ],
      activeFid: parentKey || fid,
      activeCategoryIndex: ctx.categoryIndex,
      fillMobile: false,
      japanPrefs: isJapanBrowseContext(forumBaseFid(fid)),
    };
  }

  return null;
}

/** 旧 /browse?board_fid=141:689 → 新路径 */
export function legacyBrowseRedirectTarget(
  search: {
    board_fid?: string;
    board?: string;
    board_parent?: string;
  },
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): string | null {
  const fidKey = (search.board_fid || "").trim();
  if (fidKey) {
    const parsed = parseBoardKey(fidKey);
    if (parsed) {
      const legacy = legacyFidRedirect(parsed.fid);
      if (legacy) return legacy;
      return subtypePath(parsed.fid, parsed.typeid);
    }
    const legacyBare = legacyFidRedirect(fidKey);
    if (legacyBare) return legacyBare;
    const child = findBoardChild(fidKey, nav);
    if (child) return boardBrowseHref(child);
  }
  const parentName = (search.board_parent || "").trim();
  if (parentName) {
    for (const cat of nav) {
      for (const { parent } of walkParents(cat, 0)) {
        if (parent.name === parentName) return boardParentBrowseHref(parent);
      }
      const top = cat.boards.find((b) => b.name === parentName);
      if (top) return boardParentBrowseHref(top);
    }
  }
  const boardName = (search.board || "").trim();
  if (boardName) {
    const child =
      findBoardChild(boardName, nav) ||
      (() => {
        for (const cat of nav) {
          for (const { parent } of walkParents(cat, 0)) {
            const hit = parent.children.find(
              (c) => c.name === boardName || c.type_name === boardName,
            );
            if (hit) return hit;
          }
        }
        return undefined;
      })();
    if (child) return boardBrowseHref(child);
  }
  return null;
}

export function legacyBoardNames(displayName: string): string[] {
  const name = displayName.trim();
  if (!name) return [];
  const names = new Set<string>([name]);
  if (name.includes(" · ")) {
    names.add(name.replace(/ · /g, "-"));
  } else if (name.includes("-")) {
    names.add(name.replace(/-/g, " · "));
  }
  return Array.from(names);
}

/** 刮削页分区（与片区导航对齐） */
export type ScrapeRegionId = "日本" | "国产" | "欧美" | "手动";

export type ScrapePrefixOption = {
  prefix: string;
  label: string;
};

function collectSearchPrefixes(parent: BoardNavParent): ScrapePrefixOption[] {
  const out: ScrapePrefixOption[] = [];
  const seen = new Set<string>();
  const pushChild = (ch: BoardNavChild) => {
    const p = (ch.search_keyword || ch.type_name || "").trim().toUpperCase();
    if (!p || seen.has(p)) return;
    // 厂牌前缀（含欧美长名如 DigitalPlayground）；跳过纯中文分类
    if (!/^[A-Z0-9][A-Z0-9-]{1,23}$/i.test(p)) return;
    seen.add(p);
    out.push({ prefix: p, label: p });
  };
  for (const ch of parent.children || []) pushChild(ch);
  for (const nested of parent.boards || []) {
    for (const ch of nested.children || []) pushChild(ch);
  }
  return out.sort((a, b) => a.prefix.localeCompare(b.prefix));
}

function findRegionBoard(
  region: ScrapeRegionId,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): BoardNavParent | null {
  if (region === "手动") return null;
  for (const cat of nav) {
    for (const board of cat.boards) {
      if (board.name === region) return board;
    }
  }
  return null;
}

/** 日本等有嵌套时：有码 / 无码 … */
export function scrapeNestedBoards(
  region: ScrapeRegionId,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): ScrapePrefixOption[] {
  const parent = findRegionBoard(region, nav);
  if (!parent?.boards?.length) return [];
  return parent.boards.map((b) => ({ prefix: b.name, label: b.name }));
}

/** 刮削表单：分区 → 可选厂牌前缀；nestedBoard 如「有码」「无码」 */
export function scrapeRegionPrefixes(
  region: ScrapeRegionId,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
  nestedBoard = "",
): ScrapePrefixOption[] {
  if (region === "手动") return [];

  const parent = findRegionBoard(region, nav);
  if (!parent) return [];

  const nested = String(nestedBoard || "").trim();
  if (nested && parent.boards?.length) {
    const sub = parent.boards.find((b) => b.name === nested);
    if (sub) return collectSearchPrefixes(sub);
    return [];
  }
  return collectSearchPrefixes(parent);
}

/** 自动爬取作用域：多级板块 → 厂牌前缀列表 */
export type ScrapeAutoScope = {
  region: ScrapeRegionId;
  /** 二级板块，如有码 / 无码；空=该分区全部 */
  board: string;
  /** 厂牌前缀；空=该板块下全部厂牌 */
  prefix: string;
  /** 具体番号；空=该厂牌下全部 */
  code: string;
};

export function resolveScopePrefixes(
  scope: Pick<ScrapeAutoScope, "region" | "board" | "prefix">,
  nav: BoardNavCategory[] = FALLBACK_BOARD_NAV,
): ScrapePrefixOption[] {
  const region = scope.region;
  if (region === "手动") return [];
  const all = scrapeRegionPrefixes(region, nav, scope.board);
  const p = String(scope.prefix || "")
    .trim()
    .toUpperCase();
  if (!p) return all;
  return all.filter((x) => x.prefix === p);
}

export const SCRAPE_REGIONS: ScrapeRegionId[] = [
  "日本",
  "国产",
  "欧美",
  "手动",
];

/** 自动爬取可选一级分区（不含手动） */
export const SCRAPE_AUTO_REGIONS: Exclude<ScrapeRegionId, "手动">[] = [
  "日本",
  "国产",
  "欧美",
];

