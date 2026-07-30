/**
 * 无码区：每前缀取样 1 部 → 同步刮削 → 看 kind / 哪些源出结果
 * 用法: node scripts/probe-uncensored-scrape.mjs
 */
import pg from "pg";

const SCRAPE = process.env.SCRAPE_ORIGIN || "http://127.0.0.1:9209";
const pool = new pg.Pool({
  connectionString:
    process.env.POSTGRES_DB_URL ||
    "postgres://postgres:postgres@192.168.2.38:5435/ed2k",
});

const PREFIXES = [
  { id: "CARIB", kindHint: "uncensored" },
  { id: "Caribbean", kindHint: "uncensored", aliasOf: "CARIB" },
  { id: "1PON", kindHint: "uncensored" },
  { id: "1pondo", kindHint: "uncensored", aliasOf: "1PON" },
  { id: "HEYZO", kindHint: "uncensored" },
  { id: "TokyoHot", kindHint: "uncensored" },
  { id: "FC2", kindHint: "fc2" },
  { id: "FC2PPV", kindHint: "fc2" },
  { id: "PACO", kindHint: "uncensored" },
  { id: "10MU", kindHint: "uncensored" },
  { id: "10musume", kindHint: "uncensored", aliasOf: "10MU" },
  { id: "XXX-AV", kindHint: "uncensored" },
  { id: "Cospuri", kindHint: "uncensored" },
];

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractCodesForPrefix(text, prefix) {
  const src = String(text || "");
  const p = String(prefix || "").trim();
  if (!src || !p) return [];
  const upper = src.toUpperCase();
  const pUpper = p.toUpperCase();
  const out = new Set();

  if (pUpper === "FC2" || pUpper === "FC2PPV") {
    const rePpv = /FC2[-_]?PPV[-_\s]?(\d{5,10})/gi;
    let m;
    while ((m = rePpv.exec(upper)) !== null) out.add(`FC2-PPV-${m[1]}`);
    if (pUpper === "FC2") {
      const reFc2 =
        /(?:^|[^A-Z0-9])FC2(?![-_]?PPV)[-_\s]?(\d{5,10})(?![A-Z0-9])/gi;
      while ((m = reFc2.exec(upper)) !== null) out.add(`FC2-${m[1]}`);
    }
    return [...out];
  }

  if (
    ["CARIB", "CARIBBEAN", "1PON", "1PONDO", "PACO", "10MU", "10MUSUME"].includes(
      pUpper,
    )
  ) {
    const label =
      pUpper === "CARIBBEAN"
        ? "CARIB"
        : pUpper === "1PONDO"
          ? "1PON"
          : pUpper === "10MUSUME"
            ? "10MU"
            : pUpper;
    if (upper.includes(pUpper) || upper.includes(label)) {
      const re = /(?:^|[^A-Z0-9])(\d{6})[-_](\d{2,3})(?![A-Z0-9])/gi;
      let m;
      while ((m = re.exec(upper)) !== null) {
        out.add(`${label}-${m[1]}-${m[2]}`);
      }
    }
    const esc = escapeRegExp(pUpper);
    const rePref = new RegExp(
      `${esc}[-_\\s]?(\\d{6})[-_](\\d{2,3})(?![A-Z0-9])`,
      "gi",
    );
    let m;
    while ((m = rePref.exec(upper)) !== null) {
      out.add(`${label}-${m[1]}-${m[2]}`);
    }
    if (out.size) return [...out];
  }

  // Tokyo Hot: n1234 / TokyoHot-n1234 / tokyo-hot-1234
  if (pUpper === "TOKYOHOT" || pUpper === "TOKYO-HOT") {
    let m;
    const reN = /(?:TOKYO[-_]?HOT[-_\s]?)?n(\d{3,5})/gi;
    while ((m = reN.exec(upper)) !== null) out.add(`TokyoHot-n${m[1]}`);
    const reNum = /TOKYO[-_]?HOT[-_\s]?(\d{3,5})/gi;
    while ((m = reNum.exec(upper)) !== null) out.add(`TokyoHot-${m[1]}`);
    if (out.size) return [...out];
  }

  // XXX-AV / Cospuri
  const esc = escapeRegExp(pUpper);
  const re = new RegExp(
    `(?:^|[^A-Z0-9])${esc}[-_\\s]?(\\d{2,8}(?:[A-Z]{1,2})?)(?![A-Z0-9])`,
    "gi",
  );
  let m;
  while ((m = re.exec(upper)) !== null) {
    const num = m[1].replace(/[A-Z]+$/i, "");
    if (/^\d{2,8}$/.test(num)) out.add(`${pUpper}-${num}`);
  }
  return [...out];
}

async function sampleCode(prefix) {
  const { rows } = await pool.query(
    `SELECT filename
     FROM ed2k_resources
     WHERE filename ILIKE $1
     ORDER BY updated_at DESC NULLS LAST
     LIMIT 200`,
    [`%${prefix}%`],
  );
  const counts = new Map();
  for (const r of rows) {
    for (const c of extractCodesForPrefix(r.filename, prefix)) {
      counts.set(c, (counts.get(c) || 0) + 1);
    }
  }
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  return ranked[0]?.[0] || null;
}

async function scrapeSync(code, kind) {
  const url = `${SCRAPE}/api/scrape/${encodeURIComponent(code)}?sync=1&overwrite=1`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(kind ? { kind } : {}),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = { status: "error", error: text.slice(0, 200) };
  }
  return { http: res.status, ...json };
}

const seen = new Set();
const results = [];

for (const row of PREFIXES) {
  const samplePrefix = row.aliasOf || row.id;
  let code = await sampleCode(row.id);
  if (!code && row.aliasOf) code = await sampleCode(row.aliasOf);
  if (!code) {
    results.push({
      prefix: row.id,
      code: null,
      note: "资源库无样本",
    });
    console.log(`[skip] ${row.id}: no sample`);
    continue;
  }
  if (seen.has(code) && row.aliasOf) {
    results.push({
      prefix: row.id,
      code,
      note: `与 ${row.aliasOf} 同码，跳过重复刮削`,
      alias: true,
    });
    console.log(`[alias] ${row.id} → ${code}`);
    continue;
  }
  seen.add(code);
  console.log(`[scrape] ${row.id} → ${code} (kind=${row.kindHint})`);
  const t0 = Date.now();
  const scraped = await scrapeSync(code, row.kindHint);
  const ms = Date.now() - t0;
  const summary = {
    prefix: row.id,
    code,
    kindHint: row.kindHint,
    kind: scraped.kind,
    status: scraped.status,
    title: scraped.title || scraped.title_zh || scraped.title_ja,
    actresses: (scraped.actresses || []).slice(0, 3),
    cover: Boolean(scraped.cover_path),
    sources: scraped.sources || [],
    error: scraped.error || null,
    ms,
  };
  results.push(summary);
  console.log(
    `  → ${summary.status} kind=${summary.kind} sources=${(summary.sources || []).join(",") || "-"} title=${String(summary.title || "").slice(0, 40)} err=${summary.error || ""} (${ms}ms)`,
  );
}

await pool.end();
console.log("\n=== JSON ===");
console.log(JSON.stringify(results, null, 2));
