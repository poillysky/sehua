"""跳过 / 失败 / 不合格 口径（与判帖状态机对齐）。

失败 failed —— 根本没进帖子识别（网络拦截、软文壳、空提示页等，看不见正文）；
              通常先 retry，耗尽后才 status=failed。
跳过 skipped —— 已见正文，判定不入库。
不合格 —— status=done 已入库，outcome 以「不合格：资源名/链接/预览/容量/待核」开头
              （前四类可确认；待核为兜底存疑。旧文案含「不合格：结构」「待核：」）。

跳过种类：
- {具体盘名}（跳过）     有指针：百度/迅雷/夸克…
- 115sha（跳过）
- 未满 N 天（跳过）
- 帖态/权限类（不存在、禁言、屏蔽、版务、无权、需购买）
- 未解析到目标链（跳过）  ← 兜底（含旧「有链但无主资源」）
- 非资源（跳过）          ← 兜底
"""

from __future__ import annotations

# ---- 落库用规范文案 ----
SKIP_115SHA = "115sha（跳过）"
SKIP_NO_TARGET = "未解析到目标链（跳过）"
SKIP_NON_RESOURCE = "非资源（跳过）"
SKIP_MISSING = "帖子不存在（跳过）"
SKIP_AUTHOR_BANNED = "作者已禁止（跳过）"
SKIP_MOD_BLOCKED = "版主屏蔽（跳过）"
SKIP_META_AD = "版务/广告帖（跳过）"
SKIP_NO_ACCESS = "无阅读权限（跳过）"
SKIP_NO_ACCESS_NO_TITLE = "无阅读权限（无有效标题，跳过）"
SKIP_PURCHASE = "需购买贴（跳过）"
SKIP_LOGIN_NO_TITLE = "需登录（无有效标题，跳过）"

# 旧「网盘（跳过）：盘名」前缀（曾用，归并时识别）
_LEGACY_CLOUD_PREFIX = "网盘（跳过）"

# 具体盘名（长的优先，避免「网盘」误伤）
_CLOUD_LABELS = (
    "PikPak网盘",
    "Google网盘",
    "迅雷云盘",
    "百度网盘",
    "夸克网盘",
    "MEGA网盘",
    "阿里云盘",
    "天翼云盘",
    "123云盘",
    "城通网盘",
    "UC网盘",
    "蓝奏云",
    "微云",
    "OneDrive",
    "Dropbox",
    "MediaFire",
    "Terabox",
)


def cloud_skip_tip(label: str) -> str:
    """具体网盘跳过：按盘名落库（标题/链接同一文案）。"""
    name = (label or "").strip() or "未知网盘"
    return f"{name}（跳过）"


def age_skip_tip(days: int) -> str:
    return f"未满 {int(days)} 天（跳过）"


def _cloud_label_from_reason(reason: str) -> str | None:
    r = (reason or "").strip()
    if not r:
        return None
    # 新/规范：百度网盘（跳过） / 百度网盘标题（无 ed2k/磁力，跳过）
    for lab in _CLOUD_LABELS:
        if r.startswith(lab):
            return lab
    # 曾用：网盘（跳过）：百度网盘
    if r.startswith(_LEGACY_CLOUD_PREFIX):
        rest = r.split("：", 1)[-1].strip() if "：" in r else ""
        if rest in _CLOUD_LABELS:
            return rest
        for lab in _CLOUD_LABELS:
            if lab in rest:
                return lab
    return None


def normalize_skip_reason_kind(reason: str) -> str:
    """把新旧 outcome 归并到种类（下拉/统计用）。网盘按具体盘名。"""
    r = (reason or "").strip()
    if not r:
        return r
    lab = _cloud_label_from_reason(r)
    if lab:
        return cloud_skip_tip(lab)
    if "115sha" in r.lower() or "115 sha" in r.lower():
        return SKIP_115SHA
    if r.startswith("未满") and "天" in r:
        return "未满 N 天（跳过）"
    if "未解析" in r or ("未发现" in r and ("ed2k" in r.lower() or "磁力" in r)):
        return SKIP_NO_TARGET
    if "有链但无主资源" in r or "解析入库失败" in r:
        return SKIP_NO_TARGET
    if r.startswith("非资源") or r.startswith("非ED2K") or r.startswith("非情色") or r.startswith(
        "异常下载"
    ):
        return SKIP_NON_RESOURCE
    # 失败类（未见正文耗尽）——下拉仍单独成类，不并进跳过
    if r.startswith("重试") and ("仍失败" in r or "耗尽" in r):
        return "抓取失败（未见正文）"
    if r == "failed":
        return "抓取失败（未见正文）"
    if "帖子不存在" in r:
        return SKIP_MISSING
    if "作者已禁止" in r:
        return SKIP_AUTHOR_BANNED
    if "版主屏蔽" in r:
        return SKIP_MOD_BLOCKED
    if "版务" in r or "广告帖" in r:
        return SKIP_META_AD
    if "无阅读权限" in r:
        return SKIP_NO_ACCESS
    if "需购买" in r:
        return SKIP_PURCHASE
    if "需论坛登录" in r or "需登录" in r:
        return SKIP_LOGIN_NO_TITLE
    return r
