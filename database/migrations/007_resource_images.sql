-- 资源来源增加预览插图
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS preview_images TEXT[];
