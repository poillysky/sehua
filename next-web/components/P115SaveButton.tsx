"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

import { Ed2kResourceProps } from "@/types";
import {
  getDisplayTitle,
  getExtractPassword,
  hasArchiveEd2k,
  isArchiveDownloadLink,
  linkKindOf,
  normalizeEd2kLinks,
} from "@/utils/resource";
import { Toast } from "@/utils";

export function P115SaveButton({
  item,
  ed2kLink,
  ed2kLinks,
  size = "sm",
  compact = false,
}: {
  item?: Pick<
    Ed2kResourceProps,
    | "ed2k_link"
    | "ed2k_links"
    | "extract_password"
    | "description"
    | "name"
    | "title"
    | "link_kind"
  >;
  ed2kLink?: string;
  ed2kLinks?: string[];
  size?: "sm" | "md";
  compact?: boolean;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const source = item || {
    ed2k_link: ed2kLink || "",
    ed2k_links: ed2kLinks,
  };
  const urls = normalizeEd2kLinks(source.ed2k_links, source.ed2k_link);
  const password = item ? getExtractPassword(item) : null;
  const titleHint = item ? getDisplayTitle(item) : "";
  const shareUrls = urls.filter((u) => linkKindOf(u) === "115share");
  const offlineUrls = urls.filter((u) => linkKindOf(u) !== "115share");
  const isShareOnly =
    shareUrls.length > 0 && offlineUrls.length === 0;
  const isArchive = item
    ? hasArchiveEd2k(item)
    : offlineUrls.some((u) => isArchiveDownloadLink(u));
  const wantExtract =
    !isShareOnly && (Boolean(password) || isArchive);

  if (!urls.length) {
    return null;
  }

  const onSave = async () => {
    setLoading(true);

    try {
      // 纯 115 分享：走分享接收；混合时先转存分享再离线
      if (shareUrls.length) {
        const res = await fetch("/api/115/share", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            urls: shareUrls,
            password: password || undefined,
          }),
        });
        const json = await res.json();

        if (!res.ok) {
          const msg = String(json.message || t("Toast.p115_failed"));

          if (/尚未配置|Cookie/i.test(msg)) {
            Toast.error(t("Toast.p115_need_config"));
            router.push("/settings");

            return;
          }

          throw new Error(msg);
        }

        if (!offlineUrls.length) {
          Toast.success(
            json.message ||
              t("Toast.p115_share_success", { count: shareUrls.length }),
          );

          return;
        }
      }

      if (!offlineUrls.length) {
        return;
      }

      const res = await fetch("/api/115/offline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          urls: offlineUrls,
          password: password || undefined,
          titleHint: titleHint || undefined,
          autoExtract: wantExtract,
        }),
      });
      const json = await res.json();

      if (!res.ok) {
        const msg = String(json.message || t("Toast.p115_failed"));

        if (/尚未配置|Cookie/i.test(msg)) {
          Toast.error(t("Toast.p115_need_config"));
          router.push("/settings");

          return;
        }

        throw new Error(msg);
      }

      if (json.data?.extractScheduled) {
        Toast.success(
          t("Toast.p115_success_extract", {
            count: offlineUrls.length,
          }),
        );
      } else {
        Toast.success(
          json.message || t("Toast.p115_success", { count: offlineUrls.length }),
        );
      }
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : t("Toast.p115_failed"));
    } finally {
      setLoading(false);
    }
  };

  const buttonTitle = isShareOnly
    ? "转存 115 分享到网盘"
    : wantExtract
      ? password
        ? "转存后轮询，完成后立即云解压到同名文件夹（保留压缩包，不删除转存目录）"
        : "检测到压缩包，转存完成后自动云解压到同名文件夹（保留压缩包）"
      : "转存到 115 云下载";

  const buttonLabel = isShareOnly
    ? t("Search.p115_share_save")
    : wantExtract
      ? t("Search.p115_save_extract")
      : t("Search.p115_save");

  return (
    <Button
      className={
        compact
          ? "h-6 min-h-6 shrink-0 bg-opacity-80 px-2 text-xs"
          : "shrink-0 bg-opacity-80"
      }
      color="secondary"
      isLoading={loading}
      radius="sm"
      size={compact ? "sm" : size}
      title={buttonTitle}
      variant="flat"
      onPress={() => void onSave()}
    >
      {buttonLabel}
    </Button>
  );
}
