import { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { ZoneFolderPanel } from "@/components/ZoneFolderPanel";
import ZoneFolderSearchResults from "@/components/ZoneFolderSearchResults";
import { findCategory } from "@/config/boards";
import {
  isSearchItem,
  isZoneCustomCategory,
} from "@/lib/zoneFolderModel";
import { findFolder, readZoneFolders } from "@/lib/zoneFolders";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function generateMetadata({
  params,
}: {
  params: { category: string; folderId: string };
}): Promise<Metadata> {
  const index = Number(params.category);
  const cat = findCategory(index);
  const t = await getTranslations();
  if (!cat) return { title: t("Boards.title") };

  if (isZoneCustomCategory(cat.category)) {
    const store = await readZoneFolders();
    const folder = findFolder(store.folders, decodeURIComponent(params.folderId));
    return {
      title: folder
        ? `${folder.name} · ${cat.category}`
        : `${cat.category} · ${t("Boards.title")}`,
    };
  }

  return { title: `${cat.category} · ${t("Boards.title")}` };
}

export default async function ZoneFolderPage({
  params,
  searchParams,
}: {
  params: { category: string; folderId: string };
  searchParams: {
    p?: string;
    ps?: string;
    sortType?: string;
    filterTime?: string;
    filterSize?: string;
    matchMode?: string;
  };
}) {
  const index = Number(params.category);
  const cat = findCategory(index);
  if (!cat) notFound();

  if (!isZoneCustomCategory(cat.category)) {
    notFound();
  }

  const folderId = decodeURIComponent(params.folderId);
  const store = await readZoneFolders();
  const folder = findFolder(store.folders, folderId);
  if (!folder) notFound();

  const page = Math.max(Number(searchParams.p) || 1, 1);

  if (isSearchItem(folder)) {
    return (
      <div className="flex flex-col gap-3">
        <ZoneFolderPanel
          categoryIndex={index}
          folderId={folderId}
          searchMode
        />
        <ZoneFolderSearchResults
          categoryIndex={index}
          filterSize={searchParams.filterSize}
          filterTime={searchParams.filterTime}
          folderId={folderId}
          keyword={folder.searchKeyword}
          matchMode={searchParams.matchMode}
          page={page}
          pageSize={searchParams.ps}
          sortType={searchParams.sortType}
        />
      </div>
    );
  }

  return <ZoneFolderPanel categoryIndex={index} folderId={folderId} />;
}
