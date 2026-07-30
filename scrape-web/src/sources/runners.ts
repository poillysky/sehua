import { scrapeAirav } from "./airav.js";
import { scrapeAvmoo, scrapeAvsox } from "./avsox.js";
import { scrapeDmmMeta, toDmmCid } from "./dmm.js";
import {
  scrapeAvbase,
  scrapeCarib,
  scrapeFc2,
  scrapeFc2Hub,
  scrapeFd2ppv,
  scrapeHbox,
  scrapeMadou,
  scrapeMadouqu,
  scrapeMgstage,
  scrapeTheporndb,
  scrapeXhs,
} from "./extra.js";
import { scrapeJav321, scrapeJavlibrary } from "./jav321.js";
import { scrapeJavbus } from "./javbus.js";
import { scrapeJavdb } from "./javdb.js";
import { scrape7mmtv, scrapeFreejavbt, scrapeMissav } from "./missav.js";
import type { PartialMeta } from "./http.js";
import type { SourceId } from "./registry.js";

export type ScrapeFn = (
  code: string,
  opts: { baseUrl: string },
) => Promise<PartialMeta>;

/** 各源刮削实现；挂了就抛错，由主流程试下一个 */
export const SOURCE_SCRAPERS: Partial<Record<SourceId, ScrapeFn>> = {
  airav: (code, opts) =>
    scrapeAirav(code, {
      wikiBase: opts.baseUrl,
      useWiki: true,
      useIo: false,
    }),
  airav_io: (code, opts) =>
    scrapeAirav(code, {
      ioBase: opts.baseUrl,
      useWiki: false,
      useIo: true,
    }),
  javbus: (code, opts) => scrapeJavbus(code, { baseUrl: opts.baseUrl }),
  dmm: async (code, opts) => {
    if (!toDmmCid(code)) throw new Error("not dmm cid");
    return scrapeDmmMeta(code, { baseUrl: opts.baseUrl });
  },
  javdb: (code, opts) => scrapeJavdb(code, { baseUrl: opts.baseUrl }),
  avsox: (code, opts) => scrapeAvsox(code, { baseUrl: opts.baseUrl }),
  avmoo: (code, opts) => scrapeAvmoo(code, { baseUrl: opts.baseUrl }),
  jav321: (code, opts) => scrapeJav321(code, { baseUrl: opts.baseUrl }),
  javlibrary: (code, opts) => scrapeJavlibrary(code, { baseUrl: opts.baseUrl }),
  miss_av: (code, opts) => scrapeMissav(code, { baseUrl: opts.baseUrl }),
  sevenmmtv: (code, opts) => scrape7mmtv(code, { baseUrl: opts.baseUrl }),
  freejavbt: (code, opts) => scrapeFreejavbt(code, { baseUrl: opts.baseUrl }),
  mgstage: (code, opts) => scrapeMgstage(code, { baseUrl: opts.baseUrl }),
  fc2_hub: (code, opts) => scrapeFc2Hub(code, { baseUrl: opts.baseUrl }),
  fc2: (code, opts) => scrapeFc2(code, { baseUrl: opts.baseUrl }),
  fd2ppv: (code, opts) => scrapeFd2ppv(code, { baseUrl: opts.baseUrl }),
  carib: (code, opts) => scrapeCarib(code, { baseUrl: opts.baseUrl }),
  avbase: (code, opts) => scrapeAvbase(code, { baseUrl: opts.baseUrl }),
  madou: (code, opts) => scrapeMadou(code, { baseUrl: opts.baseUrl }),
  madouqu: (code, opts) => scrapeMadouqu(code, { baseUrl: opts.baseUrl }),
  hbox_jp: (code, opts) => scrapeHbox(code, { baseUrl: opts.baseUrl }),
  theporndb: (code, opts) => scrapeTheporndb(code, { baseUrl: opts.baseUrl }),
  xiao_huang_shu: (code, opts) => scrapeXhs(code, { baseUrl: opts.baseUrl }),
};
