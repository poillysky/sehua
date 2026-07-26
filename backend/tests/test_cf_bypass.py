"""Cloudflare detection helpers."""

from crawler.cf_bypass import (
    cf_browser_wait_ms,
    extract_title,
    is_cf_challenge,
    is_interactive_cf,
)
from crawler.fetcher import Fetcher


def test_detect_just_a_moment():
    html = "<html><title>Just a moment...</title><body>challenge-platform</body></html>"
    assert is_cf_challenge(html) is True
    assert Fetcher._is_cf_challenge(html) is True


def test_detect_turnstile_markers():
    html = "<html><body>cf-turnstile checking your browser</body></html>"
    assert is_cf_challenge(html) is True


def test_interactive_chinese_cf():
    html = (
        "<html><title>请稍候…</title><body>"
        "正在进行安全验证 challenges.cloudflare.com</body></html>"
    )
    assert is_cf_challenge(html) is True
    assert is_interactive_cf(html) is True
    assert cf_browser_wait_ms(html) <= 12000


def test_normal_forum_not_cf():
    html = (
        "<html><title>主题 - 色花堂</title><body>"
        + ("x" * 9000)
        + "Powered by Discuz! challenge-platform leftover</body></html>"
    )
    assert is_cf_challenge(html) is False
    assert Fetcher._is_cf_challenge(html) is False
    assert is_interactive_cf(html) is False


def test_long_forum_page_with_cf_script_noise_not_cf():
    html = (
        "<html><title>国产自拍 - 色花堂</title><body>"
        + ("discuz " * 5000)
        + "Powered by Discuz!</body></html>"
    )
    assert is_cf_challenge(html) is False


def test_extract_title():
    assert extract_title("<title> Hello </title>") == "Hello"
