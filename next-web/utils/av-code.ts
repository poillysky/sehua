/** 从标题/文件名提取与指定前缀匹配的番号 */

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function pushCode(out: Set<string>, prefix: string, num: string) {
  let rawNum = (num || "").toUpperCase();
  if (!rawNum) return;
  // 列表只要「前缀-数字」：去掉 C/CX/U 等社区尾缀，非纯数字丢弃
  rawNum = rawNum.replace(/[A-Z]+$/, "");
  if (!/^\d{2,6}$/.test(rawNum)) return;
  out.add(`${prefix.toUpperCase()}-${rawNum}`);
}

/** 无码日期型：010122-001 / 010122_001 */
function extractDateStyle(text: string, label: string, out: Set<string>) {
  const re = /(?:^|[^A-Z0-9])(\d{6})[-_](\d{2,3})(?![A-Z0-9])/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.add(`${label.toUpperCase()}-${m[1]}-${m[2]}`);
  }
}

/**
 * 在一段文本中找出属于 prefix 的番号。
 * 返回规范化编号，如 SSIS-001、FC2-PPV-1234567。
 */
export function extractCodesForPrefix(text: string, prefix: string): string[] {
  const src = String(text || "");
  const p = String(prefix || "").trim();
  if (!src || !p) return [];

  const upper = src.toUpperCase();
  const pUpper = p.toUpperCase();
  const out = new Set<string>();

  // FC2 / FC2PPV 互斥：FC2=非PPV，FC2PPV=仅付费配信
  if (pUpper === "FC2" || pUpper === "FC2PPV") {
    let m: RegExpExecArray | null;
    if (pUpper === "FC2PPV") {
      const rePpv = /FC2[-_\s]?PPV[-_\s]?(\d{5,10})/gi;
      while ((m = rePpv.exec(upper)) !== null) {
        out.add(`FC2-PPV-${m[1]}`);
      }
      return Array.from(out);
    }
    // FC2：只要非 PPV；全文带 PPV 标记的整段跳过（避免标题写成 FC2-xxx 误入）
    if (/FC2[-_\s]?PPV/i.test(upper)) {
      return [];
    }
    const reFc2 =
      /(?:^|[^A-Z0-9])FC2(?![-_\s]?PPV)[-_\s]?(\d{5,10})(?![A-Z0-9])/gi;
    while ((m = reFc2.exec(upper)) !== null) {
      out.add(`FC2-${m[1]}`);
    }
    return Array.from(out);
  }

  // 加勒比 / 一本道等：站名 + 日期编号
  if (
    [
      "CARIB",
      "CARIBBEAN",
      "CARIBBEANCOM",
      "CARIBPR",
      "1PON",
      "1PONDO",
      "PACO",
      "PACOPACOMAMA",
      "10MU",
      "10MUSUME",
    ].includes(pUpper)
  ) {
    const label =
      pUpper === "CARIBBEAN" || pUpper === "CARIBBEANCOM"
        ? "CARIB"
        : pUpper === "CARIBPR"
          ? "CARIBPR"
          : pUpper === "1PONDO"
            ? "1PON"
            : pUpper === "10MUSUME"
              ? "10MU"
              : pUpper === "PACOPACOMAMA"
                ? "PACO"
                : pUpper;
    if (upper.includes(pUpper) || upper.includes(label)) {
      extractDateStyle(upper, label, out);
    }
    // 也兼容 CARIB-010122-001 这种已带前缀写法
    const esc = escapeRegExp(pUpper);
    const rePref = new RegExp(
      `${esc}[-_\\s]?(\\d{6})[-_](\\d{2,3})(?![A-Z0-9])`,
      "gi",
    );
    let m: RegExpExecArray | null;
    while ((m = rePref.exec(upper)) !== null) {
      out.add(`${label}-${m[1]}-${m[2]}`);
    }
    if (out.size) return Array.from(out);
  }

  // 人妻斩 / 金8：H0930-ki241208、KIN8-1638、gachinco-gachi1092
  if (["H0930", "C0930", "H4610"].includes(pUpper)) {
    const esc = escapeRegExp(pUpper);
    const re = new RegExp(
      `${esc}[-_\\s]?([A-Z0-9]{3,24})(?![A-Z0-9])`,
      "gi",
    );
    let m: RegExpExecArray | null;
    while ((m = re.exec(upper)) !== null) {
      out.add(`${pUpper}-${m[1].toUpperCase()}`);
    }
    if (out.size) return Array.from(out);
  }
  if (pUpper === "KIN8") {
    const re = /KIN8[-_\s]?(\d{3,5})(?![A-Z0-9])/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(upper)) !== null) {
      out.add(`KIN8-${m[1]}`);
    }
    if (out.size) return Array.from(out);
  }
  if (pUpper === "GACHINCO" || pUpper === "GACHI") {
    const re = /GACHI(?:NCO)?[-_\s]?GACHI?(\d{3,5})/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(upper)) !== null) {
      out.add(`GACHI-${m[1]}`);
    }
    if (out.size) return Array.from(out);
  }

  // 欧美厂牌：Studio.YY.MM.DD / Studio_YY.MM.DD → STUDIO-YYMMDD
  if (isWesternStudioPrefix(pUpper)) {
    extractWesternStudioCodes(upper, pUpper, out);
    if (out.size) return Array.from(out);
  }

  // 通用：PREFIX-123；兼容 230ORECO-192 这类站前数字
  const esc = escapeRegExp(pUpper);
  const re = new RegExp(
    `(?:^|[^A-Z0-9])(?:\\d{2,3})?${esc}[-_\\s]?(\\d{2,6}(?:[A-Z]{1,2})?)(?![A-Z0-9])`,
    "gi",
  );
  let m: RegExpExecArray | null;
  while ((m = re.exec(upper)) !== null) {
    pushCode(out, pUpper, m[1]);
  }

  return Array.from(out);
}

