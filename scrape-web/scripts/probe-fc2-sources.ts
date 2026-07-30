import { applyProxy } from "../src/proxy.js";
import { readConfig } from "../src/config.js";
import {
  profileFromSource,
  runWithRequestProfile,
} from "../src/httpContext.js";
import { applyFlareSolverr } from "../src/flaresolverr.js";
import { SOURCE_SCRAPERS } from "../src/sources/runners.js";
import {
  defaultSourceConfig,
  resolveBaseUrl,
  type SourceId,
} from "../src/sources/registry.js";

const SOURCES: SourceId[] = [
  "fd2ppv",
  "fc2",
  "fc2_hub",
  "javdb",
  "avsox",
  "airav",
  "airav_io",
  "sevenmmtv",
  "freejavbt",
  "miss_av",
];

const codes = (process.argv.slice(2).length
  ? process.argv.slice(2)
  : ["FC2-PPV-4576037", "FC2-PPV-4576456", "FC2-PPV-2856126"]
).map((c) => c.toUpperCase());

const cfg = await readConfig();
applyProxy(cfg.proxyUrl || "");
applyFlareSolverr(cfg.flareSolverrUrl || "");

console.log("proxy:", cfg.proxyUrl || "(none)");
console.log("flareSolverr:", cfg.flareSolverrUrl || "(none)");
console.log("");

const rows: Array<{
  code: string;
  source: string;
  result: string;
  ms: number;
  detail: string;
}> = [];

for (const code of codes) {
  for (const id of SOURCES) {
    const scraper = SOURCE_SCRAPERS[id];
    const src = cfg.sources[id] || defaultSourceConfig(id);
    const t0 = Date.now();
    process.stdout.write(`${code} @ ${String(id).padEnd(10)} `);
    if (!scraper) {
      console.log("SKIP");
      continue;
    }
    if (!src.enabled) {
      console.log("OFF");
      rows.push({
        code,
        source: id,
        result: "off",
        ms: 0,
        detail: "",
      });
      continue;
    }
    try {
      const meta = await runWithRequestProfile(profileFromSource(src), () =>
        scraper(code, { baseUrl: resolveBaseUrl(id, src) }),
      );
      const title = String(meta.title_zh || meta.title_ja || "").trim();
      const hasCover = Boolean(meta.cover_url);
      const ok = Boolean(title && hasCover);
      const ms = Date.now() - t0;
      const act = (meta.actresses || []).filter(Boolean).slice(0, 2).join(",") || "-";
      const result = ok ? "OK" : "PARTIAL";
      console.log(
        `${result.padEnd(7)} ${String(ms).padStart(5)}ms  cover=${hasCover ? "Y" : "N"}  act=${act}`,
      );
      if (title) console.log(`           ${title.slice(0, 72)}`);
      rows.push({
        code,
        source: id,
        result,
        ms,
        detail: title.slice(0, 40),
      });
    } catch (e) {
      const ms = Date.now() - t0;
      const err = String((e as Error).message || e);
      let short = err;
      if (/HTTP 403/.test(err)) short = "HTTP 403 (CF/拦)";
      else if (/HTTP 404/.test(err)) short = "HTTP 404";
      else if (/not found|no result|mismatch/i.test(err)) short = err.slice(0, 48);
      else short = err.slice(0, 64);
      console.log(`FAIL    ${String(ms).padStart(5)}ms  ${short}`);
      rows.push({ code, source: id, result: "FAIL", ms, detail: short });
    }
  }
  console.log("");
}

console.log("===== 汇总 (OK / PARTIAL / FAIL) =====");
const bySrc: Record<string, { ok: number; fail: number; partial: number }> = {};
for (const id of SOURCES) bySrc[id] = { ok: 0, fail: 0, partial: 0 };
for (const r of rows) {
  if (r.result === "OK") bySrc[r.source].ok++;
  else if (r.result === "PARTIAL") bySrc[r.source].partial++;
  else if (r.result === "FAIL") bySrc[r.source].fail++;
}
for (const id of SOURCES) {
  const s = bySrc[id];
  const samples = rows
    .filter((r) => r.source === id)
    .map((r) => `${r.result}${r.result === "FAIL" ? "(" + r.detail + ")" : ""}`)
    .join(" | ");
  console.log(
    `${String(id).padEnd(10)} ok=${s.ok} partial=${s.partial} fail=${s.fail}  :: ${samples}`,
  );
}
