"""资源形态填槽框架：先定型 → 按槽位填 → 验收。

与 docs/资源入库模型.md 对齐。不合格仍可写入，但 outcome 不得以「成功」开头。

模型（一句话）：
  单资源 = 只有 1 个资源名的「多资源」（同一套切名/挂链；名数=1）。
  多资源 = 资源名数 ≥2。
  核心：名数=1 时别漏链；名数≥2 时别漏资源名。

帖子结构只有两种：
  single  单资源（一名；链数记在 metrics / 链数:N）
  multi   多资源（多名）
  no_link 无可用下载链（F）

硬门前缀见 unqual_outcomes：
  资源名 — 多资源漏名/切错/不可区分
  链接   — 漏链或链未进组
  容量   — 多资源标题 vs 子资源文案合计（漏名旁证）；单资源不硬判
  待核   — 名数=1 时配额≠实链等软存疑

预览图：只入库/展示，不参与合格判定（缺图/共享图多为误报；靠切块与资源名保证）。

名数=1：资源名可=标题；不用 V；不做 ×N/标签切开硬判（标题×N≠漏切）；
正文同名标签≥2 却只认出 1 名 → 多资源漏切成单名，归「资源名」硬门报警。
名数≥2：弱名（过短/占位/=标题）与漏名一并硬判。

填不上时归因：
  cause:parse   识别错误（帖面有线索却没填对）
  cause:missing 真没有（模板允许空 / 帖面无对应数据）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from parsers.links import DualParseResult, ParsedAsset
from parsers.magnet import parse_capacity_bytes

VerdictStatus = Literal["ok", "structure_fail", "content_gap"]
FillCause = Literal["parse", "missing"]

# A/B/C/F 粗类（兼容旧筛选）
SHAPE_LABEL = {
    "A": "单资源",
    "B": "多资源",
    "C": "截断名已合并",
    "F": "无下载链",
}

# 帖子结构只有两种（+无链）
KIND_LABEL = {
    "single": "单资源",
    "multi": "多资源",
    "no_link": "无下载链",
    # 旧细类兼容读库/旧 outcome
    "single_one_link": "单资源",
    "single_multi_link": "单资源",
    "multi_one_link": "多资源",
    "multi_multi_link": "多资源",
}

CAUSE_LABEL = {
    "parse": "识别错误",
    "missing": "真没有",
}

# ×N / xN部；勿把「Sara x Rio x 3P」里的 x 3P（多人玩法）当成资源数
# 勿把「6部合集」当 ×N：那是包内片数/片名用语，常配 1配额单链
# 勿把分辨率「1024X576」「2048X1152」当 ×N（数字与 X 相连）
# 勿把「365天×10次 / 365日×10発」次数用法当 ×N
# 勿把正文资源名「楊x 23 c罩杯」当 ×23（latin x + 空格 + 数字须带个/部等）
# 总资源数只匹配标题，勿扫正文
_X_COUNT_RE = re.compile(
    r"×\s*(\d+)(?!\s*[Pp]\b)(?![Pp])(?!\d)(?!\s*(?:次|发|發|発|回))"
    # 紧贴 x23；「x 23」须带个/部等
    r"|(?<![0-9A-Za-z])[xX](\d+)(?!\s*[Pp]\b)(?![Pp])(?!\d)(?!\s*(?:次|发|發|発|回))"
    r"|(?<![0-9A-Za-z])[xX]\s+(\d+)\s*(?:个|個|部|題|题|片|集)"
    r"|(?:共|合计|總計|总计)\s*(\d+)\s*(?:部|个|個|題|题|片)"
    r"|（\s*(\d+)\s*部\s*）",
    re.I,
)
# DB/占位写入的 4KB 等极小 size，不当作真实入库容量
_PLACEHOLDER_SIZE_MAX = 8 * 1024
_V_COUNT_RE = re.compile(r"(?<![A-Za-z0-9.])(\d+)\s*V(?![A-Za-z])", re.I)
# ed2k 合集常见：70.6G/1169V//7配额 · 20.2g/17V/2配额
_QUOTA_COUNT_RE = re.compile(r"(\d+)\s*配额", re.I)
# 标题写「夸克/百度/迅雷/网盘」时，N配额常含云盘份，不全等于入库 ed2k 链数。
# 注意：纯「115eD2k」是电驴合集标，不是云盘混合，勿当 cloud_soft（否则附件轮询会提前停）。
_CLOUD_SHARE_IN_TITLE_RE = re.compile(
    r"夸克|百度网盘|百度|迅雷|阿里云?盘?|UC云|蓝奏|网盘|115网盘|115分享",
    re.I,
)
# 【115eD2k压缩包】+1链：配额常指包内份数/115 额度，不是多条 ed2k
_PACK_IN_TITLE_RE = re.compile(r"压缩包", re.I)
# 配额旁证：帖内下载向链接（不必可入库）。扩展名后禁吃逗号，防 "a.mp4,http://b" 并一条
_ED2K_QUOTA_RE = re.compile(r"ed2k://[^\s<>\"']+", re.I)
_MAGNET_QUOTA_RE = re.compile(r"magnet:\?[^\s<>\"']+", re.I)
_THUNDER_QUOTA_RE = re.compile(r"(?:thunder|ftp)://[^\s<>\"']+", re.I)
_HTTP_HOST_MEDIA_RE = re.compile(
    r"https?://[^\s<>\"',]+?\.(?:mp4|mkv|avi|wmv|ts|iso|mov|flv|m4v|rmvb|mpg|mpeg|zip|rar|7z)"
    r"(?:\?[^\s<>\"']*)?",
    re.I,
)
# 【影片大小】：MB / 【资源大小】：（空）——有标签无有效数字
_EMPTY_SIZE_LABEL_RE = re.compile(
    r"[【［〖「『\[]\s*[^】］〗」』\]]{0,12}(?:大小|容量|尺寸)\s*[】］〗」』\]]"
    r"\s*[:：︰｜|/／·・•‧＝=\-_;；,，]?\s*"
    r"(?:MB|GB|TB|M|G|T)?\s*(?=\n|$|[【［])",
    re.I,
)


@dataclass(slots=True)
class FrameSpec:
    shape: str  # A|B|C|F
    kind: str  # single | multi | no_link
    capacity: str  # D1|D2|D3|ok
    source: str  # body|attach
    layout: str = ""
    truncated_merged: bool = False


@dataclass(slots=True)
class SlotFill:
    """单个槽位的填充结果。"""

    slot: str  # filename|links|previews|size
    ok: bool
    value_summary: str = ""
    cause: FillCause | None = None
    message: str = ""


@dataclass(slots=True)
class FrameRow:
    """按资源名填好的一行槽位。"""

    filename: str
    size: int
    previews: list[str]
    links: list[str]
    hashes: list[str]
    head: ParsedAsset
    members: list[ParsedAsset]
    slot_errors: list[str] = field(default_factory=list)
    slots: list[SlotFill] = field(default_factory=list)
    # 该资源块文案解析出的容量（【影片大小】等）；0=文案无明确数字（不从链接算）
    label_size: int = 0


@dataclass(slots=True)
class FrameVerdict:
    status: VerdictStatus
    hard_errors: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


@dataclass(slots=True)
class ResourceFrame:
    spec: FrameSpec
    rows: list[FrameRow]
    verdict: FrameVerdict

    @property
    def shape(self) -> str:
        return self.spec.shape

    @property
    def kind(self) -> str:
        return self.spec.kind


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def _pack_capacity_bytes(title: str, desc: str = "", meta_size: str = "") -> int:
    """帖级总容量：标题有明确容量时以标题为准。

    描述【资源大小】常写脏值（tid=2829365：标题 31G，描述却 11G），
    parse_capacity_bytes 会优先吃【资源大小】字段导致误判。
    """
    t = parse_capacity_bytes(title or "")
    if t > 0:
        return t
    return parse_capacity_bytes(_blob(title, desc, meta_size))


def _title_capacity_bytes(title: str) -> int:
    """仅标题文案容量（不含正文）。"""
    got = parse_capacity_bytes(title or "")
    return got if got > _PLACEHOLDER_SIZE_MAX else 0


def _body_capacity_bytes(desc: str = "", meta_size: str = "") -> int:
    """仅正文/元数据文案容量（不含标题；不从链接 xl 计算）。

    优先【资源大小】/metadata，避免多资源帖里先扫到单部【影片大小】。
    """
    if meta_size:
        got = parse_capacity_bytes(meta_size)
        if got > _PLACEHOLDER_SIZE_MAX:
            return got
    raw = desc or ""
    m = re.search(
        r"【\s*资源大小\s*】\s*[:：︰｜|/／·・•‧＝=\-_;；,，]?\s*([^\n【]{1,96})",
        raw,
        re.I,
    )
    if m:
        got = parse_capacity_bytes(m.group(1))
        if got > _PLACEHOLDER_SIZE_MAX:
            return got
    got = parse_capacity_bytes(raw)
    return got if got > _PLACEHOLDER_SIZE_MAX else 0


def _uniq(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0"
    gb = n / (1024**3)
    if gb >= 1:
        return f"{gb:.2f}GB"
    mb = n / (1024**2)
    return f"{mb:.1f}MB"


def _note(
    tags: list[str],
    bucket: list[str],
    code: str,
    zh: str,
    *,
    cause: FillCause,
) -> None:
    """筛选用码 + 中文（带【识别错误】/【真没有】前缀）。"""
    tags.append(code)
    tags.append(f"cause:{cause}")
    prefix = CAUSE_LABEL[cause]
    if not zh.startswith("【"):
        zh = f"【{prefix}】{zh}"
    bucket.append(zh)


def _title_expect_count(title: str, *_ignored: str) -> int | None:
    """只从标题取 ×N / 共N部等期望资源数（正文不参与）。"""
    best: int | None = None
    for m in _X_COUNT_RE.finditer(title or ""):
        for g in m.groups():
            if g and str(g).isdigit():
                n = int(g)
                if 2 <= n <= 20000:
                    best = n if best is None else max(best, n)
                break
    return best


def _has_empty_size_label(text: str | None) -> bool:
    """【影片大小】：MB / 空值 —— 有标签但无有效容量数字。"""
    raw = (text or "").strip()
    if not raw:
        return False
    if parse_capacity_bytes(raw) > 0:
        return False
    return bool(_EMPTY_SIZE_LABEL_RE.search(raw))


def _has_placeholder_only_size_label(text: str | None) -> bool:
    """有大小类标签，但解析结果仅占位级（如 1.01KB）——文案写了却无效，不当事漏名旁证。"""
    raw = (text or "").strip()
    if not raw:
        return False
    if not re.search(
        r"(?:资源大小|影片大小|文件大小|影片容量|(?:资源|影片|文件)?大小|(?:影片)?容量)",
        raw,
    ):
        return False
    got = parse_capacity_bytes(raw)
    return 0 < got <= _PLACEHOLDER_SIZE_MAX


def _effective_size(n: int | None) -> int:
    """真实容量；占位/空记 0。"""
    v = int(n or 0)
    if v <= 0 or v <= _PLACEHOLDER_SIZE_MAX:
        return 0
    return v


def _member_size_sum(members: Sequence[ParsedAsset]) -> int:
    """多链时合计各链 size（ed2k xl）；单链取该值。忽略占位 size。"""
    pos = [
        _effective_size(getattr(a, "size", 0))
        for a in members
        if _effective_size(getattr(a, "size", 0)) > 0
    ]
    if not pos:
        return 0
    return int(sum(pos)) if len(pos) > 1 else int(pos[0])


def _all_magnet_no_xl(rows: Sequence[FrameRow]) -> bool:
    """全部为磁力且链上无有效 size（无 xl）——容量无法从 URI 核验。"""
    any_link = False
    for r in rows:
        for a in r.members:
            any_link = True
            kind = str(getattr(a, "link_kind", "") or "").strip().lower()
            if kind and kind not in {"magnet"}:
                return False
            if int(getattr(a, "size", 0) or 0) > 0:
                return False
            uri = (getattr(a, "uri", None) or "").lower()
            if uri.startswith("ed2k:"):
                return False
    return any_link


def _count_matches(actual: int, expect: int) -> bool:
    """标题/描述数量与链数是否可接受。

    - 链数 ≥ 描述数量 → 合格（多链合集常见：标题写共 N 部，附件多几条）
    - 大合集（≥20）链数略少仍允许约 5% 偏差
    """
    a, e = int(actual or 0), int(expect or 0)
    if a <= 0 or e <= 0:
        return False
    if a >= e:
        return True
    if e >= 20 and (e - a) <= max(2, e // 20):
        return True
    return False


def _quota_link_key(raw: str) -> str:
    s = (raw or "").strip().rstrip(".,;）)」』]")
    if not s:
        return ""
    low = s.lower()
    # magnet 按 btih 去重；其余按去 query 的全文
    if low.startswith("magnet:"):
        m = re.search(r"btih:([a-z0-9]{32,40})", low, re.I)
        return f"magnet:{m.group(1)}" if m else low.split("&", 1)[0]
    if low.startswith("ed2k:"):
        return low.rstrip("/")
    return low.split("?", 1)[0]


def count_http_host_media_links(text: str) -> int:
    """兼容旧名：仅 HTTP 媒体直链条数（按出现次数）。"""
    if not (text or "").strip():
        return 0
    return len(list(_HTTP_HOST_MEDIA_RE.finditer(text)))


def _looks_like_html_link_corpus(text: str) -> bool:
    return bool(re.search(r"<\s*a\b|href\s*=", text or "", re.I))


def _quota_plain_from_html(html: str) -> str:
    """HTML → 额度计数用纯文本：可见正文 + 仅出现在 href 的链。

    额度按**出现次数、不去重**。Discuz 常把同一 URI 写在 href 与锚点文字里，
    若直接对 HTML 正则会 ×2；这里只保留可见文本中的出现，href 仅在正文未写出时补上。
    同链在正文贴两行仍算 2。
    """
    raw = html or ""
    if not raw.strip():
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "lxml")
        visible = soup.get_text("\n", strip=False)
        extras: list[str] = []
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if not (
                href.lower().startswith(("ed2k:", "magnet:", "thunder:", "ftp:"))
                or _HTTP_HOST_MEDIA_RE.search(href)
            ):
                continue
            # 可见区已含该 URI → 不重复加 href（避免 ×2）；未写出才补
            if href not in visible:
                extras.append(href)
        if extras:
            return visible + "\n" + "\n".join(extras)
        return visible
    except Exception:
        return raw


def count_post_quota_links(text: str) -> int:
    """帖内/附件**提供**的下载向链接条数（按出现次数，**不去重**）。

    口径：同 btih/同 ed2k 贴两行算 2（对齐 N配额），不是入库去重链数。
    传入 HTML 时先抽可见文本再数，避免 ``href``+锚点文字把 1 条计成 2。
    调用方仍应尽量用单源（附件文本 / 正文 plain），勿叠 link_html+plain+blockcode。
    """
    if not (text or "").strip():
        return 0
    blob = _quota_plain_from_html(text) if _looks_like_html_link_corpus(text) else text
    if not (blob or "").strip():
        return 0
    n = 0
    for cre in (
        _ED2K_QUOTA_RE,
        _MAGNET_QUOTA_RE,
        _THUNDER_QUOTA_RE,
        _HTTP_HOST_MEDIA_RE,
    ):
        n += sum(1 for _ in cre.finditer(blob))
    return n


def count_unique_importable_quota_links(text: str) -> int:
    """可入库链去重条数（magnet btih / ed2k hash）；仅展示/对照用，不作额度主口径。"""
    if not (text or "").strip():
        return 0
    found: set[str] = set()
    for cre in (
        _ED2K_QUOTA_RE,
        _MAGNET_QUOTA_RE,
        _THUNDER_QUOTA_RE,
        _HTTP_HOST_MEDIA_RE,
    ):
        for m in cre.finditer(text):
            key = _quota_link_key(m.group(0) or "")
            if key:
                found.add(key)
    return len(found)


def _title_v_count(blob: str) -> int | None:
    best = None
    for m in _V_COUNT_RE.finditer(blob or ""):
        n = int(m.group(1))
        if 2 <= n <= 20000:
            best = n if best is None else max(best, n)
    return best


def _title_quota_count(blob: str) -> int | None:
    """标题/描述里的 N配额（ed2k 下载份数口径）。"""
    best = None
    for m in _QUOTA_COUNT_RE.finditer(blob or ""):
        n = int(m.group(1))
        if 1 <= n <= 20000:
            best = n if best is None else max(best, n)
    return best


_ATTACH_V_IN_NAME_RE = re.compile(
    r"(?<![0-9])(\d{1,5})\s*[Vv](?![a-zA-Z])",
)
_ATTACH_V_SKIP_NAME = ("备用", "備份", "封面", "目录", "目錄", "失败", "失敗")


def _attach_filename_v_counts(names: Sequence[str] | None) -> list[int]:
    """各可用附件文件名里的 Nv（如 ``… 96v .txt``）；跳过备用/封面/目录。"""
    out: list[int] = []
    for raw in names or []:
        name = (raw or "").strip()
        if not name:
            continue
        if any(s in name for s in _ATTACH_V_SKIP_NAME):
            continue
        # 每个文件名只取一个 Nv（避免「96v 96V」重复计）
        m = _ATTACH_V_IN_NAME_RE.search(name)
        if not m:
            continue
        n = int(m.group(1))
        if 2 <= n <= 20000:
            out.append(n)
    return out


def _attach_filename_v_sum(names: Sequence[str] | None) -> int | None:
    """全部可用附件文件名 Nv 合计（楼主分卷口径）；无则 None。"""
    vs = _attach_filename_v_counts(names)
    if not vs:
        return None
    return int(sum(vs))


def _quota_echoes_v(blob: str) -> bool:
    """标题「NV/N配额」且 V≈配额 → 配额是片数回声，不是下载链数。

    真链数信号是 V 与配额明显分家，如 ``1169V/7配额``。
    ``22V/22配额`` / ``253V/254配额`` 常见于单包或多分包合集，勿当漏链。
    """
    v = _title_v_count(blob)
    q = _title_quota_count(blob)
    if v is None or q is None:
        return False
    if int(v) == int(q):
        return True
    # 大合集允许 off-by-1（253V/254配额）；小数字 2V/3配额 不算回声
    qn = int(q)
    return qn >= 20 and abs(int(v) - qn) <= max(1, qn // 50)


def _desc_name_label_value_map(desc: str) -> dict[str, list[str]]:
    """正文名称类标签 → 去重取值（剥嵌套重复标签）。

    - ``【影片名称】：【影片名称】：xxx``（tid=2156323）同键同值计 1
    - ``【影片名称】`` + ``【资源名称】`` 分键，单资源模板并存不当事漏切
    """
    from parsers.resource_names import (
        SUBRESOURCE_TITLE_MATCH_FORMS,
        normalize_structure_label_key,
    )

    wanted = {
        normalize_structure_label_key(x) for x in SUBRESOURCE_TITLE_MATCH_FORMS
    }
    label_re = re.compile(
        r"[【［〖「『\[]\s*([^】］〗」』\]]{1,40})\s*[】］〗」』\]]\s*[:：]?\s*"
    )
    out: dict[str, list[str]] = {}
    seen_by_key: dict[str, set[str]] = {}
    for m in label_re.finditer(desc or ""):
        key = normalize_structure_label_key(m.group(1))
        if key not in wanted:
            continue
        raw = re.split(r"[\n\r]", (desc or "")[m.end() :], maxsplit=1)[0].strip()
        while True:
            m2 = label_re.match(raw)
            if not m2:
                break
            if normalize_structure_label_key(m2.group(1)) not in wanted:
                break
            raw = raw[m2.end() :].strip()
        raw = re.split(r"\s*[【［〖「『\[]", raw, maxsplit=1)[0].strip()
        raw = re.sub(r"\s+", " ", raw).strip()
        # 单字中文片名也算有效取值（测试/短名）；空串跳过
        if not raw:
            continue
        bucket = seen_by_key.setdefault(key, set())
        if raw in bucket:
            continue
        bucket.add(raw)
        out.setdefault(key, []).append(raw)
    return out


def _desc_max_same_key_distinct_names(desc: str) -> int:
    """同一名称标签键下不同取值的最大个数（漏切口径）。"""
    mp = _desc_name_label_value_map(desc)
    if not mp:
        return 0
    return max(len(vs) for vs in mp.values())


def _primary_link_kind(parsed: DualParseResult, rows: list[FrameRow]) -> str:
    kind = str(getattr(parsed, "primary_link_kind", "") or "").strip().lower()
    if kind in {"magnet", "ed2k", "115share", "both"}:
        return kind
    for r in rows:
        for a in r.members:
            k = str(getattr(a, "link_kind", "") or "").strip().lower()
            if k in {"magnet", "ed2k", "115share"}:
                return k
    return ""


def _piece_count_expect(
    blob: str, *, link_kind: str = "", title: str = ""
) -> tuple[int | None, str]:
    """取「应有链数」口径：只认 N配额；不用 V（V 极不准）。

    - 标题有配额 → 以标题为准（描述【资源大小】常写脏配额，勿抬高）
    - 标题在但无配额字样 → **不**回落描述脏配额（避免「标题写2配额」误报）
    - 无标题、仅 blob 有 → 用 blob
    - 无配额 → None（不做强制链数判断；magnet/ed2k 相同）

    注：V≈配额（片数回声）不在此处吞掉期望；由 validate_frame 在
    **容量对齐** 时打 ``info:pack_quota_soft``（防 3148293 只入 22/66 却放行）。
    返回 (数量, 来源标签)：来源为「标题」/「正文」/""。
    link_kind 保留兼容调用方，不参与口径选择。
    """
    del link_kind  # 配额口径与主链类型无关
    if title:
        q_title = _title_quota_count(title)
        if q_title is not None:
            return q_title, "标题"
        # 标题明确无「N配额」：勿用描述脏配额抬高期望
        return None, ""
    q = _title_quota_count(blob)
    if q is not None:
        return q, "正文"
    return None, ""


def _rows_capacity_aligned(
    title: str, pack_blob: str, rows: Sequence[FrameRow]
) -> bool:
    """链上 xl 合计是否与标题容量大致对齐（±15%）。

    优先用 member size。多链时禁止用行 size（行 size 常从标题回填，会把
    22/66 半截当齐）。仅 **单链且链上完全无 size**（磁力无 xl）才回退行 size，
    覆盖 tid=3136385；链上有占位 size=1 不算无 size，勿用行 size 假对齐。
    """
    cap = _title_capacity_bytes(title) or _title_capacity_bytes(pack_blob)
    if not cap or cap <= 0:
        return False
    got = sum(_member_size_sum(r.members) for r in rows)
    if got <= 0:
        n_members = sum(len(r.members or []) for r in rows)
        if n_members != 1:
            return False
        raw_sizes = [
            int(getattr(a, "size", 0) or 0)
            for r in rows
            for a in (r.members or [])
        ]
        if any(s > 0 for s in raw_sizes):
            return False
        got = sum(_effective_size(r.size) for r in rows)
    if got <= 0:
        return False
    return abs(int(got) - int(cap)) / float(cap) <= 0.15


def _preview_tuple(imgs: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(x for x in (imgs or []) if x)


def _meta_size_text(parsed: DualParseResult) -> str:
    meta = getattr(parsed, "metadata", None) or {}
    if not isinstance(meta, dict):
        return ""
    for k in ("资源大小", "影片大小", "文件大小", "影片容量"):
        v = str(meta.get(k) or "")
        if v:
            return v
    return ""


def _pack_size_looks_like_row_echo(pack_size: int, row_sizes: Sequence[int]) -> bool:
    """多资源帖：帖级 metadata 常是末块【影片大小】，不能当总容量。

    判定：帖级字节≈某个子资源，且子资源合计明显更大。
    """
    if pack_size <= 0:
        return False
    known = [int(s) for s in row_sizes if int(s or 0) > 0]
    if len(known) < 2:
        return False
    slack = max(int(pack_size * 0.05), 32 * 1024 * 1024)
    if not any(abs(s - pack_size) <= slack for s in known):
        return False
    total = sum(known)
    return total > pack_size + max(int(pack_size * 0.2), 500 * 1024 * 1024)


def _capacity_class(blob: str) -> str:
    if "容量不详" in blob or "容量不明" in blob:
        return "D2"
    if parse_capacity_bytes(blob) > 0:
        return "D1"
    return "D3"


_MAGNET_BTIH_RE = re.compile(r"btih:([A-Za-z0-9]{32,40})", re.I)


def _magnet_hash_from_uri(uri: str) -> str:
    m = _MAGNET_BTIH_RE.search(uri or "")
    return (m.group(1).upper() if m else "")


def _asset_link_key(asset: ParsedAsset) -> str:
    """链身份：优先完整 URI（同 hash 不同文件名视为不同份），否则 hash。"""
    u = (getattr(asset, "uri", None) or "").strip()
    if u:
        return u
    return (getattr(asset, "hash", None) or "").strip().upper()


def _canonical_download_key(
    *, link_kind: str = "", uri: str = "", hash_: str = ""
) -> str:
    """与 _recog_link_keys 同一口径：磁力按 hash，ed2k 按完整 URI。

    避免 asset.uri(magnet:?…) 与 magnets[].infohash 算成两条。
    ed2k URI 空白/&nbsp; 归一，避免同文件双链计成识别2入库1。
    """
    import html as _html

    kind = (link_kind or "").strip().lower()
    u = (uri or "").strip()
    h = (hash_ or "").strip().upper()
    if not kind:
        if u.lower().startswith("magnet:"):
            kind = "magnet"
        elif u.lower().startswith("ed2k:"):
            kind = "ed2k"
    if kind == "magnet":
        return h or _magnet_hash_from_uri(u)
    if u:
        text = _html.unescape(u).replace("\xa0", " ").replace("\u3000", " ")
        return re.sub(r"[ \t]+", " ", text)
    return h


def _unique_link_hashes(
    assets: Sequence[ParsedAsset], *, kinds: set[str] | None = None
) -> set[str]:
    out: set[str] = set()
    for a in assets:
        if kinds and (a.link_kind or "") not in kinds:
            continue
        h = (a.hash or "").strip().upper()
        if h:
            out.add(h)
    return out


def _recog_link_keys(
    parsed: DualParseResult, kinds_in_groups: set[str]
) -> set[str]:
    """识别到的下载链集合（ed2k 按 URI；磁力按 hash）。"""
    kinds = kinds_in_groups or {"magnet", "ed2k"}
    out: set[str] = set()
    for a in list(parsed.assets or []):
        if (a.link_kind or "") not in kinds:
            continue
        k = _canonical_download_key(
            link_kind=a.link_kind or "",
            uri=getattr(a, "uri", None) or "",
            hash_=getattr(a, "hash", None) or "",
        )
        if k:
            out.add(k)
    if "magnet" in kinds:
        for m in getattr(parsed, "magnets", None) or []:
            k = _canonical_download_key(
                link_kind="magnet",
                uri=getattr(m, "link", None) or "",
                hash_=(
                    getattr(m, "infohash", None) or getattr(m, "hash", None) or ""
                ),
            )
            if k:
                out.add(k)
    if "ed2k" in kinds:
        for e in getattr(parsed, "ed2k_links", None) or []:
            k = _canonical_download_key(
                link_kind="ed2k",
                uri=getattr(e, "link", None) or "",
                hash_=getattr(e, "hash", None) or "",
            )
            if k:
                out.add(k)
    return out


def _recog_hashes(
    parsed: DualParseResult, kinds_in_groups: set[str]
) -> set[str]:
    """兼容旧调用：仍返回 hash 集合（诊断用）。"""
    kinds = kinds_in_groups or {"magnet", "ed2k"}
    recog = _unique_link_hashes(list(parsed.assets or []), kinds=kinds)
    if "magnet" in kinds:
        for m in getattr(parsed, "magnets", None) or []:
            h = (
                getattr(m, "infohash", None) or getattr(m, "hash", None) or ""
            ).strip().upper()
            if h:
                recog.add(h)
    if "ed2k" in kinds:
        for e in getattr(parsed, "ed2k_links", None) or []:
            h = (getattr(e, "hash", None) or "").strip().upper()
            if h:
                recog.add(h)
    return recog


def classify_kind(*, n_groups: int, per_group_links: Sequence[int]) -> str:
    """帖子结构：单资源 / 多资源（链数多少不另分形态）。"""
    del per_group_links  # 链数进 metrics / outcome「链数:N」，不进 kind
    if n_groups <= 0:
        return "no_link"
    if n_groups == 1:
        return "single"
    return "multi"


def classify_frame(
    *,
    n_groups: int,
    per_group_links: Sequence[int],
    truncated_merged: bool,
    had_attachments: bool,
    layout: str,
    pack_blob: str,
    any_row_size: bool,
    pack_size: int,
) -> FrameSpec:
    if n_groups == 0:
        shape = "F"
    elif truncated_merged and n_groups == 1:
        shape = "C"
    elif n_groups == 1:
        shape = "A"
    else:
        shape = "B"

    kind = classify_kind(n_groups=n_groups, per_group_links=per_group_links)

    cap_raw = _capacity_class(pack_blob)
    if cap_raw == "D2":
        capacity = "D2"
    elif pack_size > 0 or any_row_size:
        if pack_size > 0 and not any_row_size:
            capacity = "D1"
        else:
            capacity = "ok" if any_row_size else "D3"
    else:
        capacity = "D3"

    return FrameSpec(
        shape=shape,
        kind=kind,
        capacity=capacity,
        source="attach" if had_attachments else "body",
        layout=(layout or "").strip(),
        truncated_merged=bool(truncated_merged),
    )


def fill_rows(
    named_groups: Sequence[tuple[str, ParsedAsset, list[ParsedAsset]]],
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> list[FrameRow]:
    """按资源名逐行填槽：名 / 链 / 图≤PREVIEW_IMAGE_LIMIT / 大小；记录槽位与归因。"""
    title = (post_title or parsed.title or "").strip()
    desc = (parsed.description or "").strip()
    meta_size = _meta_size_text(parsed)
    n_groups = len(named_groups)
    thread_previews = [x for x in (parsed.preview_images or []) if x]
    pack_blob = _blob(title, desc, meta_size)
    cap_class = _capacity_class(pack_blob)
    rows: list[FrameRow] = []

    for name, head0, members in named_groups:
        uris: list[str] = []
        hashes: list[str] = []
        for a in members:
            u = (a.uri or "").strip()
            if u and u not in uris:
                uris.append(u)
            h = (a.hash or "").strip().upper()
            if h and h not in hashes:
                hashes.append(h)
        if not uris and head0.uri:
            uris = [(head0.uri or "").strip()]

        previews: list[str] = []
        for a in members:
            for img in a.preview_images or []:
                if img and img not in previews:
                    previews.append(img)
        if not previews and n_groups <= 1:
            for img in thread_previews:
                if img and img not in previews:
                    previews.append(img)
        raw_preview_n = len(previews)
        from parsers.content import PREVIEW_IMAGE_LIMIT

        previews = previews[:PREVIEW_IMAGE_LIMIT]

        # 容量：有【影片/资源大小】等文案时以文案为准（合集标签 55GB 勿被残缺 magnet xl 盖掉）
        row_desc = ""
        for a in members:
            if a.description:
                row_desc = a.description
                break
        label_size = 0
        for text in (row_desc, name):
            got = parse_capacity_bytes(text or "")
            # 忽略「4K→4KB」类噪声 / 占位级「容量」
            if got > _PLACEHOLDER_SIZE_MAX:
                label_size = got
                break
        if not label_size and n_groups <= 1:
            for text in (desc, title, meta_size, parsed.description or ""):
                got = parse_capacity_bytes(text or "")
                if got > _PLACEHOLDER_SIZE_MAX:
                    label_size = got
                    break
        asset_size = _member_size_sum(members)
        if not asset_size:
            asset_size = _effective_size(head0.size)
        size = label_size or asset_size
        # 无文案时丢掉占位 size，避免 4KB 写成 0.0MB 过槽
        if not label_size:
            size = _effective_size(size)

        slots: list[SlotFill] = []
        slot_errors: list[str] = []

        fname = (name or "").strip()
        if fname:
            slots.append(SlotFill("filename", True, fname[:80]))
        else:
            msg = "资源名为空"
            slots.append(SlotFill("filename", False, "", "parse", msg))
            slot_errors.append(f"【识别错误】{msg}")

        if uris:
            slots.append(SlotFill("links", True, f"{len(uris)}条"))
        else:
            msg = "无下载链"
            cause: FillCause = "parse" if members else "missing"
            slots.append(SlotFill("links", False, "", cause, msg))
            slot_errors.append(f"【{CAUSE_LABEL[cause]}】{msg}")

        # 图片槽：≤PREVIEW_IMAGE_LIMIT；缺图/未分图不进合格硬门（只记 info）
        if previews:
            summary = f"{len(previews)}张"
            if raw_preview_n > PREVIEW_IMAGE_LIMIT:
                slots.append(
                    SlotFill(
                        "previews",
                        True,
                        summary,
                        None,
                        f"预览超过{PREVIEW_IMAGE_LIMIT}张已截断（原{raw_preview_n}张）",
                    )
                )
            else:
                slots.append(SlotFill("previews", True, summary))
        elif thread_previews and n_groups > 1:
            slots.append(
                SlotFill("previews", True, "0", None, "帖有预览未分到该名下（不计不合格）")
            )
        elif thread_previews and n_groups <= 1:
            slots.append(
                SlotFill("previews", True, "0", None, "帖有预览未填到资源上（不计不合格）")
            )
        else:
            slots.append(
                SlotFill("previews", True, "0", "missing", "帖面无预览图")
            )

        # 容量槽：只展示；size=0 一律允许（不再因「有文案却为0」自抓回填 bug）
        row_empty_label = (label_size <= 0) and _has_empty_size_label(row_desc)
        if size > 0:
            slots.append(SlotFill("size", True, _fmt_bytes(size)))
        elif cap_class == "D2":
            slots.append(
                SlotFill("size", True, "0", "missing", "写明容量不详，允许0")
            )
        elif row_empty_label:
            slots.append(
                SlotFill("size", True, "0", "missing", "大小标签无有效数值，允许0")
            )
        else:
            slots.append(
                SlotFill("size", True, "0", "missing", "未用链上容量核验，允许0")
            )

        rows.append(
            FrameRow(
                filename=fname or (head0.hash or ""),
                size=int(size or 0),
                previews=previews,
                links=uris,
                hashes=hashes,
                head=head0,
                members=list(members),
                slot_errors=slot_errors,
                slots=slots,
                label_size=int(label_size or 0),
            )
        )
    return rows


def validate_frame(
    spec: FrameSpec,
    rows: list[FrameRow],
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> FrameVerdict:
    """结构硬门 + 容量缺口；失败区分识别错误 / 真没有。"""
    title = (post_title or parsed.title or "").strip()
    desc = (parsed.description or "").strip()
    meta_size = _meta_size_text(parsed)
    pack_blob = _blob(title, desc, meta_size)
    pack_size = _pack_capacity_bytes(title, desc, meta_size)
    if _pack_size_looks_like_row_echo(pack_size, [_effective_size(r.size) for r in rows]):
        pack_size = 0
    thread_previews = [x for x in (parsed.preview_images or []) if x]

    n_groups = len(rows)
    hard: list[str] = []
    soft: list[str] = []
    tags: list[str] = []

    if spec.shape == "F":
        tags.append("shape:F")
    elif spec.shape == "C":
        tags.extend(["shape:C", "shape:A"])
    elif spec.shape == "A":
        tags.append("shape:A")
    else:
        tags.append("shape:B")
    tags.append(f"kind:{spec.kind}")

    tags.append(f"src:{spec.source}")
    if spec.layout:
        tags.append(f"layout:{spec.layout}")
    elif n_groups <= 1 and sum(len(r.links) for r in rows) > 1:
        tags.append("layout:inferred_pack")
    elif n_groups > 1:
        tags.append("layout:inferred_multi")

    n_links = sum(len(r.links) for r in rows)
    tags.append("links:single" if n_links <= 1 else "links:multi")
    tags.append("res:single" if n_groups <= 1 else "res:multi")

    if spec.capacity == "D2":
        tags.append("cap:D2")
    elif spec.capacity == "D1":
        tags.extend(["cap:D1", "cap:text_present"])
    elif spec.capacity == "ok":
        tags.append("cap:ok")
    else:
        tags.append("cap:D3")

    # 槽位硬错：预览/容量交给后面统一入口，避免同因多条
    for r in rows:
        for e in r.slot_errors:
            if "未分到该资源名下" in e or "帖有预览却未填到资源上" in e:
                continue
            if "容量" in e or "大小为0" in e:
                continue
            hard.append(e)
            if "识别错误" in e:
                tags.append("cause:parse")
            elif "真没有" in e:
                tags.append("cause:missing")

    preview_slot_miss_n = sum(
        1
        for r in rows
        for e in r.slot_errors
        if ("未分到该资源名下" in e or "帖有预览却未填到资源上" in e)
    )
    if preview_slot_miss_n:
        tags.append("info:preview_slot_miss")
        metrics["preview_slot_miss_n"] = preview_slot_miss_n

    kinds: set[str] = set()
    for r in rows:
        for a in r.members:
            if a.link_kind:
                kinds.add(a.link_kind)
    if not kinds:
        kinds = {"magnet", "ed2k"}

    group_keys: set[str] = set()
    for r in rows:
        for a in r.members:
            k = _canonical_download_key(
                link_kind=a.link_kind or "",
                uri=getattr(a, "uri", None) or "",
                hash_=getattr(a, "hash", None) or "",
            )
            if k:
                group_keys.add(k)
        for u in r.links:
            uu = (u or "").strip()
            if not uu:
                continue
            k = _canonical_download_key(uri=uu)
            if k:
                group_keys.add(k)
    recog = _recog_link_keys(parsed, kinds)
    recog_n = len(recog)
    member_sum = sum(len(r.members) for r in rows)
    uri_sum = n_links

    metrics: dict[str, Any] = {
        "n_groups": n_groups,
        "n_assets": member_sum,
        "recog_links": recog_n,
        "persist_link_members": member_sum,
        "persist_link_uris": uri_sum,
        "per_group_links": [len(r.links) for r in rows],
        "pack_size": pack_size,
        "cap_text": spec.capacity,
        "group_sizes": [r.size for r in rows],
        "group_names": [r.filename for r in rows],
        "kind": spec.kind,
        "kind_label": KIND_LABEL.get(spec.kind, spec.kind),
    }

    if recog_n > 0 or member_sum > 0:
        dropped = sorted(recog - group_keys)
        metrics["dropped_hashes"] = dropped[:20]
        metrics["extra_hashes"] = sorted(group_keys - recog)[:20]
        if recog_n != member_sum or recog_n != uri_sum or bool(dropped):
            _note(
                tags,
                hard,
                "warn:link_sum_mismatch",
                f"链数不合规：识别到{recog_n}条下载链，"
                f"入库各子资源合计{uri_sum}条"
                + (f"（有{len(dropped)}条未进组）" if dropped else ""),
                cause="parse",
            )
            tags.append("flag:link_inconsistent")

    expect_n = _title_expect_count(title)
    metrics["title_expect_n"] = expect_n
    shape_ab = "A" if spec.shape in ("A", "C") else spec.shape

    # 正文名称类标签次数（多资源第一判断用；单资源只记 metrics）
    from collections import Counter

    from parsers.resource_names import (
        SUBRESOURCE_TITLE_MATCH_FORMS,
        normalize_structure_label_key,
    )

    wanted_labels = {
        normalize_structure_label_key(x) for x in SUBRESOURCE_TITLE_MATCH_FORMS
    }
    label_hits: Counter[str] = Counter()
    for m in re.finditer(
        r"[【［〖「『\[]\s*([^】］〗」』\]]{1,40})\s*[】］〗」』\]]", desc or ""
    ):
        key = normalize_structure_label_key(m.group(1))
        if key in wanted_labels:
            label_hits[key] += 1
    label_repeat = max(label_hits.values(), default=0)
    distinct_name_n = _desc_max_same_key_distinct_names(desc or "")
    metrics["desc_name_distinct"] = distinct_name_n
    if label_repeat >= 2:
        metrics["desc_name_labels"] = int(sum(label_hits.values()))
        metrics["desc_name_label_max_repeat"] = int(label_repeat)

    if shape_ab == "B" and n_groups >= 2:
        # ---------- 多资源第一判断：别漏资源名 ----------
        name_split_noted = False
        # 1) 标题 ×N 与入库名数：只把「名数 < ×N」当漏名；
        # 名数 > ×N 常见于 ×N 假阳性/包内片数，不是漏识别（tid=23485940）
        if expect_n is not None and n_groups < int(expect_n):
            _note(
                tags,
                hard,
                "warn:title_count_mismatch",
                f"标题写×{expect_n}个资源，实际入库{n_groups}个资源名（漏资源名）",
                cause="parse",
            )
            name_split_noted = True
        elif expect_n is not None and n_groups > int(expect_n):
            tags.append("info:title_count_over_names")
            metrics["title_expect_over_names"] = True
        # 2) 正文不同片名取值 > 入库名数 → 漏名（同值嵌套标签不计）
        if distinct_name_n >= 2 and n_groups < int(distinct_name_n):
            _note(
                tags,
                hard,
                "warn:multi_label_under_split",
                f"正文有{distinct_name_n}个不同资源名称，"
                f"实际只入库{n_groups}个资源名（漏资源名）",
                cause="parse",
            )
            name_split_noted = True
        elif label_repeat >= 2 and distinct_name_n <= 1:
            tags.append("info:multi_label_same_value")
        # 3) 每个资源名下须有链（有名无链也算该名未立住）
        empty_link_n = sum(1 for r in rows if not r.links)
        if empty_link_n > 0:
            _note(
                tags,
                hard,
                "warn:multi_resource_missing_link",
                f"多资源里有{empty_link_n}/{n_groups}个资源名下没有下载链（漏资源名/未立住）",
                cause="parse",
            )
            name_split_noted = True
        # 4) 子名可区分：不重复、≠帖标题；弱名（过短/占位）= 未认出真名
        from parsers.resource_names import (
            is_collection_album_header,
            is_weak_subresource_name,
        )

        names = [r.filename for r in rows]
        if len(set(names)) < len(names):
            _note(
                tags,
                hard,
                "warn:dup_resource_name",
                "多资源存在重复资源名（一名一行违规，漏区分）",
                cause="parse",
            )
            name_split_noted = True
        if title:
            # 子名=帖标题：区分「帖主用该片当标题」vs「回落帖标题漏识别」
            same_title = 0
            for r in rows:
                fn = (r.filename or "").strip()
                if fn != title:
                    continue
                # 合集专辑头 / 无容量文案的占位回落 → 真漏
                if is_collection_album_header(fn) or int(getattr(r, "label_size", 0) or 0) <= 0:
                    same_title += 1
            if same_title > 0:
                _note(
                    tags,
                    hard,
                    "warn:filename_fallback_title",
                    f"多资源有{same_title}/{n_groups}个资源名等于帖标题，"
                    "标题与子名应区分（漏识别真正片名）",
                    cause="parse",
                )
                name_split_noted = True
        weak_n = 0
        for r in rows:
            if not is_weak_subresource_name(
                r.filename,
                post_title=title,
                hash_value=(r.hashes[0] if r.hashes else ""),
            ):
                continue
            fn = (r.filename or "").strip()
            # 帖主用首片当标题：子名=帖标题且块内有容量 → 非「未认出真名」
            if (
                title
                and fn == title
                and int(getattr(r, "label_size", 0) or 0) > 0
                and not is_collection_album_header(fn)
            ):
                continue
            weak_n += 1
        if weak_n > 0:
            _note(
                tags,
                hard,
                "warn:weak_subresource_name",
                f"多资源有{weak_n}/{n_groups}个资源名过短或占位（切块未认出真名）",
                cause="parse",
            )
            name_split_noted = True
        metrics["name_split_noted"] = name_split_noted
        if not name_split_noted:
            tags.append("info:multi_resources_recognized")

        # ---------- 预览：只统计，不进硬/软合格门（靠切块+资源名）----------
        nonempty = [
            _preview_tuple(r.previews) for r in rows if _preview_tuple(r.previews)
        ]
        empty_n = sum(1 for r in rows if not r.previews)
        if nonempty and len({p for p in nonempty}) <= 1:
            tags.append("info:shared_preview")
        if empty_n > 0:
            tags.append("info:preview_empty_rows")
            metrics["preview_empty_n"] = empty_n

        # 每资源文案容量：部分有部分无 / 与文案不一致 → 漏名旁证
        label_sizes = [int(getattr(r, "label_size", 0) or 0) for r in rows]
        has_label_n = sum(1 for s in label_sizes if s > 0)
        metrics["row_label_sizes"] = label_sizes
        if has_label_n > 0:
            mismatch_n = 0
            for r, lab in zip(rows, label_sizes):
                if lab <= 0:
                    continue
                got = _effective_size(r.size)
                slack = max(int(lab * 0.15), 200 * 1024 * 1024)
                if got <= 0 or abs(got - lab) > slack:
                    mismatch_n += 1
            if mismatch_n > 0:
                _note(
                    tags,
                    hard,
                    "warn:row_size_vs_label",
                    f"多资源有{mismatch_n}/{has_label_n}个资源大小与该资源文案不一致（漏资源名旁证）",
                    cause="parse",
                )
            missing_label_n = n_groups - has_label_n
            if missing_label_n > 0 and has_label_n >= 1:
                empty_ok = 0
                for r, lab in zip(rows, label_sizes):
                    if lab > 0:
                        continue
                    row_desc = next(
                        (
                            a.description
                            for a in r.members
                            if getattr(a, "description", None)
                        ),
                        "",
                    ) or ""
                    # 明示空标签 / 仅占位 KB → 不当事「漏切资源名」硬旁证
                    if _has_empty_size_label(row_desc) or _has_placeholder_only_size_label(
                        row_desc
                    ):
                        empty_ok += 1
                        continue
                    # 资源名本身已够强：发帖人没写大小 ≠ 漏切资源名
                    if not is_weak_subresource_name(
                        r.filename,
                        post_title=title,
                        hash_value=(r.hashes[0] if r.hashes else ""),
                    ):
                        empty_ok += 1
                if empty_ok < missing_label_n:
                    _note(
                        tags,
                        hard,
                        "warn:row_label_size_incomplete",
                        f"多资源里有{missing_label_n}/{n_groups}个资源文案未写出大小"
                        f"（漏资源名旁证）",
                        cause="parse",
                    )
                elif missing_label_n > 0:
                    # 子名已立住：仅缺大小文案 → info，不进待核/不合格
                    tags.append("info:row_label_size_omitted")

        # 标题容量 vs 子资源文案合计（闭合，旁证漏名）
        title_cap_multi = _title_capacity_bytes(title)
        if title_cap_multi > 0 and has_label_n == n_groups and n_groups >= 2:
            sub_sum = sum(label_sizes)
            metrics["sub_label_size_sum"] = sub_sum
            slack = max(int(max(title_cap_multi, sub_sum) * 0.15), 200 * 1024 * 1024)
            if abs(sub_sum - title_cap_multi) > slack:
                _note(
                    tags,
                    hard,
                    "warn:title_vs_sub_label_capacity",
                    f"标题容量{_fmt_bytes(title_cap_multi)}，"
                    f"各子资源文案合计{_fmt_bytes(sub_sum)}（不一致，漏资源名旁证）",
                    cause="parse",
                )
            else:
                tags.append("info:title_sub_label_capacity_match")

    elif shape_ab == "A" and n_groups == 1:
        r0 = rows[0]
        member_n = len(r0.members)
        # 预览：单资源不计合格（无图/未回落只记 info）
        if not r0.previews and thread_previews:
            tags.append("info:preview_unfilled_single")
        elif not r0.previews and not thread_previews:
            tags.append("info:preview_missing_ok")

        # 单资源：资源名可以等于帖标题；不做 ×N / 重复名称标签切开硬判
        name_eq_title = bool(title) and (r0.filename or "").strip() == title
        if name_eq_title:
            tags.append("info:pack_name_is_title")
        if distinct_name_n >= 2:
            tags.append("info:multi_label_skip_single")
            # 正文有≥2 个不同片名取值却只认出 1 名 = 多资源漏切成单名
            # 嵌套重复【影片名称】：【影片名称】：同值（tid=2156323）不当事漏切
            _note(
                tags,
                hard,
                "warn:split_collapse_suspect",
                f"正文重复名称标签×{distinct_name_n}，却只认出1个资源名"
                "（多资源漏切成单名）",
                cause="parse",
            )
        elif label_repeat >= 2:
            tags.append("info:multi_label_same_value")

        # 单资源核心：别漏链 —— 有 N配额才对照链数（单链/多链都核；无配额不强制；不用 V）
        link_kind_a = _primary_link_kind(parsed, rows)
        expect_pieces_a, piece_unit_a = _piece_count_expect(
            pack_blob, link_kind=link_kind_a, title=title
        )
        metrics["piece_link_kind"] = link_kind_a
        metrics["title_piece_expect"] = expect_pieces_a
        # 帖内/附件「提供」链数（含重复张贴）；额度主口径，不是入库去重数
        post_n = int(getattr(parsed, "quota_link_count", 0) or 0)
        if post_n <= 0:
            post_n = int(getattr(parsed, "http_media_count", 0) or 0)
        if post_n <= 0:
            post_n = count_post_quota_links(pack_blob)
        post_n = max(post_n, member_n)
        metrics["quota_link_count"] = post_n
        metrics["http_media_count"] = max(
            0, post_n - member_n
        )  # 提供数相对入库去重的差额（展示用）
        # 额度梳理：标题 N配额 ↔ 全部可用附件/正文提供链数；附件文件名 Nv 合计作辅证
        att_names = getattr(parsed, "attachment_names", None) or []
        att_vs = _attach_filename_v_counts(att_names)
        att_v_sum = _attach_filename_v_sum(att_names)
        metrics["attach_filename_v"] = att_vs
        metrics["attach_filename_v_sum"] = att_v_sum
        provided_n = post_n
        attach_sum_match = bool(
            att_v_sum
            and (
                _count_matches(member_n, int(att_v_sum))
                or _count_matches(provided_n, int(att_v_sum))
            )
        )
        title_match = bool(
            expect_pieces_a is not None
            and (
                _count_matches(member_n, expect_pieces_a)
                or _count_matches(provided_n, expect_pieces_a)
            )
        )

        if expect_pieces_a is None and not att_v_sum:
            tags.append("info:no_quota_skip_count")
        elif title_match:
            tags.append("info:piece_count_match")
            metrics["piece_count_match"] = True
            if provided_n > member_n and not _count_matches(member_n, expect_pieces_a):
                tags.append("info:post_links_fill_quota")
        elif attach_sum_match:
            # 全部附件文件名 Nv 合计 = 实链（tid=2178766：96v 对齐 96），标题更高 → 虚标软过
            tags.append("info:piece_count_match")
            tags.append("info:attach_filename_v_match")
            metrics["piece_count_match"] = True
            if expect_pieces_a is not None:
                tags.append("info:title_quota_overclaim_soft")
                tags.append("info:pack_quota_soft")
        elif (
            att_v_sum
            and provided_n < int(att_v_sum)
            and not _count_matches(provided_n, int(att_v_sum))
        ):
            # 附件文件名宣称合计 > 实得链 → 更像漏下分卷，待核
            src_zh = "附件" if spec.source == "attach" else "正文"
            msg = (
                f"附件文件名合计{att_v_sum}份，{src_zh}实得链数仅{provided_n}"
                f"（漏链，待核）"
            )
            if expect_pieces_a is not None:
                msg = (
                    f"标题写{expect_pieces_a}配额·附件名合计{att_v_sum}份，"
                    f"{src_zh}实得链数仅{provided_n}（漏链，待核）"
                )
            _note(
                tags,
                soft,
                "warn:piece_count_mismatch_attach_short",
                msg,
                cause="parse",
            )
            tags.append("info:attach_links_short_of_filename_v")
        elif expect_pieces_a is None:
            tags.append("info:no_quota_skip_count")
        else:
            quota_src = piece_unit_a or "标题"
            src_zh = "附件" if spec.source == "attach" else "正文"
            msg = (
                f"{quota_src}写{expect_pieces_a}配额，{src_zh}提供链数仅{provided_n}"
                f"（漏链，待核）"
            )
            if att_v_sum:
                msg = (
                    f"{quota_src}写{expect_pieces_a}配额·附件名合计{att_v_sum}份，"
                    f"{src_zh}提供链数仅{provided_n}（漏链，待核）"
                )
            code = "warn:piece_count_mismatch_soft"
            if _CLOUD_SHARE_IN_TITLE_RE.search(pack_blob or ""):
                code = "warn:piece_count_mismatch_cloud"
                tags.append("info:cloud_quota_soft")
            elif provided_n < int(expect_pieces_a):
                code = "warn:piece_count_mismatch_title_over"
                tags.append("info:title_quota_overclaim_soft")
                # 压缩包单链：标题 N配额 ≠ 漏链（包内多份/115额度口径）
                if member_n == 1 and _PACK_IN_TITLE_RE.search(pack_blob or ""):
                    tags.append("info:pack_quota_soft")
                else:
                    # 链数对齐标题 V、配额虚高（如 2V/3配额 实 2 链）→ 脏配额，勿待核
                    v_title = _title_v_count(title or "")
                    if (
                        v_title
                        and _count_matches(member_n, int(v_title))
                        and int(expect_pieces_a) > int(v_title)
                    ):
                        tags.append("info:pack_quota_soft")
                        tags.append("info:quota_over_v_soft")
                    # V≈配额 仅当容量也对齐才当片数回声；否则是附件未下全
                    # （tid=3148293：66配额附件有66链，库仅22且 xl≪标题容量）
                    elif _quota_echoes_v(title or pack_blob) and _rows_capacity_aligned(
                        title or "", pack_blob or "", rows
                    ):
                        tags.append("info:pack_quota_soft")
                        tags.append("info:quota_echoes_v")
                    elif member_n == 1 and _rows_capacity_aligned(
                        title or "", pack_blob or "", rows
                    ):
                        tags.append("info:pack_quota_soft")
                        tags.append("info:quota_echoes_v")
            _note(tags, soft, code, msg, cause="parse")

    for r in rows:
        for s in r.slots:
            if s.slot != "previews":
                continue
            if s.ok and s.message and "截断" in s.message:
                # 预览上限是产品口径，截断本身不算识别错误 / 不合格
                tags.append("info:preview_truncated")
            # 缺图/未分图：不计合格，仅 info（见上方 multi/single 预览口径）

    v_count = _title_v_count(pack_blob)
    # 配额展示口径与 piece expect 一致：标题有则用标题；标题无则不记描述脏配额
    quota_count = _title_quota_count(title) if title else None
    if quota_count is None and not title:
        quota_count = _title_quota_count(pack_blob)
    metrics["title_v_count"] = v_count
    metrics["title_quota_count"] = quota_count
    if "piece_link_kind" not in metrics:
        metrics["piece_link_kind"] = _primary_link_kind(parsed, rows)
    if "title_piece_expect" not in metrics:
        metrics["title_piece_expect"] = _piece_count_expect(
            pack_blob,
            link_kind=str(metrics.get("piece_link_kind") or ""),
            title=title,
        )[0]

    # ---- 容量：多资源已在上面用「子资源文案合计 vs 标题」做漏识别闭合；此处不再用链 xl ----
    group_sizes = [_effective_size(r.size) for r in rows]
    any_size = any(s > 0 for s in group_sizes)
    title_cap = _title_capacity_bytes(title)
    body_cap = _body_capacity_bytes(desc, meta_size)
    metrics["title_capacity"] = title_cap or None
    metrics["body_capacity"] = body_cap or None
    content_gap = False
    # 多资源容量闭合已进 hard（漏识别）；不再单独 content_gap 打「不合格：容量」
    if shape_ab != "B" and not any_size:
        _note(
            tags,
            soft,
            "warn:size_missing_ok",
            "全文无容量信息或未核链上容量，大小为0（允许）",
            cause="missing",
        )
    elif shape_ab == "B" and not any_size and not metrics.get("row_label_sizes"):
        _note(
            tags,
            soft,
            "warn:size_missing_ok",
            "多资源文案未写出容量（允许；有标题容量时已在识别门核对）",
            cause="missing",
        )

    # 定型与名数一致性已由 single/multi 表达；链数多少不再单独打「细类不符」
    # （单资源可多名链；多资源可每名多链）

    hard = _uniq(hard)
    soft = _uniq(soft)
    tags = _uniq(tags)

    if hard:
        status: VerdictStatus = "structure_fail"
        tags.append("flag:structure_fail")
        tags.append("flag:needs_rule")
        tags.append("verdict:structure_fail")
    elif content_gap:
        status = "content_gap"
        tags.append("flag:needs_rule")
        tags.append("verdict:content_gap")
    else:
        status = "ok"
        tags.append("verdict:ok")
        if soft:
            tags.append("flag:needs_rule")
            # 软提醒里的识别错误：outcome「不合格：待核」，tags 标 review
            if any(str(w).startswith("【识别错误】") for w in soft):
                tags.append("verdict:review")

    tags = _uniq(tags)
    return FrameVerdict(
        status=status,
        hard_errors=hard,
        soft_warnings=soft,
        tags=tags,
        metrics=metrics,
    )


def build_resource_frame(
    parsed: DualParseResult,
    *,
    named_groups: Sequence[tuple[str, ParsedAsset, list[ParsedAsset]]],
    had_attachments: bool = False,
    truncated_merged: bool = False,
    layout: str = "",
    post_title: str = "",
) -> ResourceFrame:
    """定型 → 填槽 → 验收，一帖一份框架结果。"""
    title = (post_title or parsed.title or "").strip()
    rows = fill_rows(named_groups, parsed, post_title=title)
    desc = parsed.description or ""
    meta_size = _meta_size_text(parsed)
    pack_blob = _blob(title, desc, meta_size)
    pack_size = _pack_capacity_bytes(title, desc, meta_size)
    # 多资源：忽略「末块大小误进帖级 metadata」造成的假总容量
    if _pack_size_looks_like_row_echo(pack_size, [_effective_size(r.size) for r in rows]):
        pack_size = 0
    any_row_size = any(_effective_size(r.size) > 0 for r in rows)
    per_links = [len(r.links) for r in rows]
    spec = classify_frame(
        n_groups=len(rows),
        per_group_links=per_links,
        truncated_merged=truncated_merged,
        had_attachments=had_attachments,
        layout=layout or str(getattr(parsed, "layout", "") or ""),
        pack_blob=pack_blob,
        any_row_size=any_row_size,
        pack_size=pack_size,
    )
    if pack_size > 0 and not any_row_size and spec.capacity != "D2":
        spec = FrameSpec(
            shape=spec.shape,
            kind=spec.kind,
            capacity="D1",
            source=spec.source,
            layout=spec.layout,
            truncated_merged=spec.truncated_merged,
        )
    verdict = validate_frame(spec, rows, parsed, post_title=title)
    return ResourceFrame(spec=spec, rows=rows, verdict=verdict)


def format_frame_outcome(base_tip: str, frame: ResourceFrame) -> str:
    """拼 import_outcome：不合格不得以「成功」开头；种类为资源名/链接/预览/容量。"""
    from parsers.unqual_outcomes import classify_unqual_kind

    v = frame.verdict
    label = KIND_LABEL.get(frame.spec.kind) or SHAPE_LABEL.get(
        frame.spec.shape, frame.spec.shape
    )
    recog = v.metrics.get("recog_links")
    persist = v.metrics.get("persist_link_uris")
    link_part = ""
    if recog is not None and persist is not None:
        if recog != persist:
            link_part = f"链数:{persist}≠识别{recog}"
        elif recog:
            link_part = f"链数:{recog}"

    tip = (base_tip or "").strip()
    if v.status == "structure_fail":
        reasons = v.hard_errors[:2]
        kind = classify_unqual_kind(status=v.status, errors=list(v.hard_errors or []))
        parts = [kind, f"形态:{label}"]
        if link_part:
            parts.append(link_part)
        if reasons:
            parts.append("原因:" + "；".join(reasons))
        elif tip and not tip.startswith("成功") and not tip.startswith("待核"):
            parts.append(tip)
    elif v.status == "content_gap":
        kind = classify_unqual_kind(
            status=v.status,
            errors=list(v.hard_errors or []) or list(v.soft_warnings or []),
        )
        parts = [kind, f"形态:{label}"]
        if link_part:
            parts.append(link_part)
        reasons = (v.hard_errors or [])[:2] or (v.soft_warnings or [])[:2]
        if reasons:
            parts.append("原因:" + "；".join(reasons))
    else:
        # 例外：云盘混合 / 压缩包单链 的配额差 → 成功 + 提醒，勿误杀
        from parsers.unqual_outcomes import UNQUAL_REVIEW

        parse_soft = [
            w for w in (v.soft_warnings or []) if str(w).startswith("【识别错误】")
        ]
        missing_soft = [
            w for w in (v.soft_warnings or []) if str(w).startswith("【真没有】")
        ]
        tags = list(v.tags or [])
        quota_soft_ok = (
            "info:cloud_quota_soft" in tags or "info:pack_quota_soft" in tags
        )
        if quota_soft_ok and parse_soft:
            # 仅配额口径类软提醒：保持成功
            quota_soft = [w for w in parse_soft if "配额" in str(w)]
            other_soft = [w for w in parse_soft if "配额" not in str(w)]
            if not other_soft and quota_soft:
                if tip.startswith("成功") or not tip:
                    head = tip if tip.startswith("成功") else (tip or "成功：已提取主链")
                elif tip.startswith("待核") or tip.startswith("不合格："):
                    head = tip
                else:
                    head = tip if "成功" in tip else f"成功：{tip}"
                parts = [head, f"形态:{label}"]
                if link_part:
                    parts.append(link_part)
                remind = list(quota_soft[:2]) + list(missing_soft[:1])
                if remind:
                    parts.append("提醒:" + "；".join(remind))
                return " · ".join(parts)[:280]
            parse_soft = other_soft
        if parse_soft:
            parts = [UNQUAL_REVIEW, f"形态:{label}"]
            if link_part:
                parts.append(link_part)
            parts.append("原因:" + "；".join(parse_soft[:2]))
        else:
            if tip.startswith("成功") or not tip:
                head = tip if tip.startswith("成功") else (tip or "成功：已提取主链")
            elif tip.startswith("待核") or tip.startswith("不合格："):
                head = tip
            else:
                head = tip if "成功" in tip else f"成功：{tip}"
            parts = [head, f"形态:{label}"]
            if link_part:
                parts.append(link_part)
            if missing_soft:
                parts.append("提醒:" + "；".join(missing_soft[:2]))

    return " · ".join(parts)[:280]


def warnings_from_frame(frame: ResourceFrame) -> list[str]:
    """给人看的中文列表：硬错误在前（已含【识别错误】/【真没有】）。"""
    return _uniq(list(frame.verdict.hard_errors) + list(frame.verdict.soft_warnings))
