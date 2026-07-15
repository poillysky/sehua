import { SVGProps } from "react";

export type IconSvgProps = SVGProps<SVGSVGElement> & {
  size?: number;
};

export type SearchResultsListProps = {
  resources: Ed2kResourceProps[];
  total_count: number;
  has_more: boolean;
};

export type Ed2kResourceProps = {
  hash: string;
  name: string;
  title?: string | null;
  description?: string | null;
  source_url?: string | null;
  board_fid?: string | null;
  board_name?: string | null;
  forum_id?: string | null;
  forum_name?: string | null;
  extract_password?: string | null;
  preview_images?: string[];
  size: number;
  ed2k_link: string;
  ed2k_links?: string[];
  link_kind?: "ed2k" | "magnet" | "other";
  single_file: boolean;
  files_count: number;
  files: {
    index: number;
    path: string;
    size: number;
    extension: string;
  }[];
  created_at: number;
  updated_at: number;
};
