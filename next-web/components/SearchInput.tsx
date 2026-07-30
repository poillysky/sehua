/* eslint-disable jsx-a11y/no-static-element-interactions */
/* eslint-disable jsx-a11y/click-events-have-key-events */
"use client";

import { Button, Spinner, Tooltip } from "@nextui-org/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import { SearchIcon, TranslateIcon } from "@/components/icons";
import {
  DEFAULT_MATCH_MODE,
  MatchMode,
  SEARCH_PARAMS,
} from "@/config/constant";
import {
  getSearchPreferences,
  saveSearchPreferences,
  type SearchKind,
} from "@/hooks/useSearchPreferences";
import { $env, Toast } from "@/utils";

export const SearchInput = ({
  defaultValue = "",
  isReplace = false,
  variant = "default",
  japanPrefs = false,
  /** 强制初始模式（如女优结果页） */
  defaultSearchKind,
}: {
  defaultValue?: string;
  isReplace?: boolean;
  /** 右上角紧凑搜索条：输入 + 类型 + 按钮 */
  variant?: "default" | "hero";
  /** 日本分区：搜索带 jp=1，启用中文/破解偏好 */
  japanPrefs?: boolean;
  defaultSearchKind?: SearchKind;
}) => {
  const [keyword, setKeyword] = useState("");
  const [matchMode, setMatchMode] = useState<MatchMode>(DEFAULT_MATCH_MODE);
  const [searchKind, setSearchKind] = useState<SearchKind>(
    defaultSearchKind || "resource",
  );
  const [loading, setLoading] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [active, setActive] = useState(false);
  const [errMessage, setErrMessage] = useState("");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const t = useTranslations();

  useEffect(() => {
    setLoading(false);
  }, [searchParams]);

  useEffect(() => {
    if (!loading) {
      return;
    }

    const timer = window.setTimeout(() => setLoading(false), 30000);

    return () => window.clearTimeout(timer);
  }, [loading]);

  useEffect(() => {
    if (defaultValue) {
      setKeyword(defaultValue);
    }
  }, [defaultValue]);

  useEffect(() => {
    const prefs = getSearchPreferences();
    setMatchMode(prefs.matchMode || DEFAULT_MATCH_MODE);
    if (defaultSearchKind) {
      setSearchKind(defaultSearchKind);
      return;
    }
    if (pathname?.startsWith("/actress")) {
      setSearchKind("actress");
      return;
    }
    setSearchKind(prefs.searchKind || "resource");
  }, [defaultSearchKind, pathname]);

  function handleKindChange(next: SearchKind) {
    setSearchKind(next);
    saveSearchPreferences({ searchKind: next });
  }

  function handleSearch() {
    const q = keyword.trim();
    setKeyword(q);

    if (!q) {
      return;
    }

    if (q.length < 2) {
      setErrMessage(t("Toast.keyword_too_short"));
      return;
    }

    const nextKeyword = q.length > 100 ? q.slice(0, 100) : q;
    if (nextKeyword !== q) {
      setKeyword(nextKeyword);
    }

    saveSearchPreferences({ matchMode, searchKind });

    if (searchKind === "actress") {
      const params = new URLSearchParams();
      params.set("keyword", nextKeyword);
      if (japanPrefs || searchParams.get("jp") === "1") {
        params.set("jp", "1");
      }
      const same =
        pathname?.startsWith("/actress") &&
        searchParams.get("keyword") === nextKeyword &&
        !searchParams.get("p");
      if (same) return;
      setLoading(true);
      const url = `/actress?${params.toString()}`;
      // 已在结果页换词：replace，减少历史污染
      const replaceNav =
        isReplace || Boolean(pathname?.startsWith("/actress"));
      if (replaceNav) router.replace(url);
      else router.push(url);
      return;
    }

    const currentMode = searchParams.get("matchMode") || "smart";
    const sameKeyword = searchParams.get("keyword") === nextKeyword;
    const sameMode =
      (matchMode === "smart" && currentMode === "smart") ||
      matchMode === currentMode;
    if (
      pathname?.startsWith("/search") &&
      sameKeyword &&
      sameMode &&
      !searchParams.get("p")
    ) {
      return;
    }

    const params = new URLSearchParams();
    const preferences = getSearchPreferences();

    params.set("keyword", nextKeyword);

    if (preferences.sortType) {
      params.set("sortType", preferences.sortType);
    }

    if (matchMode && matchMode !== "smart") {
      params.set("matchMode", matchMode);
    }

    if (japanPrefs || searchParams.get("jp") === "1") {
      params.set("jp", "1");
    }

    const url = `/search?${params.toString()}`;

    setLoading(true);
    const replaceNav =
      isReplace || Boolean(pathname?.startsWith("/search"));
    if (replaceNav) {
      router.replace(url);
    } else {
      router.push(url);
    }
  }

  function handleKeyup(e: any) {
    if (e.key === "Enter" || e.keyCode === 13) {
      handleSearch();
      e.target.blur();
    }
  }

  function handleBlur() {
    if ($env.isMobile) {
      handleSearch();
    }

    setActive(false);
  }

  function handleFocus() {
    setErrMessage("");
    setActive(true);
  }

  function handleModeChange(next: MatchMode) {
    setMatchMode(next);
    saveSearchPreferences({ matchMode: next });
  }

  async function handleTranslate() {
    const text = keyword.trim();

    if (!text) {
      return;
    }

    if (text.length < 2) {
      setErrMessage(t("Toast.keyword_too_short"));

      return;
    }

    setTranslating(true);
    setErrMessage("");

    try {
      const response = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.message || t("Toast.translate_failed"));
      }

      setKeyword(result.data.text);

      if (result.data.alreadyEnglish) {
        Toast.info(t("Toast.translate_already_english"));
      } else {
        Toast.success(t("Toast.translate_success"));
      }
    } catch (error: any) {
      Toast.error(error?.message || t("Toast.translate_failed"));
    } finally {
      setTranslating(false);
    }
  }

  const isHero = variant === "hero";
  const isActress = searchKind === "actress";
  const placeholder = isActress
    ? t("Search.placeholderActress")
    : t("Search.placeholder");

  const kindTabs = (
    <div
      aria-label={t("Search.filterLabel.searchKind")}
      className="inline-flex shrink-0 rounded-lg bg-black/[0.04] p-0.5 dark:bg-white/[0.06]"
      role="radiogroup"
    >
      {(
        [
          ["resource", t("Search.mode.resource")],
          ["actress", t("Search.mode.actress")],
        ] as const
      ).map(([kind, label]) => {
        const selected = searchKind === kind;
        return (
          <button
            key={kind}
            aria-checked={selected}
            className={clsx(
              "rounded-md px-2.5 py-[5px] text-xs font-medium tracking-wide transition-[color,background-color,box-shadow]",
              isHero && "sm:px-3 sm:text-[13px]",
              selected
                ? "bg-white text-foreground shadow-sm dark:bg-slate-700 dark:text-slate-50"
                : "text-default-500 hover:text-foreground dark:text-slate-400 dark:hover:text-slate-100",
            )}
            role="radio"
            type="button"
            onClick={() => handleKindChange(kind)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );

  const clearBtn = (
    <button
      aria-label="Clear"
      className={clsx(
        "flex h-8 w-8 items-center justify-center rounded-full text-default-400 transition-opacity hover:bg-default-200/70 hover:text-default-600 dark:hover:bg-slate-700/80",
        active && keyword ? "opacity-100" : "pointer-events-none opacity-0",
      )}
      tabIndex={-1}
      type="button"
      onMouseDown={(e) => {
        e.preventDefault();
        setKeyword("");
      }}
    >
      <svg
        aria-hidden
        className="h-4 w-4"
        fill="currentColor"
        viewBox="0 0 24 24"
      >
        <path d="M12 2a10 10 0 1010 10A10.016 10.016 0 0012 2zm3.36 12.3a.754.754 0 010 1.06.748.748 0 01-1.06 0l-2.3-2.3-2.3 2.3a.748.748 0 01-1.06 0 .754.754 0 010-1.06l2.3-2.3-2.3-2.3A.75.75 0 019.7 8.64l2.3 2.3 2.3-2.3a.75.75 0 011.06 1.06l-2.3 2.3z" />
      </svg>
    </button>
  );

  if (isHero) {
    return (
      <div className="home-search w-full">
        <div
          className={clsx(
            "home-search__bar flex w-full items-center overflow-hidden rounded-2xl backdrop-blur-md transition-[box-shadow,ring-color] duration-200",
            errMessage && "ring-2 ring-danger",
            active && !errMessage && "ring-2 ring-primary/45",
          )}
        >
          <div className="flex shrink-0 items-center pl-2.5 pr-1 sm:pl-3">
            {kindTabs}
          </div>
          <input
            aria-label="Search"
            className="home-search__input min-w-0 flex-1 bg-transparent py-3 outline-none placeholder:text-default-400"
            placeholder={placeholder}
            type="search"
            enterKeyHint="search"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            value={keyword}
            onBlur={handleBlur}
            onChange={(e) => setKeyword(e.target.value)}
            onFocus={handleFocus}
            onKeyUp={handleKeyup}
          />
          <div className="flex shrink-0 items-center gap-0.5 pr-1">
            {clearBtn}
            {!isActress ? (
              <label className="home-search__mode relative flex h-9 shrink-0 items-center rounded-lg px-1.5 hover:bg-black/[0.03] dark:hover:bg-white/[0.05]">
                <span className="sr-only">{t("Search.filterLabel.matchMode")}</span>
                <select
                  className="home-search__select h-full cursor-pointer appearance-none bg-transparent py-1 pl-1.5 pr-5 text-sm text-foreground outline-none"
                  value={matchMode}
                  onChange={(e) =>
                    handleModeChange(e.target.value as MatchMode)
                  }
                >
                  {SEARCH_PARAMS.matchMode.map((mode) => (
                    <option key={mode} value={mode}>
                      {t(`Search.matchMode.${mode}`)}
                    </option>
                  ))}
                </select>
                <svg
                  aria-hidden
                  className="pointer-events-none absolute right-1.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-default-500"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <path
                    d="M6 9l6 6 6-6"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                  />
                </svg>
              </label>
            ) : null}
          </div>
          <button
            aria-label={t("Search.action")}
            className={clsx(
              "home-search__submit flex h-full shrink-0 items-center justify-center bg-primary text-primary-foreground transition-opacity active:opacity-80 hover:opacity-90",
              { "cursor-progress opacity-80": loading },
            )}
            disabled={loading}
            type="button"
            onClick={() => handleSearch()}
          >
            {loading ? (
              <Spinner color="current" size="sm" />
            ) : (
              <SearchIcon className="text-base sm:text-lg" />
            )}
          </button>
        </div>
        {errMessage ? (
          <p className="mt-1 text-xs text-danger">{errMessage}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="relative w-full">
      <div
        className={clsx(
          "flex h-12 w-full items-center gap-1.5 rounded-2xl border bg-default-100/90 px-2 transition-[box-shadow,border-color,background-color] duration-200 dark:bg-slate-800/70",
          errMessage
            ? "border-danger"
            : active
              ? "border-primary/40 shadow-[0_0_0_3px_rgba(14,165,233,0.12)] dark:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]"
              : "border-default-200/80 dark:border-slate-700/80",
        )}
      >
        <div className="flex shrink-0 items-center pl-0.5">{kindTabs}</div>
        <input
          aria-label="Search"
          autoCapitalize="off"
          autoCorrect="off"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-foreground outline-none placeholder:text-default-400"
          enterKeyHint="search"
          placeholder={placeholder}
          spellCheck={false}
          type="search"
          value={keyword}
          onBlur={handleBlur}
          onChange={(e) => setKeyword(e.target.value)}
          onFocus={handleFocus}
          onKeyUp={handleKeyup}
        />
        <div className="flex shrink-0 items-center gap-0.5 pr-0.5">
          {clearBtn}
          {!isActress ? (
            <Tooltip closeDelay={0} content={t("Search.translate")} delay={300}>
              <Button
                isIconOnly
                className={clsx(
                  "h-8 min-w-8 w-8 border-none text-default-400 hover:bg-default-200/70 dark:hover:bg-slate-700/80",
                  { "cursor-progress": translating },
                )}
                isDisabled={translating || !keyword.trim()}
                radius="full"
                size="sm"
                variant="light"
                onPress={handleTranslate}
              >
                {translating ? (
                  <Spinner size="sm" />
                ) : (
                  <TranslateIcon className="text-lg pointer-events-none flex-shrink-0" />
                )}
              </Button>
            </Tooltip>
          ) : null}
          <Button
            isIconOnly
            className={clsx(
              "h-8 min-w-8 w-8 border-none bg-primary text-primary-foreground hover:opacity-90",
              { "cursor-progress opacity-80": loading },
            )}
            isDisabled={loading}
            radius="full"
            size="sm"
            onPress={() => handleSearch()}
          >
            {loading ? (
              <Spinner color="current" size="sm" />
            ) : (
              <SearchIcon className="text-base pointer-events-none flex-shrink-0" />
            )}
          </Button>
        </div>
      </div>
      {errMessage ? (
        <p className="absolute -bottom-5 left-1 text-xs text-danger">
          {errMessage}
        </p>
      ) : null}
    </div>
  );
};
