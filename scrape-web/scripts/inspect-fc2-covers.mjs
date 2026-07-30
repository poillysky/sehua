import pg from "pg";
import sharp from "sharp";
import fs from "fs";
import path from "path";

const pool = new pg.Pool({
  connectionString:
    process.env.POSTGRES_DB_URL ||
    "postgres://postgres:postgres@192.168.2.38:5435/ed2k",
});

const codes = [
  "FC2-PPV-4576037",
  "FC2-PPV-4576456",
  "FC2-PPV-4557677",
  "FC2-PPV-2856126",
  "FC2-PPV-4573362",
];

const { rows } = await pool.query(
  `SELECT code, cover_path, cover_source, title FROM av_metadata WHERE code = ANY($1)`,
  [codes],
);

function findFile(coverPath, code) {
  const tries = [];
  if (coverPath) {
    const rel = String(coverPath).replace(/^\//, "");
    tries.push(path.resolve(rel));
    tries.push(path.resolve("data", rel.replace(/^covers\//, "covers/")));
    tries.push(path.resolve(String(coverPath).replace(/^\/covers\//, "data/covers/")));
  }
  const safe = String(code).replace(/[^A-Za-z0-9_-]+/g, "_");
  for (const dir of ["data/covers/FC2/FC2", "data/covers/FC2", "data/covers"]) {
    for (const ext of [".jpg", ".jpeg", ".png", ".webp"]) {
      tries.push(path.join(dir, safe + ext));
      tries.push(path.join(dir, code + ext));
    }
  }
  for (const t of tries) {
    if (fs.existsSync(t) && fs.statSync(t).isFile()) return t;
  }
  // recursive search by code fragment
  const root = "data/covers";
  const walk = (d) => {
    if (!fs.existsSync(d)) return null;
    for (const n of fs.readdirSync(d)) {
      const f = path.join(d, n);
      const st = fs.statSync(f);
      if (st.isDirectory()) {
        const x = walk(f);
        if (x) return x;
      } else if (n.toUpperCase().includes(safe.toUpperCase().slice(0, 20))) {
        return f;
      }
    }
    return null;
  };
  return walk(root);
}

for (const r of rows) {
  const found = findFile(r.cover_path, r.code);
  if (!found) {
    console.log(r.code, "src=" + r.cover_source, "path=" + r.cover_path, "MISSING");
    continue;
  }
  const meta = await sharp(found).metadata();
  const ar = (meta.width / (meta.height || 1)).toFixed(3);
  const orient =
    meta.width > meta.height * 1.15
      ? "landscape"
      : meta.height > meta.width * 1.15
        ? "portrait"
        : "squareish";
  console.log(
    r.code,
    "src=" + r.cover_source,
    meta.width + "x" + meta.height,
    "AR=" + ar,
    orient,
    "db=" + r.cover_path,
  );
}
await pool.end();