/** 欧美厂牌（与 av-makers.western.json 对齐；大写比对） */
const WESTERN_STUDIO_PREFIXES = new Set(
  [
    "BRAZZERS",
    "BLACKED",
    "BLACKEDRAW",
    "TUSHY",
    "VIXEN",
    "DEEPER",
    "REALITYKINGS",
    "RK",
    "NAUGHTYAMERICA",
    "BANGBROS",
    "BANGBUS",
    "MOFOS",
    "FAKETAXI",
    "FAKEHUB",
    "EVILANGEL",
    "JULESJORDAN",
    "PURETABOO",
    "ADULTTIME",
    "DORCEL",
    "PRIVATE",
    "ONLYFANS",
    "MANYVIDS",
    "DIGITALPLAYGROUND",
    "ELEGANTANGEL",
    "LETHALHARDCORE",
    "ANALVIDS",
    "KINK",
    "PUBLICAGENT",
    "FAMILYSTROKES",
    "TEAMSKEET",
    "BRATTYSIS",
    "NUBILES",
  ].map((s) => s.toUpperCase()),
);

export function isWesternStudioPrefix(prefix: string): boolean {
  const key = String(prefix || "")
    .trim()
    .toUpperCase()
    .replace(/[_\s-]/g, "");
  return WESTERN_STUDIO_PREFIXES.has(key);
}

function westernStudioKey(prefix: string): string {
  return String(prefix || "")
    .trim()
    .toUpperCase()
    .replace(/[_-\s]/g, "");
}

/** Brazzers.24.06.20 / Blacked_23.01.15 → BRAZZERS-240620 */
function extractWesternStudioCodes(
  upper: string,
  prefixUpper: string,
  out: Set<string>,
) {
  const key = westernStudioKey(prefixUpper);
  const esc = escapeRegExp(key);
  // Studio.YY.MM.DD / Studio-YY-MM-DD / Studio_YY.MM.DD
  const reDate = new RegExp(
    `${esc}[._\\-\\s]?(\\d{2})[._\\-](\\d{2})[._\\-](\\d{2})(?!\\d)`,
    "gi",
  );
  let m: RegExpExecArray | null;
  while ((m = reDate.exec(upper)) !== null) {
    out.add(`${key}-${m[1]}${m[2]}${m[3]}`);
  }
  // Studio.E123 / Studio-12345（部分系列）
  const reEp = new RegExp(
    `${esc}[._\\-\\s]?(?:E|EP)?(\\d{3,6})(?![A-Z0-9])`,
    "gi",
  );
  while ((m = reEp.exec(upper)) !== null) {
    // 避免与日期片段重复抢短数字；至少 3 位
    if (m[1].length >= 3) out.add(`${key}-${m[1]}`);
  }
}

