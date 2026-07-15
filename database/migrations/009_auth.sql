-- 账号与权限

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
