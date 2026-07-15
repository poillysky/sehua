import { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { resourceByHash } from "@/app/api/graphql/service";
import { base64ToHex } from "@/utils";
import { DetailContent } from "@/components/DetailContent";
import { getDisplayTitle, isResourceHash } from "@/utils/resource";

export const dynamic = "force-dynamic";

const fetchData = cache(async (hash64: string) => {
  const hash = base64ToHex(hash64);

  // 支持 ed2k 32 位 / 磁力 infohash 40 位
  if (!isResourceHash(hash)) {
    console.error("Invalid hash", hash);
    notFound();
  }

  const data = await resourceByHash(null, { hash });

  if (!data) {
    notFound();
  }

  return data;
});

export async function generateMetadata({
  params: { hash64 },
}: {
  params: { hash64: string };
}): Promise<Metadata> {
  const data = await fetchData(hash64);

  return {
    title: getDisplayTitle(data),
  };
}

export default async function Detail({
  params: { hash64 },
}: {
  params: { hash64: string };
}) {
  const data = await fetchData(hash64);

  return <DetailContent data={data} />;
}
