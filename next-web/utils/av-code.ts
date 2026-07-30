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

  // FC2 / FC2PPV
  if (pUpper === "FC2" || pUpper === "FC2PPV") {
    const rePpv = /FC2[-_]?PPV[-_\s]?(\d{5,10})/gi;
    let m: RegExpExecArray | null;
    while ((m = rePpv.exec(upper)) !== null) {
      out.add(`FC2-PPV-${m[1]}`);
    }
    if (pUpper === "FC2") {
      const reFc2 = /(?:^|[^A-Z0-9])FC2(?![-_]?PPV)[-_\s]?(\d{5,10})(?![A-Z0-9])/gi;
      while ((m = reFc2.exec(upper)) !== null) {
        out.add(`FC2-${m[1]}`);
      }
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
