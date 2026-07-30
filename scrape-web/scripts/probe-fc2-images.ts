import { applyProxy } from "../src/proxy.js";
import { fetchText } from "../src/sources/http.js";
import { runWithRequestProfile } from "../src/httpContext.js";
import { pickOgImage } from "../src/sources/util.js";

applyProxy("http://192.168.2.88:7893");

const id = process.argv[2] || "4576037";
const html = await runWithRequestProfile({ proxyMode: "inherit" }, () =>
  fetchText(`https://adult.contents.fc2.com/article/${id}/`, {
    timeoutMs: 25000,
    referer: "https://adult.contents.fc2.com/",
  }),
);

console.log("og:image", pickOgImage(html));

const imgs = new Set();
for (const m of html.matchAll(
  /https?:\/\/[^"'\\\s<>]+?\.(?:jpg|jpeg|png|webp)/gi,
)) {
  const u = m[0].replace(/&amp;/g, "&");
  if (/storage|contents\.fc2|sample|thumb|image|file\//i.test(u)) imgs.add(u);
}
console.log("\nimage urls (" + imgs.size + "):");
for (const u of [...imgs].slice(0, 40)) console.log(u);

// common FC2 gallery patterns
const samples = [...html.matchAll(/data-src=["']([^"']+)["']/gi)].map((m) => m[1]);
const srcs = [...html.matchAll(/\ssrc=["']([^"']+\.(?:jpg|jpeg|png|webp)[^"']*)["']/gi)].map((m) => m[1]);
console.log("\ndata-src count", samples.length);
console.log("img src count", srcs.length);
for (const u of [...new Set([...samples, ...srcs])].slice(0, 30)) {
  if (/fc2|storage|sample|thumb/i.test(u)) console.log(" ", u.slice(0, 160));
}