/** 排序键：按主数字升序，再比完整字符串 */
export function codeSortKey(code: string): [number, number, string] {
  const parts = String(code || "")
    .toUpperCase()
    .match(/\d+/g);
  const a = parts?.[0] ? Number(parts[0]) : 0;
  const b = parts?.[1] ? Number(parts[1]) : 0;
  return [a, b, String(code || "").toUpperCase()];
}

export function compareCodes(a: string, b: string): number {
  const ka = codeSortKey(a);
  const kb = codeSortKey(b);
  if (ka[0] !== kb[0]) return ka[0] - kb[0];
  if (ka[1] !== kb[1]) return ka[1] - kb[1];
  return ka[2].localeCompare(kb[2]);
}

/** 点番号 → 精确搜索；日本分区可带 jp=1 以启用中文/破解偏好 */
export function codeSearchHref(
  code: string,
  options?: { japanPrefs?: boolean },
): string {
  const params = new URLSearchParams();
  params.set("keyword", code);
  params.set("matchMode", "exact");
  if (options?.japanPrefs) {
    params.set("jp", "1");
  }
  return `/search?${params.toString()}`;
}

/** FC2 / FC2-PPV 番号（封面偏横图） */
export function isFc2Code(code: string): boolean {
  return /^FC2(-PPV)?-\d+/i.test(String(code || "").trim());
}

/** 无码 / 国产：刮削与展示均整图，不按有码右半幅裁 */
export function isFullCoverCode(code: string): boolean {
  const c = String(code || "").trim().toUpperCase();
  if (!c) return false;
  if (isFc2Code(c)) return true;
  if (/^\d{6}[-_]\d{2,3}$/.test(c)) return true;
  if (
    /^(CARIB(?:BEAN(?:COM)?)?|CARIBPR|1PON(?:DO)?|PACO(?:PACOMAMA)?|HEYZO|TOKYO[-_]?HOT|MURMUR|KIN8|GACHI(?:NCO)?|H0930|C0930|H4610|10MU(?:SUME)?|XXX[-_]?AV|COSPURI)/i.test(
      c,
    )
  ) {
    return true;
  }
  return /^(MD|MKY|PMX|TMY|TZ|CUS|LY|MSD|MSQ|91CM|JVID|DOM|DSUA|EMX|FSOG|HKG|IDG|JD|KCM|LAA|MAD|MAH|MB|MCY|MDC|MDS|ML|MMZ|MPG|MSG|MTVQ|MXJ|MZQ|NHK|NMH|NMS|OMG|PCA|PM|RAS|SAT|SAO|SEX|SMD|TDMY|TG|TMW|UA|WDM|XKVP|XJX|YM|YOK|ZMX)/i.test(
    c,
  );
}

/** 番号前缀是否按横图封面展示（无码厂牌） */
export function isLandscapeCoverPrefix(prefix: string): boolean {
  const p = String(prefix || "").trim().toUpperCase().replace(/_/g, "-");
  if (!p) return false;
  if (p === "FC2" || p === "FC2PPV" || p.startsWith("FC2")) return true;
  return /^(CARIB(?:BEAN(?:COM)?)?|CARIBPR|1PON(?:DO)?|PACO(?:PACOMAMA)?|HEYZO|TOKYO[-_]?HOT|MURMUR|KIN8|GACHI(?:NCO)?|H0930|C0930|H4610|10MU(?:SUME)?|XXX[-_]?AV|COSPURI)$/i.test(
    p,
  );
}
