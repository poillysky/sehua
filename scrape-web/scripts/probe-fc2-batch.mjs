import "dotenv/config";
import pg from "pg";

const SCRAPE = process.env.SCRAPE_ORIGIN || "http://127.0.0.1:9209";
const pool = new pg.Pool({
  connectionString:
    process.env.POSTGRES_DB_URL ||
    "postgres://postgres:postgres@192.168.2.38:5435/ed2k",
});

function normalizeFc2(raw) {
  const t = String(raw || "")
    .toUpperCase()
    .replace(/\s+/g, "");
  const m =
    t.match(/FC2[-_]?PPV[-_]?(\d{6,10})/) || t.match(/FC2[-_]?(\d{6,10})/);
  if (!m) return null;
  // 避免把「2864440 18岁」吃成 286444018
  const id = m[1];
  if (id.length > 8) return null;
  return t.includes("PPV") || /FC2PPV/.test(t)
    ? `FC2-PPV-${id}`
    : `FC2-${id}`;
}

const { rows } = await pool.query(`
  SELECT filename FROM ed2k_resources
  WHERE filename ~* 'FC2[-_]?PPV[-_]?\\d{6,8}'
  ORDER BY updated_at DESC NULLS LAST
  LIMIT 60
`);
const codes = [];
const seen = new Set();
for (const r of rows) {
  const n = normalizeFc2(r.filename);
  if (!n || seen.has(n)) continue;
  seen.add(n);
  codes.push(n);
  if (codes.length >= 5) break;
}
if (!codes.length) {
  codes.push("FC2-PPV-2856126", "FC2-PPV-2859296", "FC2-PPV-2860375");
}
console.log("sample:", codes.join(", "));
console.log("");

const results = [];
for (const code of codes) {
  const t0 = Date.now();
  process.stdout.write(`→ ${code} ... `);
  try {
    const res = await fetch(
      `${SCRAPE}/api/scrape/${encodeURIComponent(code)}?sync=1&overwrite=1`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "fc2" }),
      },
    );
    const j = await res.json();
    const ok =
      j.status === "ok" &&
      Boolean(j.cover_path) &&
      Boolean(j.title || j.title_zh);
    const row = {
      code,
      ok,
      status: j.status,
      ms: Date.now() - t0,
      sources: (j.sources || []).join(",") || "-",
      cover: j.cover_source || "-",
      title: String(j.title_zh || j.title || "").slice(0, 40),
      err: j.error || null,
    };
    results.push(row);
    console.log(
      `${ok ? "OK" : "NG"} [${j.status}] src=${row.sources} cover=${row.cover} ${row.ms}ms`,
    );
    if (row.title) console.log(`   title: ${row.title}`);
    if (row.err) console.log(`   err: ${row.err}`);
  } catch (e) {
    results.push({
      code,
      ok: false,
      status: "error",
      ms: Date.now() - t0,
      err: String(e.message || e),
    });
    console.log(`EX ${e.message}`);
  }
}

const pass = results.filter((r) => r.ok).length;
console.log("");
console.log(`FC2 success: ${pass}/${results.length} (${Math.round((pass / Math.max(results.length, 1)) * 100)}%)`);
await pool.end();
