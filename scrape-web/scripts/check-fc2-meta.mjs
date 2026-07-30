import pg from "pg";
const pool = new pg.Pool({
  connectionString: "postgres://postgres:postgres@192.168.2.38:5435/ed2k",
});
const codes = ["FC2-PPV-4576037", "FC2-PPV-2856126", "FC2-PPV-4576456"];
const { rows } = await pool.query(
  `SELECT code, cover_source, status,
          left(coalesce(title_zh, title, title_ja, ''), 50) AS title
   FROM av_metadata WHERE code = ANY($1)`,
  [codes],
);
for (const r of rows) {
  console.log(`${r.code}\t${r.status}\tcover=${r.cover_source}\t${r.title}`);
}
await pool.end();
