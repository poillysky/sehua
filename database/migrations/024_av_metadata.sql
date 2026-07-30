-- 番号元数据（搜索栈 scrape-web 写入；next-web 只读）
CREATE TABLE IF NOT EXISTS av_metadata (
  code TEXT PRIMARY KEY,
  title TEXT,
  cover_path TEXT,
  cover_source TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  scraped_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_av_metadata_status_updated
  ON av_metadata (status, updated_at);

CREATE TABLE IF NOT EXISTS av_scrape_queue (
  id BIGSERIAL PRIMARY KEY,
  code TEXT NOT NULL,
  priority INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_av_scrape_queue_pending_code
  ON av_scrape_queue (code)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_av_scrape_queue_pick
  ON av_scrape_queue (status, priority DESC, id ASC);
