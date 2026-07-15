"""Parsers package: content fields + dual magnet/ed2k link extraction."""

from parsers.content import ThreadContent, parse_thread_content
from parsers.ed2k import Ed2kLink, parse_ed2k_text, pick_primary_ed2k
from parsers.links import DualParseResult, ParsedAsset, parse_thread_dual
from parsers.magnet import MagnetLink, parse_magnet_text, pick_primary_magnet

__all__ = [
    "ThreadContent",
    "parse_thread_content",
    "Ed2kLink",
    "parse_ed2k_text",
    "pick_primary_ed2k",
    "MagnetLink",
    "parse_magnet_text",
    "pick_primary_magnet",
    "DualParseResult",
    "ParsedAsset",
    "parse_thread_dual",
]
