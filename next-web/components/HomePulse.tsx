import { getTranslations } from "next-intl/server";
import { cache } from "react";

import { statsInfo } from "@/app/api/graphql/service";

const getStats = cache(async () => statsInfo());

/** 品牌区右下角：收录条数 */
export async function HomePulse() {
  const t = await getTranslations();
  const data = await getStats();
  const count = Number(data?.total_count || 0);
  if (!count) return null;

  return (
    <p className="home-pulse">
      <span className="home-pulse__count tabular-nums">
        {t("Home.pulse_count", { count: count.toLocaleString() })}
      </span>
    </p>
  );
}
