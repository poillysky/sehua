import { getTranslations } from "next-intl/server";

import { ResourceFeedItem } from "@/components/ResourceFeedItem";
import { Ed2kResourceProps } from "@/types";

export async function HomeResourceFeed({
  resources,
}: {
  resources: Ed2kResourceProps[];
}) {
  const t = await getTranslations();

  if (!resources.length) {
    return (
      <p className="text-sm text-default-500 text-center py-8">
        {t("Home.empty")}
      </p>
    );
  }

  return (
    <div className="w-full flex flex-col gap-4">
      <h2 className="text-sm md:text-base font-medium text-default-600">
        {t("Home.latest")}
      </h2>
      {resources.map((item) => (
        <ResourceFeedItem key={item.hash} item={item} />
      ))}
    </div>
  );
}
