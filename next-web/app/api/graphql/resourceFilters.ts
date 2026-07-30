/** 公开可见：磁力 / 电驴 / 115分享 / 占位 stub */
export const PUBLIC_RESOURCE_FILTER = `
  AND (
    lower(COALESCE(r.ed2k_link, '')) LIKE 'ed2k://%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE 'magnet:%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115cdn.com/s/%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE '%115.com/s/%'
    OR lower(COALESCE(r.ed2k_link, '')) LIKE 'unavailable://%'
  )
`;
