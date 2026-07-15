-- 升级旧库：resource_sources 来源论坛/板块字段（014 仅 CREATE IF NOT EXISTS 不会补列）
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS board_fid TEXT;
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS board_name TEXT;
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS forum_id TEXT;
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS import_outcome TEXT;
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS preview_images TEXT[];
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS ed2k_links TEXT[];
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS extract_password TEXT;

-- 爬虫队列侧 forum_id（012 已有；此处再保一次）
ALTER TABLE crawl_pages ADD COLUMN IF NOT EXISTS forum_id TEXT;
