-- 占位/入库细分判定原因（如：无权限下载附件、需回复贴）
ALTER TABLE resource_sources
  ADD COLUMN IF NOT EXISTS import_outcome TEXT;

-- 用队列里已有 outcome 回填历史占位记录（无 crawl_pages 时跳过，搜索-only 库兼容）
DO $$
BEGIN
  IF to_regclass('public.crawl_pages') IS NOT NULL THEN
    UPDATE resource_sources rs
    SET import_outcome = cp.outcome
    FROM crawl_pages cp
    WHERE rs.import_outcome IS NULL
      AND cp.page_type = 'thread'
      AND cp.url = rs.source_url
      AND cp.outcome IS NOT NULL
      AND cp.outcome <> '';
  END IF;
END $$;
