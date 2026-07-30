const FS = process.env.FS_URL || "http://192.168.2.38:8191/v1";
const SCRAPE = process.env.SCRAPE_ORIGIN || "http://127.0.0.1:9209";

console.log("=== FlareSolverr ready ===");
const ready = await (await fetch("http://192.168.2.38:8191/")).json();
console.log(ready);

console.log("\n=== FS request.get httpbin ===");
const t0 = Date.now();
const fsRes = await fetch(FS, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    cmd: "request.get",
    url: "https://httpbin.org/get",
    maxTimeout: 20000,
  }),
});
const fsJson = await fsRes.json();
console.log({
  http: fsRes.status,
  status: fsJson.status,
  message: fsJson.message,
  solStatus: fsJson.solution?.status,
  ms: Date.now() - t0,
});

console.log("\n=== scrape-web config ===");
let cfg;
try {
  const r = await fetch(`${SCRAPE}/api/config`);
  const text = await r.text();
  cfg = JSON.parse(text);
  console.log({
    flareSolverrUrl: cfg.flareSolverrUrl,
    flareSolverrEnabled: cfg.flareSolverrEnabled,
    proxy: cfg.activeProxy || cfg.proxyUrl,
  });
  for (const id of ["fc2_hub", "javdb", "miss_av", "javlibrary"]) {
    const x = (cfg.sources || []).find((s) => s.id === id);
    console.log(id, {
      enabled: x?.enabled,
      useFlareSolverr: x?.useFlareSolverr,
    });
  }
} catch (e) {
  console.log("config FAIL", e.message);
  cfg = null;
}

if (cfg && !cfg.flareSolverrEnabled) {
  console.log("\n=== PUT flareSolverrUrl ===");
  const put = await fetch(`${SCRAPE}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flareSolverrUrl: FS }),
  });
  const saved = await put.json();
  console.log({
    ok: put.ok,
    flareSolverrUrl: saved.flareSolverrUrl,
    flareSolverrEnabled: saved.flareSolverrEnabled,
  });
}
