-- 资源解压密码（论坛帖解析，可选字段）
ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS extract_password TEXT;
