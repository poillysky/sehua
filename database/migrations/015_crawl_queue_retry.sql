-- 待抓队列退避 / 失败计数（对齐拓扑：软文队列 · 下轮再抓）

ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS tid BIGINT;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS fetch_fail_count INT NOT NULL DEFAULT 0;
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS retry_after TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_crawl_pages_pending_ready
  ON crawl_pages (page_type, status, retry_after, fetch_fail_count, updated_at)
  WHERE page_type = 'thread' AND status = 'pending';

CREATE INDEX IF NOT EXISTS idx_crawl_pages_board_pending
  ON crawl_pages (board_fid, status)
  WHERE page_type = 'thread';
