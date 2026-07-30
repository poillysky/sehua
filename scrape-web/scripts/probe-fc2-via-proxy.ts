import { ProxyAgent, fetch as ufetch } from "undici";
import { applyProxy, getActiveProxy } from "../src/proxy.js";
import { fetchText } from "../src/sources/http.js";
import { runWithRequestProfile } from "../src/httpContext.js";
import { scrapeFc2 } from "../src/sources/extra.js";

const PROXY = process.env.SCRAPE_PROXY || "http://192.168.2.88:7893";
const id = process.argv[2] || "4576037";
const article = `https://adult.contents.fc2.com/article/${id}/`;

console.log("PROXY", PROXY);

console.log("\n=== direct ===");
try {
  await ufetch("https://adult.contents.fc2.com/", {
    signal: AbortSignal.timeout(10000),
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  console.log("direct OK (unexpected)");
} catch (e: any) {
  console.log("direct FAIL", e.cause?.code || e.message);
}

console.log("\n=== ProxyAgent explicit ===");
try {
  const agent = new ProxyAgent(PROXY);
  const res = await ufetch("https://adult.contents.fc2.com/", {
    signal: AbortSignal.timeout(20000),
    headers: { "User-Agent": "Mozilla/5.0" },
    dispatcher: agent,
  });
  const html = await res.text();
  console.log(
    "status",
    res.status,
    "len",
    html.length,
    "title",
    (html.match(/<title[^>]*>([^<]*)/i) || [])[1]?.slice(0, 80),
  );
} catch (e: any) {
  console.log("FAIL", e.message, e.cause?.code, e.cause?.message);
}

console.log("\n=== applyProxy + inherit (same as scrape-web) ===");
applyProxy(PROXY);
console.log("activeProxy", getActiveProxy());
await runWithRequestProfile({ proxyMode: "inherit" }, async () => {
  try {
    const html = await fetchText(article, {
      timeoutMs: 25000,
      referer: "https://adult.contents.fc2.com/",
    });
    const title = (html.match(/<title[^>]*>([^<]*)/i) || [])[1] || "";
    const notFound = /未找到|お探しの商品|販売を終了/i.test(html);
    console.log(
      "fetchText OK len",
      html.length,
      "notFound",
      notFound,
      "title",
      title.slice(0, 80),
    );
  } catch (e: any) {
    console.log(
      "fetchText FAIL",
      e.message,
      e.cause?.code || "",
      e.cause?.message || "",
    );
  }
  try {
    const meta = await scrapeFc2(`FC2-PPV-${id}`);
    console.log("scrapeFc2 OK", JSON.stringify(meta, null, 2));
  } catch (e: any) {
    console.log("scrapeFc2 FAIL", e.message);
  }
});

console.log("\n=== proxyMode=on ===");
await runWithRequestProfile({ proxyMode: "on" }, async () => {
  try {
    const html = await fetchText("https://adult.contents.fc2.com/", {
      timeoutMs: 20000,
    });
    console.log(
      "on OK",
      html.length,
      (html.match(/<title[^>]*>([^<]*)/i) || [])[1]?.slice(0, 60),
    );
  } catch (e: any) {
    console.log("on FAIL", e.message, e.cause?.code || "");
  }
});
