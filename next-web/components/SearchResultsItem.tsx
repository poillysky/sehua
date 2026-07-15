"use client";

import { Ed2kResourceProps } from "@/types";
import { ResourceFeedItem } from "@/components/ResourceFeedItem";

export default function SearchResultsItem({
  item,
  keywords,
}: {
  item: Ed2kResourceProps;
  keywords: string | string[];
}) {
  return <ResourceFeedItem item={item} keywords={keywords} showPreview={false} />;
}
