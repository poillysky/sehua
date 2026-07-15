-- ED2K 资源库初始化脚本
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS ed2k_resources (
  hash CHAR(32) PRIMARY KEY,
  filename TEXT NOT NULL,
  size BIGINT NOT NULL DEFAULT 0,
  ed2k_link TEXT NOT NULL,
  extension TEXT,
  search_string TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resource_sources (
  id BIGSERIAL PRIMARY KEY,
  hash CHAR(32) NOT NULL REFERENCES ed2k_resources(hash) ON DELETE CASCADE,
  title TEXT,
  description TEXT,
  source_url TEXT,
  preview_images TEXT[],
  ed2k_links TEXT[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_filename_trgm
  ON ed2k_resources USING gin (filename gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_search_string_trgm
  ON ed2k_resources USING gin (search_string gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_created_at
  ON ed2k_resources (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_size
  ON ed2k_resources (size);

CREATE INDEX IF NOT EXISTS idx_resource_sources_hash
  ON resource_sources (hash);
