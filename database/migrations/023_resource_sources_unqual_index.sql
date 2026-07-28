-- 不合格 outcome 计数（爬虫状态 / 不合格明细）加速
CREATE INDEX IF NOT EXISTS idx_resource_sources_unqual_forum_url
  ON resource_sources (forum_id, source_url)
  WHERE import_outcome LIKE '不合格%'
     OR import_outcome LIKE '待核：%'
     OR import_outcome LIKE '待核:%';

CREATE INDEX IF NOT EXISTS idx_resource_sources_import_outcome
  ON resource_sources (import_outcome);
