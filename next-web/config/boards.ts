import boardsNavJson from "./boards.nav.json";

export type BoardNavChild = {
  key: string;
  fid: string;
  typeid: string;
  name: string;
  type_name: string;
  board_name: string;
};

export type BoardNavParent = {
  name: string;
  children: BoardNavChild[];
};

export type BoardNavCategory = {
  category: string;
  boards: BoardNavParent[];
};

export const BOARD_NAV = boardsNavJson as BoardNavCategory[];

export function findBoardChild(key: string): BoardNavChild | undefined {
  const needle = key.trim();
  if (!needle) return undefined;
  for (const cat of BOARD_NAV) {
    for (const board of cat.boards) {
      const hit = board.children.find((c) => c.key === needle);
      if (hit) return hit;
    }
  }
  return undefined;
}

/** 浏览页跳转：优先 board_fid（子版 key） */
export function boardBrowseHref(child: BoardNavChild): string {
  const params = new URLSearchParams();
  params.set("board_fid", child.key);
  if (child.name) params.set("board", child.name);
  return `/browse?${params.toString()}`;
}

export function boardParentBrowseHref(parent: BoardNavParent): string {
  const params = new URLSearchParams();
  params.set("board_parent", parent.name);
  return `/browse?${params.toString()}`;
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
