"use client";

import { useRouter } from "next/navigation";
import { Button } from "@nextui-org/react";
import { useTranslations } from "next-intl";

import { PrevIcon } from "@/components/icons";

export const DETAIL_RETURN_URL_KEY = "ed2k-detail-return-url";

export function saveDetailReturnUrl() {
  if (typeof window === "undefined") {
    return;
  }

  sessionStorage.setItem(
    DETAIL_RETURN_URL_KEY,
    `${window.location.pathname}${window.location.search}`,
  );
}

export function DetailBackButton() {
  const router = useRouter();
  const t = useTranslations();

  const handleBack = () => {
    const returnUrl = sessionStorage.getItem(DETAIL_RETURN_URL_KEY);
    const currentPath = `${window.location.pathname}${window.location.search}`;

    if (returnUrl && returnUrl !== currentPath) {
      router.push(returnUrl);
      return;
    }

    if (window.history.length > 1) {
      router.back();
      return;
    }

    router.push("/browse");
  };

  return (
    <Button
      className="bg-opacity-80 w-fit"
      color="default"
      radius="full"
      size="sm"
      startContent={<PrevIcon size={14} />}
      variant="flat"
      onPress={handleBack}
    >
      {t("Detail.back")}
    </Button>
  );
}
