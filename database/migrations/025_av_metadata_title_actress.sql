-- av_metadata：中文片名 / 日文片名 / 女优
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS title_zh TEXT;
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS title_ja TEXT;
ALTER TABLE av_metadata ADD COLUMN IF NOT EXISTS actresses TEXT[];

CREATE INDEX IF NOT EXISTS idx_av_metadata_title_zh
  ON av_metadata (title_zh)
  WHERE title_zh IS NOT NULL AND title_zh <> '';
