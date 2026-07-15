-- 占位/入库细分判定原因（如：无权限下载附件、需回复贴）
ALTER TABLE resource_sources
  ADD COLUMN IF NOT EXISTS import_outcome TEXT;

-- 用队列里已有 outcome 回填历史占位记录
-- 搜索-only / 半成品库：无 crawl_pages 或无 outcome 列时跳过
DO $$
BEGIN
  IF to_regclass('public.crawl_pages') IS NULL THEN
    RETURN;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'crawl_pages'
      AND column_name = 'outcome'
  ) THEN
    RETURN;
  END IF;

  UPDATE resource_sources rs
  SET import_outcome = cp.outcome
  FROM crawl_pages cp
  WHERE rs.import_outcome IS NULL
    AND cp.page_type = 'thread'
    AND cp.url = rs.source_url
    AND cp.outcome IS NOT NULL
    AND cp.outcome <> '';
END $$;
