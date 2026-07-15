"use client";

import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

import { CopyIcon } from "@/components/icons";
import { Ed2kResourceProps } from "@/types";
import { setClipboard, Toast } from "@/utils";
import { normalizeEd2kLinks } from "@/utils/resource";

export function Ed2kResourceDetailList({
  item,
}: {
  item: Ed2kResourceProps;
}) {
  const t = useTranslations();
  const links = normalizeEd2kLinks(item.ed2k_links, item.ed2k_link);

  if (!links.length) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1">
      {links.map((link, index) => (
        <div
          key={`${link}-${index}`}
          className="flex items-start gap-1.5 py-0.5"
        >
          <span className="w-6 shrink-0 text-right font-sans tabular-nums text-[11px] leading-tight text-default-400 md:text-xs">
            {index + 1}.
          </span>
          <span className="min-w-0 flex-1 break-all font-mono text-[11px] leading-tight text-foreground md:text-xs">
            {link}
          </span>
          <Button
            isIconOnly
            className="h-6 w-6 min-w-6 shrink-0 bg-opacity-80"
            color="primary"
            radius="sm"
            size="sm"
            variant="flat"
            onPress={() => {
              setClipboard(link);
              Toast.success(t("Toast.copy_success"));
            }}
          >
            <CopyIcon size={12} />
          </Button>
        </div>
      ))}
    </div>
  );
}
