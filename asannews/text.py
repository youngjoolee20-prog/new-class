"""정제 · 관련성 판단 · 주제 분류 · 매체명."""
import html
import re
from urllib.parse import urlparse

from . import config

_TAG = re.compile(r"<[^>]+>")
_PREFIX = re.compile(
    r"^\s*(?:(?:\[[^\]]{1,20}\]|【[^】]{1,20}】|\([^)]{1,25}=[^)]{0,15}\)|<[^>]{1,15}>|\([^)]{1,10}\))\s*)+"
)


def clean(s):
    """<b> 태그와 HTML 엔티티 제거, 공백 정리."""
    if not s:
        return ""
    s = _TAG.sub("", s)
    s = html.unescape(html.unescape(s))
    return re.sub(r"\s+", " ", s).strip()


def strip_prefix(title):
    """제목 앞 말머리([포토], (아산=뉴스1) 등) 제거."""
    t = _PREFIX.sub("", title or "").strip()
    return t or (title or "").strip()


def _remove_excluded(text):
    for w in config.EXCLUDE_WORDS:
        text = text.replace(w, " ")
    return text


def is_relevant(title, desc=""):
    """제외어를 지운 뒤에도 지역명이 남고, 제목에 지역명이 있거나 본문에 지역어가 있으면 관련 기사."""
    t = _remove_excluded(title or "")
    d = _remove_excluded(desc or "")
    if config.REGION_SHORT not in t + " " + d:
        return False
    if config.REGION_SHORT in t:
        return True
    return any(w in d or w in t for w in config.LOCAL_WORDS)


def classify_topic(title, desc=""):
    """주제별 키워드 출현 수(제목 가중치 2배)로 분류."""
    best, best_score = config.OTHER_TOPIC, 0
    for topic, words in config.TOPICS.items():
        score = sum(2 * title.count(w) + (desc or "").count(w) for w in words)
        if score > best_score:
            best, best_score = topic, score
    return best


def domain_of(url):
    host = (urlparse(url or "").hostname or "").lower()
    for p in ("www.", "m.", "news.", "mobile."):
        if host.startswith(p) and host.count(".") >= 2:
            host = host[len(p):]
    return host


def press_from_domain(domain):
    if not domain:
        return "알 수 없음"
    for d, name in config.PRESS_BY_DOMAIN.items():
        if domain == d or domain.endswith("." + d):
            return name
    return domain
