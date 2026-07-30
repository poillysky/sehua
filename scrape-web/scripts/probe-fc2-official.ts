import { scrapeFc2 } from "../src/sources/extra.js";
import { fetchText } from "../src/sources/http.js";
import { readConfig } from "../src/config.js";
import { runWithRequestProfile } from "../src/httpContext.js";

const id = process.argv[2] || "4576037";
const base = "https://adult.contents.fc2.com";
const urls = [
  `${base}/`,
  `${base}/article/${id}/`,
  `${base}/article_search/?id=${id}&l=zh&ex=none`,
];

const cfg = await readConfig();
const src = cfg.sources.fc2;
console.log("proxy:", cfg.proxy || "(none)");
console.log("fc2 source:", JSON.stringify(src, null, 2));
console.log("id:", id);
console.log("");

await runWithRequestProfile(
  {
    cookie: src?.cookie,
    userAgent: src?.userAgent,
    proxyMode: src?.proxyMode || "inherit",
    timeoutMs: src?.timeoutMs,
    retry: src?.retry,
    useFlareSolverr: src?.useFlareSolverr,
    proxy: cfg.proxy,
  },
  async () => {
    for (const url of urls) {
      const t0 = Date.now();
      try {
        const html = await fetchText(url, {
          timeoutMs: 25000,
          referer: `${base}/`,
        });
        const notFound =
          /お探しの商品|未找到您要找的商品|この商品は販売を終了|この商品は取扱いできません/i.test(
            html,
          );
        const title = (html.match(/<title[^>]*>([^<]*)/i) || [])[1] || "";
        const ogTitle =
          (
            html.match(
              /property=["']og:title["'][^>]*content=["']([^"']+)/i,
            ) ||
            html.match(
              /content=["']([^"']+)["'][^>]*property=["']og:title["']/i,
            ) ||
            []
          )[1] || "";
        const ogImage =
          (
            html.match(
              /property=["']og:image["'][^>]*content=["']([^"']+)/i,
            ) ||
            html.match(
              /content=["']([^"']+)["'][^>]*property=["']og:image["']/i,
            ) ||
            []
          )[1] || "";
        console.log(`HTTP-OK ${Date.now() - t0}ms ${url}`);
        console.log(`  len=${html.length} notFoundFlag=${notFound}`);
        console.log(`  <title>= ${title.slice(0, 100)}`);
        console.log(`  og:title= ${ogTitle.slice(0, 100) || "-"}`);
        console.log(`  og:image= ${ogImage.slice(0, 120) || "-"}`);
        if (notFound || /未找到|お探しの商品/.test(title + ogTitle)) {
          const idx = html.search(/未找到|お探しの商品|販売を終了/);
          if (idx >= 0) {
            console.log(
              `  snip= ${html
                .slice(Math.max(0, idx - 40), idx + 80)
                .replace(/\s+/g, " ")}`,
            );
          }
        }
      } catch (e) {
        console.log(`HTTP-FAIL ${Date.now() - t0}ms ${url}`);
        console.log(`  ${String((e as Error).message || e).slice(0, 400)}`);
      }
      console.log("");
    }

    console.log("--- scrapeFc2() ---");
    try {
      const meta = await scrapeFc2(`FC2-PPV-${id}`, { baseUrl: base });
      console.log("scrape OK", meta);
    } catch (e) {
      console.log("scrape FAIL:", String((e as Error).message || e));
    }
  },
);
