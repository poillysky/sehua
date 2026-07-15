-- 资源来源增加简介字段
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS description TEXT;

-- 已有记录：用 title 补全 search_string（若简介为空则跳过）
UPDATE ed2k_resources r
SET search_string = trim(both from concat_ws(' ', r.filename, rs.title, rs.description))
FROM resource_sources rs
WHERE rs.hash = r.hash
  AND rs.title IS NOT NULL
  AND rs.title <> ''
  AND r.search_string = r.filename;
