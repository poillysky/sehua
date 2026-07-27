"""入库形态标记（委托 resource_frame 填槽验收，保持对外 API）。

标记写入 resource_sources.parse_tags / parse_warnings（TEXT[]）。
- parse_tags：机器筛选码（shape:A、verdict:ok、warn:…）
- parse_warnings：易懂中文提示
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import (
    SHAPE_LABEL,
    ResourceFrame,
    build_resource_frame,
    format_frame_outcome,
    warnings_from_frame,
)

# 兼容旧 import
__all__ = [
    "ShapeReport",
    "SHAPE_LABEL",
    "build_shape_report",
    "format_outcome_with_tags",
    "tags_for_sql_filter",
]


@dataclass(slots=True)
class ShapeReport:
    """一帖识别→入库前的形态报告（由 ResourceFrame 派生）。"""

    shape: str = "A"
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    frame: ResourceFrame | None = None

    @property
    def needs_rule_fix(self) -> bool:
        return bool(self.warnings)

    @property
    def verdict(self) -> str:
        if self.frame is not None:
            return self.frame.verdict.status
        for t in self.tags:
            if t.startswith("verdict:"):
                return t.split(":", 1)[1]
        return "ok"


def build_shape_report(
    parsed: DualParseResult,
    *,
    named_groups: Sequence[tuple[str, ParsedAsset, list[ParsedAsset]]],
    had_attachments: bool = False,
    truncated_merged: bool = False,
    layout: str = "",
    post_title: str = "",
) -> ShapeReport:
    """根据解析结果 + 分组结果生成 tags/warnings（内部走填槽框架）。"""
    frame = build_resource_frame(
        parsed,
        named_groups=named_groups,
        had_attachments=had_attachments,
        truncated_merged=truncated_merged,
        layout=layout,
        post_title=post_title or (parsed.title or ""),
    )
    return ShapeReport(
        shape=frame.spec.shape,
        tags=list(frame.verdict.tags),
        warnings=warnings_from_frame(frame),
        metrics=dict(frame.verdict.metrics),
        frame=frame,
    )


def format_outcome_with_tags(base: str, report: ShapeReport) -> str:
    """入库结果文案；有 frame 时走填槽 outcome（禁止假成功）。"""
    if report.frame is not None:
        return format_frame_outcome(base, report.frame)
    # 无 frame 的退化路径（不应常见）
    tip = (base or "").strip() or "成功：已提取主链"
    label = SHAPE_LABEL.get(report.shape, report.shape)
    parts = [tip, f"形态:{label}"]
    if report.warnings:
        parts.append("提醒:" + "；".join(report.warnings[:3]))
    return " · ".join(parts)[:280]


def tags_for_sql_filter(tag: str) -> str:
    """文档示例：WHERE parse_tags @> ARRAY['shape:A']"""
    return tag
