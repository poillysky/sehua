import { NextResponse } from "next/server";
import { z } from "zod";

const schema = z.object({
  text: z.string().trim().min(1).max(500),
});

// 影视资源名常见噪声，翻译前先剥离
const MEDIA_NOISE_REGEX =
  /\b(1080[pP]?|720[pP]?|2160[pP]?|4[kK]|x26[45]|HEVC|H\.?264|H\.?265|BluRay|Blu-Ray|WEB[- ]?DL|WEBRip|HDR10?|DV|Remux|REPACK|PROPER|中字|简繁|繁体|简体|国语|粤语|双语|内嵌|外挂|合集|全集|完結|完结|第[一二三四五六七八九十\d]+季|第[一二三四五六七八九十\d]+集|S\d{1,2}E\d{1,2}|EP?\d{1,3}|\d{4}年?)\b|[\[\]()【】（）]/g;

class TranslateError extends Error {
  rateLimited: boolean;

  constructor(message: string, rateLimited = false) {
    super(message);
    this.name = "TranslateError";
    this.rateLimited = rateLimited;
  }
}

function detectLangPair(text: string): string | null {
  if (/[\u4e00-\u9fff]/.test(text)) return "zh-CN|en";
  if (/[\u3040-\u309f\u30a0-\u30ff]/.test(text)) return "ja|en";
  if (/[\uac00-\ud7af]/.test(text)) return "ko|en";

  if (/^[a-zA-Z0-9\s.,!?;:'"()\[\]{}<>@#%^&*~`|\-_/\\]+$/.test(text)) {
    return null;
  }

  return "auto|en";
}

function normalizeLangPair(langPair: string) {
  return langPair === "auto|en" ? "zh-CN|en" : langPair;
}

function toLibreTranslateLang(code: string) {
  const map: Record<string, string> = {
    "zh-CN": "zh",
    zh: "zh",
    ja: "ja",
    ko: "ko",
    en: "en",
  };

  return map[code] || code.split("-")[0];
}

function cleanMediaQuery(text: string) {
  return text
    .replace(MEDIA_NOISE_REGEX, " ")
    .replace(/[._\-+]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
}

function isLatinTitle(text: string) {
  return /^[a-zA-Z0-9\s:.'&!?,\-]+$/.test(text.trim());
}

function normalizeForMatch(text: string) {
  return text.toLowerCase().replace(/\s+/g, "");
}

function pickBestTmdbResult(results: any[], query: string) {
  const normalizedQuery = normalizeForMatch(query);

  return [...results].sort((a, b) => {
    const score = (item: any) => {
      const titles = [
        item.title,
        item.name,
        item.original_title,
        item.original_name,
      ].filter(Boolean);

      let value = item.popularity || 0;

      for (const title of titles) {
        const normalizedTitle = normalizeForMatch(String(title));

        if (normalizedTitle === normalizedQuery) {
          value += 1000;
        } else if (
          normalizedTitle.includes(normalizedQuery) ||
          normalizedQuery.includes(normalizedTitle)
        ) {
          value += 300;
        }
      }

      return value;
    };

    return score(b) - score(a);
  })[0];
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
) {
  try {
    return await fetch(url, {
      ...init,
      next: { revalidate: 0 },
      signal: AbortSignal.timeout(timeoutMs),
      headers: {
        "User-Agent": "SehuaTang-Search/1.0",
        ...init.headers,
      },
    });
  } catch (error: any) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") {
      throw new TranslateError("翻译服务响应超时，请稍后重试");
    }

    throw new TranslateError("无法连接翻译服务，请检查容器网络");
  }
}

function getSelfHostedTranslateUrl() {
  return process.env.TRANSLATE_API_URL?.replace(/\/$/, "") || "";
}

async function fetchTmdbEnglishDetail(item: any, apiKey: string) {
  const endpoint =
    item.media_type === "tv"
      ? `https://api.themoviedb.org/3/tv/${item.id}`
      : `https://api.themoviedb.org/3/movie/${item.id}`;

  const url = new URL(endpoint);

  url.searchParams.set("api_key", apiKey);
  url.searchParams.set("language", "en-US");

  const response = await fetchWithTimeout(url.toString());

  if (!response.ok) {
    return null;
  }

  const data = await response.json();

  const candidates = [
    data.original_title,
    data.title,
    data.original_name,
    data.name,
  ].filter(Boolean);

  return (
    candidates.find((title: string) => isLatinTitle(title))?.trim() || null
  );
}

async function translateWithTmdb(text: string): Promise<string | null> {
  const apiKey = process.env.TMDB_API_KEY;

  if (!apiKey) {
    return null;
  }

  const query = cleanMediaQuery(text);

  if (query.length < 2) {
    return null;
  }

  const url = new URL("https://api.themoviedb.org/3/search/multi");

  url.searchParams.set("api_key", apiKey);
  url.searchParams.set("query", query);
  url.searchParams.set("language", "zh-CN");
  url.searchParams.set("include_adult", "false");

  const response = await fetchWithTimeout(url.toString());

  if (!response.ok) {
    return null;
  }

  const data = await response.json();
  const results = (data.results || []).filter(
    (item: any) => item.media_type === "movie" || item.media_type === "tv",
  );

  if (!results.length) {
    return null;
  }

  const best = pickBestTmdbResult(results, query);
  const direct =
    [best.original_title, best.original_name, best.title, best.name]
      .filter(Boolean)
      .find((title: string) => isLatinTitle(title))
      ?.trim() || null;

  if (direct) {
    return direct;
  }

  return fetchTmdbEnglishDetail(best, apiKey);
}

async function translateWithLibreTranslate(text: string, langPair: string) {
  const baseUrl = getSelfHostedTranslateUrl();

  if (!baseUrl) {
    throw new TranslateError("未配置自建翻译服务地址");
  }

  const [source] = normalizeLangPair(langPair).split("|");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (process.env.TRANSLATE_API_KEY) {
    headers.Authorization = `Bearer ${process.env.TRANSLATE_API_KEY}`;
  }

  const response = await fetchWithTimeout(
    `${baseUrl}/translate`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        q: cleanMediaQuery(text) || text,
        source: toLibreTranslateLang(source),
        target: "en",
        format: "text",
      }),
    },
    30_000,
  );

  if (!response.ok) {
    throw new TranslateError(`自建翻译服务不可用 (${response.status})`);
  }

  const data = await response.json();
  const translatedText = data?.translatedText?.trim();

  if (!translatedText) {
    throw new TranslateError("翻译结果为空");
  }

  return translatedText;
}

