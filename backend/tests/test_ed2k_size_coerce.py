"""ed2k size 炸档纠正。"""

from __future__ import annotations

from parsers.ed2k import (
    MAX_REASONABLE_FILE_BYTES,
    coerce_file_size,
    size_from_ed2k_uri,
)


def test_size_from_ed2k_uri():
    uri = "ed2k://|file|91t神.zip|6507568601|C347C69BF21DF8C9F22562770B2C39A7|/"
    assert size_from_ed2k_uri(uri) == 6507568601


def test_coerce_rejects_exploded_size_like_1556002():
    uri = "ed2k://|file|91t神.zip|6507568601|C347C69BF21DF8C9F22562770B2C39A7|/"
    exploded = 100055558127616  # ~93184 GB
    assert exploded > MAX_REASONABLE_FILE_BYTES
    assert coerce_file_size(exploded, [uri]) == 6507568601


def test_coerce_keeps_sane_size():
    uri = "ed2k://|file|a.zip|1000|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/"
    assert coerce_file_size(1000, [uri]) == 1000
