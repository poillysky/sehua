import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/** 兼容旧 /boards 入口 */
export default function BoardsRedirectPage() {
  redirect("/");
}
