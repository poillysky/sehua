import { applyProxy } from "../src/proxy.js";
import { readConfig } from "../src/config.js";
import { fetchText } from "../src/sources/http.js";
import { runWithRequestProfile } from "../src/httpContext.js";
import { applyFlareSolverr } from "../src/flaresolverr.js";
import fs from "node:fs";

const cfg = await readConfig();
applyProxy(cfg.proxyUrl || "");
applyFlareSolverr(cfg.flareSolverrUrl || "");

const id = process.argv[2] || "4576037";
const url = `https://fd2ppv.cc/articles/${id}`;
const html = await runWithRequestProfile(
  { proxyMode: "inherit", useFlareSolverr: true, timeoutMs: 60000 },
  () => fetchText(url, { timeoutMs: 60000, referer: "https://fd2ppv.cc/" }),
);
fs.writeFileSync(`data/fd2ppv-${id}.html`, html);
console.log("len", html.length, "saved data/fd2ppv-" + id + ".html");

const imgs = [...html.matchAll(/<img\b[^>]*>/gi)].map((m) => m[0]);
console.log("img tags", imgs.length);
for (const tag of imgs.slice(0, 30)) {
  console.log(tag.replace(/\s+/g, " ").slice(0, 200));
}
console.log("\n--- urls ---");
for (const m of html.matchAll(
  /(?:src|data-src|href|content)=["']([^"']+\.(?:jpg|jpeg|png|webp)[^"']*)["']/gi,
)) {
  const u = m[1];
  if (/logo|icon|avatar|sprite|emoji|flag/i.test(u)) continue;
  console.log(u.slice(0, 160));
}
