ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS forum_id TEXT;

UPDATE crawl_pages
SET forum_id = 'sehuatang'
WHERE page_type = 'thread'
  AND forum_id IS NULL
  AND (
    url ILIKE '%sehuatang.net%'
    OR url ILIKE '%sehuatang.org%'
    OR url ILIKE '%98t.%'
  );

UPDATE crawl_pages
SET forum_id = 'other'
WHERE page_type = 'thread'
  AND forum_id IS NULL
  AND status != 'pending';

CREATE INDEX IF NOT EXISTS idx_crawl_pages_forum_id
  ON crawl_pages (forum_id, link_kind, updated_at DESC)
  WHERE page_type = 'thread' AND status != 'pending';
