/* eslint-disable jsx-a11y/no-static-element-interactions */
/* eslint-disable jsx-a11y/click-events-have-key-events */
"use client";

import { Input, Button, Spinner, Tooltip } from "@nextui-org/react";
import { useRouter, useSearchParams } from "next/navigation";
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
} from "@/hooks/useSearchPreferences";
import { $env, Toast } from "@/utils";

export const SearchInput = ({
  defaultValue = "",
  isReplace = false,
  variant = "default",
  japanPrefs = false,
}: {
  defaultValue?: string;
  isReplace?: boolean;
  /** 右上角紧凑搜索条：输入 + 类型 + 按钮 */
  variant?: "default" | "hero";
  /** 日本分区：搜索带 jp=1，启用中文/破解偏好 */
  japanPrefs?: boolean;
}) => {
  const [keyword, setKeyword] = useState("");
  const [matchMode, setMatchMode] = useState<MatchMode>(DEFAULT_MATCH_MODE);
  const [loading, setLoading] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [active, setActive] = useState(false);
  const [errMessage, setErrMessage] = useState("");
  const router = useRouter();
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
    setMatchMode(getSearchPreferences().matchMode || DEFAULT_MATCH_MODE);
  }, []);

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

    const currentMode = searchParams.get("matchMode") || "smart";
    const sameKeyword = searchParams.get("keyword") === nextKeyword;
    const sameMode =
      (matchMode === "smart" && currentMode === "smart") ||
      matchMode === currentMode;
    if (sameKeyword && sameMode && !searchParams.get("p")) {
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

    saveSearchPreferences({ matchMode });

    const url = `/search?${params.toString()}`;

    setLoading(true);
    if (isReplace) {
      router.replace(url);
    } else {
      router.push(url);
    }
  }

  function handleKeyup(e: any) {
    if (e.key === "Enter" || e.keyCode === 13) {
      if (!$env.isMobile) {
        handleSearch();
      }
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

  if (isHero) {
    return (
      <div className="home-search w-full">
        <div
          className={clsx(
            "flex h-9 w-full items-stretch overflow-hidden rounded-md bg-background/95 shadow-sm ring-1 ring-default-200/80 backdrop-blur-sm",
            "dark:bg-slate-900/90 dark:ring-slate-600/70",
            "sm:h-10",
            errMessage && "ring-2 ring-danger",
            active && !errMessage && "ring-2 ring-primary/40",
          )}
        >
          <input
            aria-label="Search"
            className="min-w-0 flex-1 bg-transparent px-2.5 text-sm outline-none placeholder:text-default-400 sm:px-3"
            placeholder={t("Search.placeholder")}
            type="text"
            value={keyword}
            onBlur={handleBlur}
            onChange={(e) => setKeyword(e.target.value)}
            onFocus={handleFocus}
            onKeyUp={handleKeyup}
          />
          <label className="relative flex shrink-0 items-center border-l border-default-200/80 dark:border-slate-600/70">
            <span className="sr-only">{t("Search.filterLabel.matchMode")}</span>
            <select
              className="h-full max-w-[5.5rem] cursor-pointer appearance-none bg-default-100/80 py-0 pl-2 pr-6 text-xs text-foreground outline-none dark:bg-slate-800/80 sm:max-w-none sm:pl-2.5 sm:pr-7 sm:text-[13px]"
              value={matchMode}
              onChange={(e) => handleModeChange(e.target.value as MatchMode)}
            >
              {SEARCH_PARAMS.matchMode.map((mode) => (
                <option key={mode} value={mode}>
                  {t(`Search.matchMode.${mode}`)}
                </option>
              ))}
            </select>
            <svg
              aria-hidden
              className="pointer-events-none absolute right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-default-500"
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
          <button
            aria-label={t("Search.action")}
            className={clsx(
              "flex h-full w-9 shrink-0 items-center justify-center bg-primary text-primary-foreground transition-opacity hover:opacity-90 sm:w-10",
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
    <Input
      aria-label="Search"
      classNames={{
        inputWrapper: "h-12 px-4 bg-default-100",
        input: "text-base",
        helperWrapper: "absolute bottom-[-25px]",
      }}
      defaultValue={defaultValue}
      endContent={
        <div className="flex items-center gap-0.5">
          <span
            className={clsx(
              "p-2 -m-2 z-10 invisible appearance-none select-none opacity-0 hover:!opacity-60 cursor-pointer active:!opacity-40 rounded-full outline-none text-large transition-opacity motion-reduce:transition-none",
              { "!visible opacity-40": active && !!keyword },
            )}
            onPointerDown={() => setKeyword("")}
          >
            <svg
              aria-hidden="true"
              focusable="false"
              height="1em"
              role="presentation"
              viewBox="0 0 24 24"
              width="1em"
            >
              <path
                d="M12 2a10 10 0 1010 10A10.016 10.016 0 0012 2zm3.36 12.3a.754.754 0 010 1.06.748.748 0 01-1.06 0l-2.3-2.3-2.3 2.3a.748.748 0 01-1.06 0 .754.754 0 010-1.06l2.3-2.3-2.3-2.3A.75.75 0 019.7 8.64l2.3 2.3 2.3-2.3a.75.75 0 011.06 1.06l-2.3 2.3z"
                fill="currentColor"
              />
            </svg>
          </span>
          <Tooltip closeDelay={0} content={t("Search.translate")} delay={300}>
            <Button
              isIconOnly
              className={clsx("border-none active:bg-default min-w-8 w-8 h-8", {
                "cursor-progress": translating,
              })}
              isDisabled={translating || !keyword.trim()}
              variant="ghost"
              onPress={handleTranslate}
            >
              {translating ? (
                <Spinner size="sm" />
              ) : (
                <TranslateIcon className="text-lg text-default-400 pointer-events-none flex-shrink-0" />
              )}
            </Button>
          </Tooltip>
          <Button
            isIconOnly
            className={clsx("border-none active:bg-default min-w-8 w-8 h-8", {
              "cursor-progress": loading,
            })}
            variant="ghost"
            onPress={() => handleSearch()}
          >
            {loading ? (
              <Spinner size="sm" />
            ) : (
              <SearchIcon className="text-xl text-default-400 pointer-events-none flex-shrink-0" />
            )}
          </Button>
        </div>
      }
      errorMessage={errMessage}
      isInvalid={!!errMessage}
      labelPlacement="outside"
      placeholder={t("Search.placeholder")}
      value={keyword}
      onBlur={handleBlur}
      onFocus={handleFocus}
      onKeyUp={handleKeyup}
      onValueChange={setKeyword}
    />
  );
};
