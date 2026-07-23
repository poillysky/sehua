"use client";

import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

import { CopyIcon } from "@/components/icons";
import { PreviewImage } from "@/components/PreviewImage";
import { Ed2kResourceProps } from "@/types";
import {
  filterPreviewImages,
  formatDescriptionLines,
  getEd2kCopyText,
  getEd2kLinkCount,
  linkKindOf,
} from "@/utils/resource";
import { setClipboard, Toast } from "@/utils";

export function ResourcePreviewImages({
  images,
  size = "md",
}: {
  images?: string[];
  size?: "sm" | "md";
}) {
  const previewImages = filterPreviewImages(images);

  if (!previewImages.length) {
    return null;
  }

  const heightClass =
    size === "sm"
      ? "min-h-20 max-h-32 w-full"
      : "min-h-20 max-h-48 w-full sm:min-h-28";

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 md:gap-3">
      {previewImages.map((src, index) => (
        <a
          key={`${src}-${index}`}
          className="block shrink-0 overflow-hidden rounded-md border border-default-200 bg-default-100"
          href={src}
          rel="noreferrer noopener"
          target="_blank"
        >
          <PreviewImage
            alt={`preview-${index + 1}`}
            className={`${heightClass} w-full object-cover transition-transform hover:scale-105 dark:brightness-90`}
            src={src}
          />
        </a>
      ))}
    </div>
  );
}

export function ResourceDescription({
  description,
  compact = false,
}: {
  description?: string | null;
  compact?: boolean;
}) {
  const lines = formatDescriptionLines(description);

  if (!lines.length) {
    return null;
  }

  return (
    <div
      className={
        compact
          ? "flex flex-col gap-1.5 text-sm text-default-600 line-clamp-5"
          : "flex flex-col gap-2 text-sm md:text-base text-default-600"
      }
    >
      {lines.map((line) => (
        <div key={line.label} className="flex gap-1.5 break-words">
          <span className="shrink-0 font-medium text-default-500">
            {line.label}：
          </span>
          <span className="flex-1">{line.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Ed2kCopyButton({
  item,
  ed2kLink,
  ed2kLinks,
  size = "sm",
  compact = false,
}: {
  item?: Pick<Ed2kResourceProps, "hash" | "ed2k_link" | "ed2k_links">;
  ed2kLink?: string;
  ed2kLinks?: string[];
  size?: "sm" | "md";
  compact?: boolean;
}) {
  const t = useTranslations();
  const source = item || {
    ed2k_link: ed2kLink || "",
    ed2k_links: ed2kLinks,
  };
  const copyText = getEd2kCopyText(source as Pick<Ed2kResourceProps, "hash" | "ed2k_link" | "ed2k_links">);
  const linkCount = getEd2kLinkCount(source as Pick<Ed2kResourceProps, "hash" | "ed2k_link" | "ed2k_links">);
  const kind = linkKindOf(source.ed2k_link || source.ed2k_links?.[0]);

  if (!copyText) {
    return null;
  }

  const label =
    linkCount > 1
      ? t("Search.ed2k_multi", { count: linkCount })
      : kind === "magnet"
        ? t("Search.magnet")
        : kind === "115share"
          ? t("Search.share115")
          : t("Search.ed2k");

  return (
    <Button
      className={
        compact
          ? "h-6 min-h-6 shrink-0 bg-opacity-80 px-2 text-xs"
          : "shrink-0 bg-opacity-80"
      }
      color="primary"
      radius="sm"
      size={compact ? "sm" : size}
      startContent={<CopyIcon size={compact ? 12 : 16} />}
      variant="flat"
      onPress={() => {
        setClipboard(copyText);
        Toast.success(
          linkCount > 1
            ? t("Toast.copy_success_multi", { count: linkCount })
            : t("Toast.copy_success"),
        );
      }}
    >
      {label}
    </Button>
  );
}
