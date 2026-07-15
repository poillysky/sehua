"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

import { prefetchBrowseResources } from "@/components/BrowsePageContent";

export function BrowseEntryButton() {
  const router = useRouter();
  const t = useTranslations();
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      className="min-w-[112px] bg-primary-100/90 text-primary data-[hover=true]:bg-primary-100"
      isDisabled={isPending}
      isLoading={isPending}
      radius="full"
      variant="flat"
      onMouseEnter={prefetchBrowseResources}
      onPress={() => {
        startTransition(() => {
          router.push("/browse");
        });
      }}
    >
      {t("Browse.entry")}
    </Button>
  );
}