CREATE TABLE IF NOT EXISTS crawl_boards (
  url             TEXT PRIMARY KEY,
  fid             TEXT NOT NULL,
  name            TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  last_list_page  INT NOT NULL DEFAULT 0,
  last_error      TEXT,
  thread_count    INT NOT NULL DEFAULT 0,
  discovered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_crawled_at TIMESTAMPTZ,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawl_boards_status ON crawl_boards (status, last_crawled_at NULLS FIRST);

INSERT INTO collector_settings (key, value) VALUES
  ('web_crawler_auto_discover', 'true'),
  ('web_crawler_max_boards_per_run', '8'),
  ('web_crawler_list_pages_per_board', '15'),
  ('web_crawler_board_refresh_hours', '12'),
  ('web_crawler_max_list_pages', '0'),
  ('web_crawler_max_threads_per_run', '150'),
  ('web_crawler_request_delay', '2')
ON CONFLICT (key) DO UPDATE SET
  value = EXCLUDED.value,
  updated_at = now()
WHERE collector_settings.key IN (
  'web_crawler_max_list_pages',
  'web_crawler_max_threads_per_run',
  'web_crawler_request_delay'
);
