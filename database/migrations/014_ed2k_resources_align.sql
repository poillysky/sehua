-- 在已有 tang98（content_items / crawl_*）上对齐 ed2k 资源模型。
-- 不重建 crawl_pages（列结构与 ed2k 原版不同，后续单独兼容）。

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- sources：全新库或从未跑过 001 的旧库都要能建出来
CREATE TABLE IF NOT EXISTS sources (
  id          SERIAL PRIMARY KEY,
  key         TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('web', 'telegram', 'upload')),
  url         TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO sources (key, name, source_type) VALUES
  ('upload:manual', '手动上传', 'upload'),
  ('web:crawler', '网站爬虫', 'web')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS ed2k_resources (
  hash          TEXT PRIMARY KEY,
  filename      TEXT NOT NULL,
  size          BIGINT NOT NULL,
  ed2k_link     TEXT NOT NULL,
  extension     TEXT GENERATED ALWAYS AS (
    substring(lower(filename) FROM '[^/.]\.([a-z0-9]+)$')
  ) STORED,
  search_string TEXT NOT NULL,
  tsv           TSVECTOR NOT NULL GENERATED ALWAYS AS (
    to_tsvector('simple', search_string)
  ) STORED,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resource_sources (
  id                SERIAL PRIMARY KEY,
  hash              TEXT NOT NULL REFERENCES ed2k_resources(hash) ON DELETE CASCADE,
  source_id         INT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  source_url        TEXT,
  title             TEXT,
  published_at      TIMESTAMPTZ,
  description       TEXT,
  preview_images    TEXT[],
  ed2k_links        TEXT[] NOT NULL DEFAULT '{}',
  extract_password  TEXT,
  board_fid         TEXT,
  board_name        TEXT,
  forum_id          TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_sources_unique
  ON resource_sources (hash, source_id, COALESCE(source_url, ''));

CREATE TABLE IF NOT EXISTS tags (
  id   SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS resource_tags (
  hash   TEXT NOT NULL REFERENCES ed2k_resources(hash) ON DELETE CASCADE,
  tag_id INT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (hash, tag_id)
);

CREATE TABLE IF NOT EXISTS import_jobs (
  id           SERIAL PRIMARY KEY,
  source_type  TEXT NOT NULL,
  raw_content  TEXT,
  parsed_count INT DEFAULT 0,
  status       TEXT NOT NULL DEFAULT 'pending',
  error_msg    TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ed2k_filename_trgm ON ed2k_resources USING gin (filename gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ed2k_search_trgm ON ed2k_resources USING gin (search_string gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ed2k_tsv ON ed2k_resources USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_ed2k_size ON ed2k_resources (size DESC);
CREATE INDEX IF NOT EXISTS idx_ed2k_created ON ed2k_resources (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ed2k_extension ON ed2k_resources (extension);

-- 账号（ed2k 009）
CREATE TABLE IF NOT EXISTS auth_roles (
  id SERIAL PRIMARY KEY,
  name VARCHAR(32) NOT NULL UNIQUE,
  label VARCHAR(64) NOT NULL,
  permissions TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name VARCHAR(128),
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS auth_user_roles (
  user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

INSERT INTO auth_roles (name, label, permissions) VALUES
  ('admin', '管理员', ARRAY['*']),
  ('operator', '操作员', ARRAY['resources.view', 'crawler.view', 'import', 'crawl.run', 'settings.read']),
  ('viewer', '只读', ARRAY['resources.view', 'crawler.view'])
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS collector_settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
