-- 随机抓帖：已探测 tid 持久化（重启后仍跳过，避免重复探）
CREATE TABLE IF NOT EXISTS random_tid_probes (
  forum_id    TEXT NOT NULL,
  tid         BIGINT NOT NULL,
  outcome     TEXT NOT NULL DEFAULT 'probed',
  board_fid   TEXT,
  title       TEXT,
  probed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (forum_id, tid)
);

CREATE INDEX IF NOT EXISTS idx_random_tid_probes_forum_outcome
  ON random_tid_probes (forum_id, outcome);

CREATE INDEX IF NOT EXISTS idx_random_tid_probes_forum_updated
  ON random_tid_probes (forum_id, updated_at DESC);
