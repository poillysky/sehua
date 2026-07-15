-- 爬虫实时活动日志 + 帖子元数据

CREATE TABLE IF NOT EXISTS crawl_activity_log (
  id          BIGSERIAL PRIMARY KEY,
  run_id      TEXT NOT NULL,
  level       TEXT NOT NULL DEFAULT 'info',
  message     TEXT NOT NULL,
  board_fid   TEXT,
  board_name  TEXT,
  thread_url  TEXT,
  thread_title TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawl_activity_log_created
  ON crawl_activity_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crawl_activity_log_run
  ON crawl_activity_log (run_id, id DESC);

ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS thread_title TEXT;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS board_fid TEXT;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS board_name TEXT;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS preview_images TEXT[];
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS outcome TEXT;
