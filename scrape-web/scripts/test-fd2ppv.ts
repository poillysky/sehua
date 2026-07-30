import { applyProxy } from "../src/proxy.js";
import { readConfig } from "../src/config.js";
import { applyFlareSolverr } from "../src/flaresolverr.js";
import {
  profileFromSource,
  runWithRequestProfile,
} from "../src/httpContext.js";
import { scrapeFd2ppv } from "../src/sources/extra.js";
import {
  defaultSourceConfig,
  resolveBaseUrl,
} from "../src/sources/registry.js";

const cfg = await readConfig();
applyProxy(cfg.proxyUrl || "");
applyFlareSolverr(cfg.flareSolverrUrl || "");
const src = cfg.sources.fd2ppv || defaultSourceConfig("fd2ppv");
// 新源默认要开 FS
if (!src.useFlareSolverr) src.useFlareSolverr = true;

console.log("proxy", cfg.proxyUrl || "(none)");
console.log("flare", cfg.flareSolverrUrl || "(none)");
console.log("base", resolveBaseUrl("fd2ppv", src));
console.log("");

const codes = process.argv.slice(2).length
  ? process.argv.slice(2)
  : ["FC2-PPV-4576037", "FC2-PPV-2856126", "FC2-PPV-4576456"];

for (const code of codes) {
  const t0 = Date.now();
  process.stdout.write(`${code} ... `);
  try {
    const meta = await runWithRequestProfile(profileFromSource(src), () =>
      scrapeFd2ppv(code, { baseUrl: resolveBaseUrl("fd2ppv", src) }),
    );
    console.log(`OK ${Date.now() - t0}ms`);
    console.log(`  title: ${String(meta.title_zh || meta.title_ja || "").slice(0, 70)}`);
    console.log(`  cover: ${meta.cover_url}`);
    console.log(`  act: ${(meta.actresses || []).join(",") || "-"}`);
  } catch (e) {
    console.log(`FAIL ${Date.now() - t0}ms ${(e as Error).message}`);
  }
}
