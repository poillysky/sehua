-- Hot-path lookups by thread URL (delete stub after real import, known tids, etc.)
-- Without this index, WHERE source_url = %s seq-scans ~300k rows (~10–20s per write).
CREATE INDEX IF NOT EXISTS idx_resource_sources_source_url
  ON resource_sources (source_url)
  WHERE source_url IS NOT NULL AND source_url <> '';
