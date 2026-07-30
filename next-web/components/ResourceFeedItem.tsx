"use client";

import type { KeyboardEvent, MouseEvent, ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Spinner } from "@nextui-org/react";
import clsx from "clsx";
import { useTranslations } from "next-intl";

import { Ed2kResourceProps } from "@/types";
import {
  formatByteSize,
  formatDate,
  hexToBase64,
  parseHighlight,
} from "@/utils";
import {
  filterPreviewImages,
  galleryPreviewImages,
  getDescriptionField,
  getDisplayTitle,
  getExtractPassword,
} from "@/utils/resource";
import { Ed2kCopyButton } from "@/components/ResourceMeta";
import { Ed2kResourceDetailList } from "@/components/Ed2kResourceDetailList";
import { P115SaveButton } from "@/components/P115SaveButton";
import { PreviewImage } from "@/components/PreviewImage";
import { saveDetailReturnUrl } from "@/components/DetailBackButton";
import { setClipboard, Toast } from "@/utils";

type ResourceFeedItemProps = {
  item: Ed2kResourceProps;
  keywords?: string | string[];
  compact?: boolean;
  showPreview?: boolean;
  /** 在卡片内列出该资源名称下全部下载链（search 用） */
  showLinks?: boolean;
};

const cardShellClass =
  "flex w-full flex-col overflow-hidden rounded-xl border border-gray-200/90 bg-white shadow-sm transition-[box-shadow,border-color,transform] duration-200 hover:border-primary/25 hover:shadow-md dark:border-slate-700 dark:bg-slate-900 dark:hover:border-primary/35";
const cardBandClass = "bg-gray-50/95 dark:bg-slate-800/95";
const cardDividerClass = "h-px w-full shrink-0 bg-gray-200/90 dark:bg-slate-700/90";
const cardBodyClass = "bg-white px-3 py-2 md:px-4 dark:bg-slate-900";
const titleClass =
  "w-full text-left text-sm md:text-base font-medium leading-snug text-primary break-words line-clamp-2 [&_.text-red-400]:font-semibold";

function ResourceCardShell({
  children,
  loading = false,
  onPress,
}: {
  children: ReactNode;
  loading?: boolean;
  onPress: () => void;
}) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (loading) {
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onPress();
    }
  };

  const handleClick = () => {
    if (loading) {
      return;
    }

    onPress();
  };

  return (
    <div
      className={clsx(
        cardShellClass,
        "relative cursor-pointer",
        loading && "pointer-events-none",
      )}
      role="button"
      tabIndex={loading ? -1 : 0}
      aria-busy={loading}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {children}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/75 backdrop-blur-[1px] dark:bg-slate-900/75">
          <Spinner color="primary" size="md" />
        </div>
      )}
    </div>
  );
}

function ResourceMetaDate({
  createdAt,
  labeled = true,
}: {
  createdAt: number;
  labeled?: boolean;
}) {
  const t = useTranslations();

  return (
    <span suppressHydrationWarning>
      {labeled ? t("Search.created_at") : null}
      {formatDate(createdAt, t("COMMON.DATE_FORMAT"), false)}
    </span>
  );
}

