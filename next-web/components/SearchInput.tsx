/* eslint-disable jsx-a11y/no-static-element-interactions */
/* eslint-disable jsx-a11y/click-events-have-key-events */
"use client";

import { Input, Button, Spinner, Tooltip } from "@nextui-org/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import { SearchIcon, TranslateIcon } from "@/components/icons";
import { $env, Toast } from "@/utils";
import { getSearchPreferences } from "@/hooks/useSearchPreferences";

export const SearchInput = ({
  defaultValue = "",
  isReplace = false,
}: {
  defaultValue?: string;
  isReplace?: boolean;
}) => {
  const [keyword, setKeyword] = useState("");
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
    // Set default value for keyword when provided
    if (defaultValue) {
      setKeyword(defaultValue);
    }
  }, [defaultValue]);

  function handleSearch() {
    // Trim the keyword and set it to state
    setKeyword(keyword.trim());

    // If keyword is empty, do nothing
    if (!keyword) {
      return;
    }

    // If search params equals current search params, do nothing
    if (searchParams.get("keyword") === keyword && !searchParams.get("p")) {
      return;
    }

    if (keyword.length < 2) {
      // If keyword length is less than 2, display warning toast
      // Toast.warn(t("Toast.keyword_too_short"));
      setErrMessage(t("Toast.keyword_too_short"));

      return;
    }

    if (keyword.length > 100) {
      // limit keyword length to 100 characters
      setKeyword(keyword.slice(0, 100));
    }

    const params = new URLSearchParams();
    const preferences = getSearchPreferences();

    params.set("keyword", keyword.trim());

    if (preferences.sortType) {
      params.set("sortType", preferences.sortType);
    }

    if (preferences.matchMode && preferences.matchMode !== "smart") {
      params.set("matchMode", preferences.matchMode);
    }

    const url = `/search?${params.toString()}`;

    setLoading(true); // Set loading state to true
    if (isReplace) {
      router.replace(url);
    } else {
      router.push(url);
    }
  }

  function handleKeyup(e: any) {
    // Handle Enter key press for triggering search
    if (e.key === "Enter" || e.keyCode === 13) {
      // If on desktop, trigger search
      if (!$env.isMobile) {
        handleSearch();
      }

      // Blur input, on mobile that will trigger search
      e.target.blur();
    }
  }

  function handleBlur() {
    if ($env.isMobile) {
      // If on mobile, trigger search
      handleSearch();
    }

    setActive(false);
  }

  function handleFocus() {
    setErrMessage("");
    setActive(true);
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
            onPress={handleSearch}
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
