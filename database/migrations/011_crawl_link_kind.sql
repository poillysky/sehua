ALTER TABLE crawl_pages
  ADD COLUMN IF NOT EXISTS link_kind TEXT
  CHECK (link_kind IS NULL OR link_kind IN ('magnet', 'ed2k', 'failed'));

UPDATE crawl_pages
SET link_kind = CASE
  WHEN status = 'failed' THEN 'failed'
  WHEN ed2k_count > 0 THEN 'ed2k'
  WHEN outcome ILIKE '%magnet%' THEN 'magnet'
  WHEN outcome ILIKE '%成功入库%'
    OR outcome ILIKE '%不符合展示%'
    OR last_error = 'not display-ready' THEN 'ed2k'
  ELSE 'failed'
END
WHERE page_type = 'thread' AND status != 'pending';

CREATE INDEX IF NOT EXISTS idx_crawl_pages_link_kind
  ON crawl_pages (page_type, link_kind, updated_at DESC)
  WHERE page_type = 'thread' AND status != 'pending';
