"""2048 同 tid 跨镜像应合成一条处理记录。"""

from db.repository import RESOURCE_GROUP_KEY_SQL, name_row_hash


def test_name_row_hash_stable_across_2048_mirrors():
    a = name_row_hash(
        "https://bbs.a.com/read.php?tid=26719397",
        "油鬼子",
        forum_id="2048",
    )
    b = name_row_hash(
        "https://bbs.b.com/read.php?tid=26719397",
        "油鬼子",
        forum_id="2048",
    )
    assert a == b
    c = name_row_hash(
        "https://www.sehuatang.net/thread-1-1-1.html",
        "油鬼子",
        forum_id="sehuatang",
    )
    assert c != a


def test_resource_group_key_sql_mentions_2048_tid():
    assert "tid:2048:" in RESOURCE_GROUP_KEY_SQL
    assert "regexp_match" in RESOURCE_GROUP_KEY_SQL
