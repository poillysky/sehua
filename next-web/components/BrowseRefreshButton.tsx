"use client";

import { Button } from "@nextui-org/react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { RefreshIcon } from "@/components/BrowseIcons";

export function BrowseRefreshButton({
  isLoading = false,
  onRefresh,
}: {
  isLoading?: boolean;
  onRefresh?: () => void;
}) {
  const router = useRouter();
  const t = useTranslations();

  return (
    <Button
      className="shrink-0 border border-primary/20 bg-background/80 font-medium text-primary backdrop-blur-sm data-[hover=true]:bg-primary/10 dark:border-primary/30 dark:bg-slate-900/70"
      color="primary"
      isDisabled={isLoading}
      isLoading={isLoading}
      radius="full"
      size="sm"
      startContent={isLoading ? undefined : <RefreshIcon size={15} />}
      variant="flat"
      onPress={() => {
        if (onRefresh) {
          onRefresh();

          return;
        }

        router.refresh();
      }}
    >
      {t("Browse.refresh")}
    </Button>
  );
}
