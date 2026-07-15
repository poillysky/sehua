ALTER TABLE resource_sources
  ADD COLUMN IF NOT EXISTS ed2k_links TEXT[] NOT NULL DEFAULT '{}';

UPDATE resource_sources rs
SET ed2k_links = ARRAY[r.ed2k_link]
FROM ed2k_resources r
WHERE rs.hash = r.hash
  AND coalesce(array_length(rs.ed2k_links, 1), 0) = 0;
