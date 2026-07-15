CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE sources (
  id          SERIAL PRIMARY KEY,
  key         TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('web', 'telegram', 'upload')),
  url         TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ed2k_resources (
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

CREATE TABLE resource_sources (
  id           SERIAL PRIMARY KEY,
  hash         TEXT NOT NULL REFERENCES ed2k_resources(hash) ON DELETE CASCADE,
  source_id    INT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  source_url   TEXT,
  title        TEXT,
  published_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_resource_sources_unique
  ON resource_sources (hash, source_id, COALESCE(source_url, ''));

CREATE TABLE tags (
  id   SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE resource_tags (
  hash   TEXT NOT NULL REFERENCES ed2k_resources(hash) ON DELETE CASCADE,
  tag_id INT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (hash, tag_id)
);

CREATE TABLE import_jobs (
  id           SERIAL PRIMARY KEY,
  source_type  TEXT NOT NULL,
  raw_content  TEXT,
  parsed_count INT DEFAULT 0,
  status       TEXT NOT NULL DEFAULT 'pending',
  error_msg    TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ed2k_filename_trgm ON ed2k_resources USING gin (filename gin_trgm_ops);
CREATE INDEX idx_ed2k_search_trgm ON ed2k_resources USING gin (search_string gin_trgm_ops);
CREATE INDEX idx_ed2k_tsv ON ed2k_resources USING gin (tsv);
CREATE INDEX idx_ed2k_size ON ed2k_resources (size DESC);
CREATE INDEX idx_ed2k_created ON ed2k_resources (created_at DESC);
CREATE INDEX idx_ed2k_extension ON ed2k_resources (extension);

INSERT INTO sources (key, name, source_type) VALUES
  ('upload:manual', '手动上传', 'upload'),
  ('web:crawler', '网站爬虫', 'web'),
  ('telegram:listener', 'Telegram 群组', 'telegram');

INSERT INTO ed2k_resources (hash, filename, size, ed2k_link, search_string)
VALUES (
  '766C163CF5DDE96E597B333D550D1204',
  'www.98T.la@高数3105.zip',
  1306033644,
  'ed2k://|file|www.98T.la@高数3105.zip|1306033644|766C163CF5DDE96E597B333D550D1204|/',
  'www.98T.la@高数3105.zip 高数3105'
);

INSERT INTO resource_sources (hash, source_id, title)
SELECT
  '766C163CF5DDE96E597B333D550D1204',
  id,
  '示例资源'
FROM sources
WHERE key = 'upload:manual';
