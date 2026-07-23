"""回填 ed2k_resources.filename：子资源名=【影片名称】/【资源名称】，不用链内名。

规则与 resolve_sub_filename 一致：拒绝 ed2k/dn 技术名 → 描述真名 → 帖子标题。

用法（在 backend 目录）:
  .venv\\Scripts\\python.exe -m scripts.backfill_filenames
  .venv\\Scripts\\python.exe -m scripts.backfill_filenames --dry-run
"""

from __future__ import annotations

import argparse
import sys

from db.resource_db import connect_resource
from parsers.ed2k import build_search_string
from parsers.resource_names import resolve_sub_filename


def backfill(*, dry_run: bool = False, batch: int = 500) -> dict[str, int]:
    conn = connect_resource()
    updated = 0
    scanned = 0
    skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.hash, r.filename, r.ed2k_link, r.search_string,
                       COALESCE(rs.title, '') AS title,
                       COALESCE(rs.description, '') AS description,
                       COALESCE(rs.extract_password, '') AS extract_password
                FROM ed2k_resources r
                LEFT JOIN resource_sources rs ON rs.hash = r.hash
                ORDER BY r.hash
                """
            )
            rows = cur.fetchall()

        changes: list[tuple[str, str, str]] = []  # hash, new_filename, new_search
        for row in rows:
            scanned += 1
            h, filename, ed2k_link, _old_search, title, description, extract_password = row
            h = str(h or "")
            old_name = (filename or "").strip()
            new_name = resolve_sub_filename(
                inner_name=old_name,
                title=str(title or ""),
                hash_value=h,
                link_uri=str(ed2k_link or ""),
                description=str(description or ""),
            )
            if new_name == old_name:
                skipped += 1
                continue
            new_search = build_search_string(
                new_name,
                str(title or ""),
                str(description or ""),
                str(extract_password or ""),
            )
            changes.append((h, new_name, new_search))

        if dry_run:
            print(f"[dry-run] scanned={scanned} would_update={len(changes)} keep={skipped}")
            for h, name, _ in changes[:20]:
                print(f"  {h[:12]}… → {name[:80]}")
            if len(changes) > 20:
                print(f"  … +{len(changes) - 20} more")
            return {"scanned": scanned, "updated": 0, "would_update": len(changes), "kept": skipped}

        with conn.cursor() as cur:
            for i in range(0, len(changes), batch):
                chunk = changes[i : i + batch]
                for h, name, search in chunk:
                    cur.execute(
                        """
                        UPDATE ed2k_resources
                        SET filename = %s,
                            search_string = %s,
                            updated_at = now()
                        WHERE hash = %s
                        """,
                        (name, search, h),
                    )
                    updated += int(cur.rowcount or 0)
        conn.commit()
        print(f"scanned={scanned} updated={updated} kept={skipped}")
        return {"scanned": scanned, "updated": updated, "kept": skipped}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backfill resource filenames")
    p.add_argument("--dry-run", action="store_true", help="只统计不写库")
    p.add_argument("--batch", type=int, default=500)
    args = p.parse_args(argv)
    backfill(dry_run=args.dry_run, batch=args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
