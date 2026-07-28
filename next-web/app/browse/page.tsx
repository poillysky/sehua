import { redirect } from "next/navigation";

import { legacyBrowseRedirectTarget } from "@/config/boards";

export const dynamic = "force-dynamic";

/** 兼容旧 /browse?board_fid=… 链接 */
export default function BrowseRedirectPage({
  searchParams,
}: {
  searchParams: {
    board_fid?: string;
    board?: string;
    board_parent?: string;
    p?: string;
  };
}) {
  const target = legacyBrowseRedirectTarget(searchParams);
  if (!target) {
    redirect("/");
  }
  const page = Number(searchParams.p) || 0;
  if (page > 1) {
    redirect(`${target}?p=${page}`);
  }
  redirect(target);
}
