import pg from "pg";

const pool = new pg.Pool({
  connectionString: "postgres://postgres:postgres@192.168.2.38:5435/ed2k",
});

/** 无码区前缀（别名合并取样） */
const PREFIXES = [
  "CARIB",
  "Caribbean",
  "1PON",
  "1pondo",
  "HEYZO",
  "TokyoHot",
  "FC2",
  "FC2PPV",
  "PACO",
  "10MU",
  "10musume",
  "XXX-AV",
  "Cospuri",
];

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function sampleForPrefix(prefix) {
  const p = prefix.trim();
  const { rows } = await pool.query(
    `SELECT filename
     FROM ed2k_resources
     WHERE filename ILIKE $1
     ORDER BY updated_at DESC NULLS LAST
     LIMIT 80`,
    [`%${p}%`],
  );
  const re = new RegExp(
    `(${escapeRe(p)}[-_]?[A-Z0-9][-_A-Z0-9.]{2,40}|${escapeRe(p)}[-_]?\\d{3,})`,
    "i",
  );
  // 更宽松：从文件名里抠含前缀的 token
  const hits = [];
  for (const r of rows) {
    const name = String(r.filename || "");
    const tokens = name.match(/[A-Za-z0-9][A-Za-z0-9._-]{3,40}/g) || [];
    for (const t of tokens) {
      if (t.toUpperCase().includes(p.toUpperCase().replace(/-/g, ""))) {
        hits.push(t);
      } else if (re.test(t)) {
        hits.push(t);
      }
    }
    // date-style caribbean: 010123-001 near CARIB
    if (/carib/i.test(p) || /caribbean/i.test(p)) {
      const d = name.match(/\b(\d{6}[-_]\d{3})\b/);
      if (d) hits.push(`CARIB-${d[1].replace(/_/g, "-")}`);
    }
  }
  return [...new Set(hits)].slice(0, 8);
}

for (const p of PREFIXES) {
  const samples = await sampleForPrefix(p);
  console.log(`${p}\t${samples.join(" | ") || "(none)"}`);
}

await pool.end();
