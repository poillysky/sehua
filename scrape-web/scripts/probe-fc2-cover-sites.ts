/**
 * 探测候选 FC2 封面站（默认走 FlareSolverr）
 */
import { applyProxy } from "../src/proxy.js";
import { readConfig } from "../src/config.js";
import { fetchText } from "../src/sources/http.js";
import {
  runWithRequestProfile,
} from "../src/httpContext.js";
import { applyFlareSolverr } from "../src/flaresolverr.js";

const cfg = await readConfig();
applyProxy(cfg.proxyUrl || "");
applyFlareSolverr(cfg.flareSolverrUrl || "");

const ids = process.argv.slice(2).length
  ? process.argv.slice(2)
  : ["4576037", "2856126"];

type Candidate = {
  name: string;
  url: (id: string) => string;
  pickCover: (html: string, id: string) => string | null;
  useFlare?: boolean;
};

function abs(u: string, base: string): string {
  try {
    return new URL(u, base).toString();
  } catch {
    return u;
  }
}

const candidates: Candidate[] = [
  {
    name: "fc2ppvdb",
    useFlare: true,
    url: (id) => `https://fc2ppvdb.com/articles/${id}`,
    pickCover: (html, id) => {
      const re = new RegExp(
        `<img[^>]+(?:alt=["'][^"']*${id}[^"']*["'][^>]+src=["']([^"']+)["']|src=["']([^"']+)["'][^>]+alt=["'][^"']*${id}[^"']*["'])`,
        "i",
      );
      const m = html.match(re);
      const u = m?.[1] || m?.[2];
      if (u) return abs(u, "https://fc2ppvdb.com/");
      const og = html.match(
        /property=["']og:image["'][^>]*content=["']([^"']+)/i,
      )?.[1];
      if (og) return abs(og, "https://fc2ppvdb.com/");
      const imgs = [...html.matchAll(/<img[^>]+src=["']([^"']+)["']/gi)].map(
        (x) => x[1],
      );
      const hit = imgs.find(
        (s) =>
          /storage|contents\.fc2|cloudfront|amazonaws|fc2ppvdb|upload/i.test(
            s,
          ) && !/logo|icon|avatar|sprite/i.test(s),
      );
      return hit ? abs(hit, "https://fc2ppvdb.com/") : null;
    },
  },
  {
    name: "fd2ppv",
    useFlare: true,
    url: (id) => `https://fd2ppv.cc/articles/${id}`,
    pickCover: (html, id) => {
      const re = new RegExp(
        `<img[^>]+(?:alt=["'][^"']*${id}[^"']*["'][^>]+src=["']([^"']+)["']|src=["']([^"']+)["'][^>]+alt=["'][^"']*${id}[^"']*["'])`,
        "i",
      );
      const m = html.match(re);
      const u = m?.[1] || m?.[2];
      if (u) return abs(u, "https://fd2ppv.cc/");
      const og = html.match(
        /property=["']og:image["'][^>]*content=["']([^"']+)/i,
      )?.[1];
      return og ? abs(og, "https://fd2ppv.cc/") : null;
    },
  },
  {
    name: "fc2club",
    useFlare: true,
    url: (id) => `https://fc2club.top/html/FC2-${id}.html`,
    pickCover: (html) => {
      const m =
        html.match(
          /<img[^>]+class=["'][^"']*responsive[^"']*["'][^>]+src=["']([^"']+)["']/i,
        ) ||
        html.match(
          /src=["']([^"']+)["'][^>]+class=["'][^"']*responsive[^"']*["']/i,
        );
      if (!m?.[1]) {
        const og = html.match(
          /property=["']og:image["'][^>]*content=["']([^"']+)/i,
        )?.[1];
        return og ? abs(og, "https://fc2club.top/") : null;
      }
      return abs(
        m[1].replace("../uploadfile", "/uploadfile"),
        "https://fc2club.top/",
      );
    },
  },
];

console.log("proxy", cfg.proxyUrl || "(none)");
console.log("flare", cfg.flareSolverrUrl || "(none)");
console.log("ids", ids.join(", "));
console.log("");

for (const id of ids) {
  for (const c of candidates) {
    const url = c.url(id);
    const t0 = Date.now();
    process.stdout.write(`${id} @ ${c.name.padEnd(10)} `);
    try {
      const html = await runWithRequestProfile(
        {
          proxyMode: "inherit",
          useFlareSolverr: c.useFlare !== false,
          timeoutMs: 60000,
        },
        () =>
          fetchText(url, {
            timeoutMs: 60000,
            referer: new URL(url).origin + "/",
          }),
      );
      const cover = c.pickCover(html, id);
      const title =
        html
          .match(/<h2[^>]*>\s*<a[^>]*>([\s\S]*?)<\/a>/i)?.[1]
          ?.replace(/<[^>]+>/g, "")
          .trim() ||
        html
          .match(/<h3[^>]*>([\s\S]*?)<\/h3>/i)?.[1]
          ?.replace(/<[^>]+>/g, "")
          .trim() ||
        html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim() ||
        "";
      console.log(
        `${cover ? "COVER" : "NO-COVER"} ${Date.now() - t0}ms len=${html.length}`,
      );
      if (title) console.log(`  title: ${title.slice(0, 70)}`);
      if (cover) console.log(`  cover: ${cover.slice(0, 140)}`);
      else console.log(`  head: ${html.slice(0, 180).replace(/\s+/g, " ")}`);
    } catch (e) {
      console.log(
        `FAIL ${Date.now() - t0}ms ${String((e as Error).message).slice(0, 120)}`,
      );
    }
  }
  console.log("");
}
