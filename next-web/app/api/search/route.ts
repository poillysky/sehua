import { NextResponse } from "next/server";
import { z } from "zod";

import { search as searchResources } from "@/app/api/graphql/service";
import {
  getCachedSearch,
  getSearchCacheKey,
  setCachedSearch,
} from "@/lib/searchCache";
import {
  SEARCH_PARAMS,
  SEARCH_KEYWORD_LENGTH_MIN,
  SEARCH_KEYWORD_LENGTH_MAX,
  SEARCH_PAGE_SIZE,
  DEFAULT_FILTER_TIME,
  DEFAULT_FILTER_SIZE,
  normalizeMatchMode,
  normalizeSortType,
} from "@/config/constant";

const schema = z.object({
  keyword: z
    .string()
    .min(SEARCH_KEYWORD_LENGTH_MIN)
    .max(SEARCH_KEYWORD_LENGTH_MAX),
  offset: z.coerce.number().min(0).default(0),
  limit: z.coerce
    .number()
    .min(1)
    .max(SEARCH_PAGE_SIZE)
    .default(SEARCH_PAGE_SIZE),
  sortType: z.string().optional(),
  filterTime: z.enum(SEARCH_PARAMS.filterTime).default(DEFAULT_FILTER_TIME),
  filterSize: z.enum(SEARCH_PARAMS.filterSize).default(DEFAULT_FILTER_SIZE),
  matchMode: z.enum(SEARCH_PARAMS.matchMode).optional(),
  fuzzy: z.enum(["0", "1"]).optional(),
  withTotalCount: z
    .enum(["0", "1"])
    .transform((value) => value === "1")
    .default("1"),
});

const handler = async (request: Request) => {
  const { searchParams } = new URL(request.url);
  const params = Object.fromEntries(searchParams.entries());

  let safeParams;

  try {
    const parsed = schema.parse(params);

    safeParams = {
      ...parsed,
      sortType: normalizeSortType(parsed.sortType),
      matchMode: normalizeMatchMode({
        matchMode: parsed.matchMode,
        fuzzy: parsed.fuzzy,
      }),
    };
  } catch (error: any) {
    console.error(error);

    const { path, message } = error.errors[0] || {};
    const errMessage = path ? `${path[0]}: ${message}` : message;

    return NextResponse.json(
      {
        data: null,
        message: errMessage || "Invalid request",
        status: 400,
      },
      {
        status: 400,
      },
    );
  }

  try {
    const cacheKey = getSearchCacheKey(safeParams);
    const cached = getCachedSearch(cacheKey);

    if (cached) {
      return NextResponse.json(
        {
          data: cached,
          message: "success",
          status: 200,
          cached: true,
        },
        {
          status: 200,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
          },
        },
      );
    }

    const data = await searchResources(null, { queryInput: safeParams });

    setCachedSearch(cacheKey, data);

    return NextResponse.json(
      {
        data,
        message: "success",
        status: 200,
      },
      {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      },
    );
  } catch (error: any) {
    console.error(error);

    return NextResponse.json(
      {
        data: null,
        message: error?.message || "Internal Server Error",
        status: 500,
      },
      {
        status: 500,
      },
    );
  }
};

export { handler as GET, handler as POST };
