export type ScrapePayload = {
  code?: string;
  kind?: string;
  status?: string;
  title?: string | null;
  title_zh?: string | null;
  title_ja?: string | null;
  actresses?: string[];
  cover_path?: string | null;
  error?: string | null;
  updated_at?: string | null;
};

export const KIND_LABEL: Record<string, string> = {
  av: "有码",
  fc2: "FC2",
  chinese: "国产",
  uncensored: "无码",
  mgstage: "MGStage",
};

export const STATUS_LABEL: Record<string, string> = {
  ok: "成功",
  missing: "未找到",
  error: "失败",
  skipped: "已跳过",
  pending: "等待",
  running: "进行中",
  done: "完成",
};

export function metaEqual(
  a: ScrapePayload | null,
  b: ScrapePayload | null,
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  const actA = (a.actresses || []).join("\0");
  const actB = (b.actresses || []).join("\0");
  return (
    a.code === b.code &&
    a.kind === b.kind &&
    a.status === b.status &&
    a.title === b.title &&
    a.title_zh === b.title_zh &&
    a.title_ja === b.title_ja &&
    a.cover_path === b.cover_path &&
    a.error === b.error &&
    actA === actB
  );
}