function ResourceSummaryLines({
  resourceType,
  resourceSize,
  resourceAmount,
  extractPassword,
  passwordLabel,
}: {
  resourceType?: string | null;
  resourceSize?: string | null;
  resourceAmount?: string | null;
  extractPassword?: string | null;
  passwordLabel?: string;
}) {
  const t = useTranslations();

  if (!resourceType && !resourceSize && !resourceAmount && !extractPassword) {
    return null;
  }

  const rows: { label: string; value: ReactNode }[] = [];

  if (resourceType) {
    rows.push({ label: t("Home.resource_type"), value: resourceType });
  }
  if (resourceSize) {
    rows.push({ label: t("Home.resource_size"), value: resourceSize });
  }
  if (resourceAmount) {
    rows.push({ label: t("Home.resource_amount"), value: resourceAmount });
  }
  if (extractPassword) {
    rows.push({
      label: passwordLabel || t("Home.extract_password"),
      value: (
        <code
          className="inline-block max-w-full break-all rounded-md bg-default-100 px-1.5 py-0.5 font-mono text-[11px] leading-4 text-primary md:text-xs dark:bg-slate-800"
          title={t("Toast.copy_password_hint")}
          onClick={(event) => {
            event.stopPropagation();
            setClipboard(extractPassword);
            Toast.success(t("Toast.copy_password_success"));
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              event.stopPropagation();
              setClipboard(extractPassword);
              Toast.success(t("Toast.copy_password_success"));
            }
          }}
          role="button"
          tabIndex={0}
        >
          {extractPassword}
        </code>
      ),
    });
  }

  return (
    <dl className="flex min-h-0 min-w-0 flex-1 flex-col justify-center gap-1.5 text-xs leading-5 text-gray-700 md:gap-2 md:text-sm dark:text-slate-300">
      {rows.map((row) => (
        <div
          key={row.label}
          className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-start gap-x-2 md:grid-cols-[5rem_minmax(0,1fr)] md:gap-x-3"
        >
          <dt className="shrink-0 text-default-400">{row.label}</dt>
          <dd className="min-w-0 break-words text-foreground/90 dark:text-slate-200">
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ResourceFooterMeta({ item }: { item: Ed2kResourceProps }) {
  const t = useTranslations();
  const linkCount = item.files_count;
  const isStub = item.link_kind === "stub";

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600 md:text-sm dark:text-slate-400">
      {isStub ? (
        <span className="rounded bg-default-200/80 px-1.5 py-0.5 text-[11px] text-default-600 dark:bg-slate-700 dark:text-slate-300">
          {t("Search.stub")}
        </span>
      ) : null}
      {item.forum_name ? (
        <span>
          {t("Search.forum")}
          {item.forum_name}
        </span>
      ) : null}
      {item.board_name ? (
        <span>
          {t("Search.board")}
          {item.board_name}
        </span>
      ) : null}
      {!isStub ? (
        <span>
          {t("Search.file_size")}
          {linkCount > 1
            ? t("Search.file_size_multi", {
                count: linkCount,
                size: formatByteSize(item.size),
              })
            : formatByteSize(item.size)}
        </span>
      ) : null}
      <ResourceMetaDate createdAt={item.created_at} />
    </div>
  );
}

function ResourceCardFooter({ item }: { item: Ed2kResourceProps }) {
  const stopCardPress = (event: MouseEvent | KeyboardEvent) => {
    event.stopPropagation();
  };

  return (
    <div
      className={`${cardBandClass} flex w-full items-center justify-between gap-x-4 gap-y-2 px-3 py-2 md:px-4`}
    >
      <ResourceFooterMeta item={item} />
      <div
        className="flex shrink-0 items-center gap-1.5"
        onClick={stopCardPress}
        onKeyDown={stopCardPress}
        role="presentation"
      >
        <P115SaveButton compact item={item} />
        <Ed2kCopyButton compact item={item} />
      </div>
    </div>
  );
}

function ResourceLinksBlock({ item }: { item: Ed2kResourceProps }) {
  const stopCardPress = (event: MouseEvent | KeyboardEvent) => {
    event.stopPropagation();
  };

  return (
    <>
      <div className={cardDividerClass} />
      <div
        className={`${cardBodyClass} max-h-72 overflow-y-auto py-2`}
        onClick={stopCardPress}
        onKeyDown={stopCardPress}
        role="presentation"
      >
        <Ed2kResourceDetailList item={item} />
      </div>
    </>
  );
}

export function ResourceFeedItem({
  item,
  keywords = [],
  compact = true,
  showPreview = true,
  showLinks = false,
}: ResourceFeedItemProps) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const [navigating, setNavigating] = useState(false);
  const [coverDead, setCoverDead] = useState(false);
  const [deadThumbs, setDeadThumbs] = useState<Record<string, boolean>>({});
  const displayTitle = getDisplayTitle(item);
  const detailUrl = `/detail/${hexToBase64(item.hash)}`;
  const previewImages = filterPreviewImages(item.preview_images);
  const galleryImages = galleryPreviewImages(item.preview_images);
  const coverImage = previewImages[0];
  const thumbImages =
    galleryImages.length > 1 ? galleryImages.slice(1) : [];
  const visibleThumbs = thumbImages.filter(
    (src, index) => !deadThumbs[`${src}-${index}`],
  );
  const resourceType = getDescriptionField(item.description, "资源类型");
  const resourceSize = getDescriptionField(item.description, "资源大小");
  const resourceAmount = getDescriptionField(item.description, "资源数量");
  const extractPassword = getExtractPassword(item);
  const dense = !showPreview;
  const linksBlock = showLinks ? <ResourceLinksBlock item={item} /> : null;

  useEffect(() => {
    setNavigating(false);
  }, [pathname]);

  const openDetail = () => {
    if (navigating) {
      return;
    }

    saveDetailReturnUrl();
    setNavigating(true);
    router.push(detailUrl);
  };

  const cardShell = (content: ReactNode) => (
    <ResourceCardShell loading={navigating} onPress={openDetail}>
      {content}
    </ResourceCardShell>
  );

  if (dense) {
    const hasSummary = Boolean(
      resourceType || resourceSize || resourceAmount || extractPassword,
    );

    return cardShell(
      <>
        <div
          className={`${cardBandClass} flex w-full items-start gap-2 px-3 py-2 text-left md:px-4`}
        >
          <h2
            dangerouslySetInnerHTML={{
              __html: parseHighlight(displayTitle, keywords),
            }}
            className={titleClass}
          />
        </div>
        {hasSummary && (
          <>
            <div className={cardDividerClass} />
            <div className={cardBodyClass}>
              <ResourceSummaryLines
                extractPassword={extractPassword}
                passwordLabel={
                  item.link_kind === "115share"
                    ? t("Home.share_code")
                    : undefined
                }
                resourceAmount={resourceAmount}
                resourceSize={resourceSize}
                resourceType={resourceType}
              />
            </div>
          </>
        )}
        {linksBlock}
        <div className={cardDividerClass} />
        <ResourceCardFooter item={item} />
      </>,
    );
  }

  return cardShell(
    <>
      <div className={`${cardBandClass} flex w-full items-start gap-2 px-3 py-2 text-left md:px-4`}>
        <h2
          dangerouslySetInnerHTML={{
            __html: parseHighlight(displayTitle, keywords),
          }}
          className={titleClass}
        />
      </div>
      <div className={cardDividerClass} />
      <div className={`${cardBodyClass} py-3`}>
        <div className="flex items-stretch gap-3 md:gap-4">
          {coverImage && !coverDead ? (
            <div className="shrink-0 self-center">
              <PreviewImage
                alt={displayTitle}
                className="h-24 w-24 rounded-lg border border-default-200 bg-default-100 object-cover md:h-28 md:w-28"
                preferProxy
                srcs={previewImages}
                onAllFailed={() => setCoverDead(true)}
              />
            </div>
          ) : (
            <div className="h-24 w-24 shrink-0 self-center rounded-lg border border-dashed border-default-300 bg-default-100 md:h-28 md:w-28" />
          )}

          <ResourceSummaryLines
            extractPassword={extractPassword}
            passwordLabel={
              item.link_kind === "115share" ? t("Home.share_code") : undefined
            }
            resourceAmount={resourceAmount}
            resourceSize={resourceSize}
            resourceType={resourceType}
          />
        </div>

        {!compact && visibleThumbs.length > 0 && (
          <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-5 md:grid-cols-6">
            {thumbImages.map((src, index) => {
              const key = `${src}-${index}`;
              if (deadThumbs[key]) return null;
              return (
                <PreviewImage
                  key={key}
                  alt={`preview-${index + 2}`}
                  className="aspect-square w-full rounded-md border border-default-200 bg-default-100 object-cover"
                  preferProxy
                  src={src}
                  onAllFailed={() =>
                    setDeadThumbs((prev) => ({ ...prev, [key]: true }))
                  }
                />
              );
            })}
          </div>
        )}
      </div>
      {linksBlock}
      <div className={cardDividerClass} />
      <ResourceCardFooter item={item} />
    </>,
  );
}
