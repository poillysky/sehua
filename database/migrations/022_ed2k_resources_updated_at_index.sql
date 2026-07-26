-- 处理记录按 r.updated_at DESC 取「最近 N 行」；无此索引会随表膨胀全表排序。
CREATE INDEX IF NOT EXISTS idx_ed2k_updated
  ON ed2k_resources (updated_at DESC NULLS LAST);
