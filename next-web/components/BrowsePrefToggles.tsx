"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import clsx from "clsx";

import {
  getBrowsePreferences,
  saveBrowsePreferences,
  type BrowsePreferences,
} from "@/hooks/useBrowsePreferences";

function PrefChip({
  active,
  label,
  title,
  onClick,
}: {
  active: boolean;
  label: string;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={title}
      className={clsx(
        "inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium transition-colors sm:h-7 sm:px-2.5 sm:text-[12px]",
        active
          ? "border-primary/35 bg-primary/12 text-primary"
          : "border-default-200/70 bg-white/80 text-default-500 hover:border-primary/30 hover:text-primary dark:border-slate-600 dark:bg-slate-800/70",
      )}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/** 浏览偏好：中文 / 破解（本地 + cookie，搜索排序加权） */
export function BrowsePrefToggles() {
  const t = useTranslations();
  const router = useRouter();
  const [prefs, setPrefs] = useState<BrowsePreferences>({
    preferChinese: false,
    preferCrack: false,
  });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPrefs(getBrowsePreferences());
    setReady(true);
  }, []);

  function toggle(key: keyof BrowsePreferences) {
    const next = saveBrowsePreferences({ [key]: !prefs[key] });
    setPrefs(next);
    router.refresh();
  }

  return (
    <div
      className={clsx(
        "flex shrink-0 items-center gap-1.5",
        !ready && "pointer-events-none opacity-60",
      )}
      role="group"
      aria-label={t("Boards.pref_group")}
    >
      <PrefChip
        active={prefs.preferChinese}
        label={t("Boards.pref_chinese")}
        title={t("Boards.pref_chinese_hint")}
        onClick={() => toggle("preferChinese")}
      />
      <PrefChip
        active={prefs.preferCrack}
        label={t("Boards.pref_crack")}
        title={t("Boards.pref_crack_hint")}
        onClick={() => toggle("preferCrack")}
      />
    </div>
  );
}
