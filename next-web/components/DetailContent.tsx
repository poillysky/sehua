"use client";

import {
  Card,
  CardBody,
  CardHeader,
  Divider,
  Link,
} from "@nextui-org/react";
import { useTranslations } from "next-intl";
import { Suspense, type ReactNode } from "react";

import { Ed2kResourceProps } from "@/types";
import {
  formatDate,
} from "@/utils";
import {
  formatDescriptionLines,
  getDisplayTitle,
  getExtractPassword,
} from "@/utils/resource";
import { useHydration } from "@/hooks/useHydration";
import { ResourcePreviewImages, Ed2kCopyButton } from "@/components/ResourceMeta";
import { P115SaveButton } from "@/components/P115SaveButton";
import { Ed2kResourceDetailList } from "@/components/Ed2kResourceDetailList";
import { DetailBackButton } from "@/components/DetailBackButton";

const cardDividerClass = "bg-gray-200 dark:bg-slate-700";
const cardBandClass = "bg-gray-100 dark:bg-slate-800";
const cardHeaderClass = `flex items-center justify-between gap-2 py-1 text-sm ${cardBandClass}`;
const cardBodyClass = "px-3 py-1 md:px-4";

function DetailInfoRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const labelText = label.replace(/[:：]\s*$/, "");

  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-x-2 py-1 sm:grid-cols-[6rem_1fr]">
      <dt className="shrink-0 text-[11px] font-medium leading-tight text-default-500 md:text-xs">
        {labelText}：
      </dt>
      <dd className="m-0 min-w-0 break-words text-[11px] leading-tight text-foreground md:text-xs">
        {children}
      </dd>
    </div>
  );
}

function trimLabel(text: string) {
  return text.replace(/[:：]\s*$/, "");
}

export const DetailContent = ({ data }: { data: Ed2kResourceProps }) => {
  const t = useTranslations();
  const hydrated = useHydration();
  const displayTitle = getDisplayTitle(data);
  const hasPreview = Boolean(data.preview_images?.length);
  const detailRows = formatDescriptionLines(data.description);
  const extractPassword = getExtractPassword(data);
  const hasPasswordInDesc = detailRows.some((row) => row.label === "解压密码");

  return (
    <>
      <DetailBackButton />

      <h1 className="mt-3 text-xl md:text-2xl break-words font-semibold leading-snug">
        {displayTitle}
      </h1>

      <div className="mt-4 grid grid-cols-1 gap-5">
        <Card className="bg-opacity-80 dark:brightness-95">
          <CardHeader className={cardHeaderClass}>
            {t("Detail.details")}
          </CardHeader>
          <Divider className={cardDividerClass} />
          <CardBody className={cardBodyClass}>
            <dl className="divide-y divide-default-100 dark:divide-slate-700/60">
              {detailRows.map((row) => (
                <DetailInfoRow key={row.label} label={row.label}>
                  {row.value}
                </DetailInfoRow>
              ))}

              {!hasPasswordInDesc && extractPassword && (
                <DetailInfoRow label={trimLabel(t("Home.extract_password"))}>
                  <code className="break-all font-mono text-[11px] md:text-xs">
                    {extractPassword}
                  </code>
                </DetailInfoRow>
              )}

              {data.board_name && (
                <DetailInfoRow label={trimLabel(t("Detail.board"))}>
                  {data.board_name}
                </DetailInfoRow>
              )}

              {data.source_url && (
                <DetailInfoRow label={trimLabel(t("Detail.source"))}>
                  <Link
                    isExternal
                    showAnchorIcon
                    className="text-[11px] md:text-xs break-all"
                    href={data.source_url}
                  >
                    {data.source_url}
                  </Link>
                </DetailInfoRow>
              )}

              <DetailInfoRow label={trimLabel(t("Search.created_at"))}>
                <Suspense key={hydrated ? "load" : "loading"}>
                  {formatDate(
                    data.created_at,
                    t("COMMON.DATE_FORMAT"),
                    !hydrated,
                  )}
                </Suspense>
              </DetailInfoRow>
            </dl>
          </CardBody>
        </Card>

        {hasPreview && (
          <Card className="bg-opacity-80 dark:brightness-95">
            <CardHeader className={cardHeaderClass}>
              {t("Detail.preview")}
            </CardHeader>
            <Divider className={cardDividerClass} />
            <CardBody className={cardBodyClass}>
              <ResourcePreviewImages images={data.preview_images} size="md" />
            </CardBody>
          </Card>
        )}

        <Card className="bg-opacity-80 dark:brightness-95">
          <CardHeader className={cardHeaderClass}>
            <span>{t("Detail.ed2k")}</span>
            <div className="flex shrink-0 items-center gap-1.5">
              <P115SaveButton compact item={data} />
              <Ed2kCopyButton compact item={data} />
            </div>
          </CardHeader>
          <Divider className={cardDividerClass} />
          <CardBody className={cardBodyClass}>
            <Ed2kResourceDetailList item={data} />
          </CardBody>
        </Card>
      </div>
    </>
  );
};
