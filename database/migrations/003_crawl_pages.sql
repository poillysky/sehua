CREATE TABLE IF NOT EXISTS crawl_pages (
  url           TEXT PRIMARY KEY,
  page_type     TEXT NOT NULL CHECK (page_type IN ('list', 'thread')),
  status        TEXT NOT NULL DEFAULT 'pending',
  ed2k_count    INT NOT NULL DEFAULT 0,
  last_error    TEXT,
  crawled_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawl_pages_status ON crawl_pages (status, updated_at);
CREATE INDEX IF NOT EXISTS idx_crawl_pages_type ON crawl_pages (page_type, status);
