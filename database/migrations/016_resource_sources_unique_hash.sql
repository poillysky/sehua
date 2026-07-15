-- 同一资源 hash 只保留一条来源记录：后写覆盖先写。
-- 清理历史重复后，将唯一约束从 (hash, source_id, url) 改为 hash。

DELETE FROM resource_sources a
USING resource_sources b
WHERE a.hash = b.hash
  AND a.id < b.id;

DROP INDEX IF EXISTS idx_resource_sources_unique;

CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_sources_hash_unique
  ON resource_sources (hash);