async function translateWithMyMemory(text: string, langPair: string) {
  const url = new URL("https://api.mymemory.translated.net/get");
  const query = cleanMediaQuery(text) || text;

  url.searchParams.set("q", query);
  url.searchParams.set("langpair", langPair);

  if (process.env.TRANSLATE_API_EMAIL) {
    url.searchParams.set("de", process.env.TRANSLATE_API_EMAIL);
  }

  const response = await fetchWithTimeout(url.toString());

  if (response.status === 429) {
    throw new TranslateError("MyMemory 请求过于频繁 (429)", true);
  }

  if (!response.ok) {
    throw new TranslateError(
      `MyMemory 翻译不可用 (${response.status})`,
      response.status === 429,
    );
  }

  const data = await response.json();
  const translatedText = data?.responseData?.translatedText?.trim();

  if (!translatedText) {
    throw new TranslateError("翻译结果为空");
  }

  if (
    translatedText.includes("MYMEMORY WARNING") ||
    data?.quotaFinished === true
  ) {
    throw new TranslateError("MyMemory 今日配额已用尽", true);
  }

  return translatedText;
}

async function translateWithGoogle(text: string, langPair: string) {
  const [source] = langPair.split("|");
  const query = cleanMediaQuery(text) || text;
  const url = new URL("https://translate.googleapis.com/translate_a/single");

  url.searchParams.set("client", "gtx");
  url.searchParams.set("sl", source === "auto" ? "auto" : toLibreTranslateLang(source));
  url.searchParams.set("tl", "en");
  url.searchParams.set("dt", "t");
  url.searchParams.set("q", query);

  const response = await fetchWithTimeout(url.toString());

  if (response.status === 429) {
    throw new TranslateError("翻译请求过于频繁，请稍后再试", true);
  }

  if (!response.ok) {
    throw new TranslateError(`备用翻译不可用 (${response.status})`);
  }

  const data = await response.json();
  const translatedText = data?.[0]
    ?.map((item: string[]) => item?.[0])
    .join("")
    ?.trim();

  if (!translatedText) {
    throw new TranslateError("翻译结果为空");
  }

  return translatedText;
}

async function translateWithPublicApis(text: string, langPair: string) {
  const normalizedPair = normalizeLangPair(langPair);
  const query = cleanMediaQuery(text) || text;

  try {
    return await translateWithGoogle(query, normalizedPair);
  } catch (error) {
    if (error instanceof TranslateError && error.rateLimited) {
      console.warn("Google limited, fallback to MyMemory:", error.message);

      return translateWithMyMemory(query, normalizedPair);
    }

    console.warn("Google failed, fallback to MyMemory:", error);

    return translateWithMyMemory(query, normalizedPair);
  }
}

async function translateText(text: string, langPair: string) {
  // 1. TMDB 官方片名（影视资源最标准）
  const tmdbTitle = await translateWithTmdb(text);

  if (tmdbTitle) {
    return tmdbTitle;
  }

  const selfHostedUrl = getSelfHostedTranslateUrl();
  const allowFallback = process.env.TRANSLATE_FALLBACK === "1";

  // 2. 自建翻译
  if (selfHostedUrl) {
    try {
      return await translateWithLibreTranslate(text, langPair);
    } catch (error) {
      if (!allowFallback) {
        throw error;
      }

      console.warn("Self-hosted translate failed, fallback to public APIs:", error);
    }
  }

  // 3. 公网机器翻译（Google 优先，更适合影视短语）
  return translateWithPublicApis(text, langPair);
}

const handler = async (request: Request) => {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { data: null, message: "Invalid JSON body", status: 400 },
      { status: 400 },
    );
  }

  let safeParams;

  try {
    safeParams = schema.parse(body);
  } catch (error: any) {
    const { path, message } = error.errors?.[0] || {};

    return NextResponse.json(
      {
        data: null,
        message: path ? `${path[0]}: ${message}` : message,
        status: 400,
      },
      { status: 400 },
    );
  }

  const langPair = detectLangPair(safeParams.text);

  if (!langPair) {
    return NextResponse.json({
      data: { text: safeParams.text, alreadyEnglish: true },
      message: "success",
      status: 200,
    });
  }

  try {
    const translatedText = await translateText(safeParams.text, langPair);

    return NextResponse.json({
      data: { text: translatedText, alreadyEnglish: false },
      message: "success",
      status: 200,
    });
  } catch (error: any) {
    console.error("Translation error:", error);

    return NextResponse.json(
      {
        data: null,
        message: error?.message || "翻译失败，请稍后重试",
        status: 500,
      },
      { status: 500 },
    );
  }
};

export { handler as POST };
