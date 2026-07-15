CREATE TABLE IF NOT EXISTS collector_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO collector_settings (key, value) VALUES
  ('web_crawler_enabled', 'true'),
  ('web_crawl_urls', ''),
  ('web_crawler_interval_minutes', '30'),
  ('web_crawler_timeout', '30'),
  ('web_crawler_ua', 'Mozilla/5.0 (compatible; ED2KCollector/1.0)'),
  ('tg_enabled', 'false'),
  ('tg_api_id', ''),
  ('tg_api_hash', ''),
  ('tg_groups', ''),
  ('tg_session', 'ed2k'),
  ('next_web_url', 'http://localhost:3008'),
  ('collector_title', 'ED2K 收集器')
ON CONFLICT (key) DO NOTHING;
