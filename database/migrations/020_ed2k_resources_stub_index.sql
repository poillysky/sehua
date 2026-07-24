-- Stub rows (~3% of resources): allow priority-stub / stub cleanup without
-- scanning all ed2k_resources via lower(COALESCE(ed2k_link)).
CREATE INDEX IF NOT EXISTS idx_ed2k_resources_stubs
  ON ed2k_resources (hash)
  WHERE ed2k_link LIKE 'unavailable://thread/%';
