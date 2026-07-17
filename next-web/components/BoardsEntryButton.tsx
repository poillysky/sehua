"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

export function BoardsEntryButton() {
  const router = useRouter();
  const t = useTranslations();
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      className="min-w-[112px] bg-default-100/90 text-default-700 data-[hover=true]:bg-default-200 dark:bg-slate-800/80 dark:text-slate-200 dark:data-[hover=true]:bg-slate-700"
      isDisabled={isPending}
      isLoading={isPending}
      radius="full"
      variant="flat"
      onPress={() => {
        startTransition(() => {
          router.push("/boards");
        });
      }}
    >
      {t("Boards.entry")}
    </Button>
  );
}
