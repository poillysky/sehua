-- Random tid / board-meta updates look up crawl_pages by tid.
CREATE INDEX IF NOT EXISTS idx_crawl_pages_tid
  ON crawl_pages (tid)
  WHERE page_type = 'thread' AND tid IS NOT NULL;
