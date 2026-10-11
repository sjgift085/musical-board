"""뮤지컬 업계 기사 수집: 구글 뉴스 RSS(키 불필요) + 네이버 뉴스 검색 API(키가 있으면)."""
import html
import os
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from common import HEADERS, KST, clean, fetch, iso, now_kst

QUERIES = ["뮤지컬", "창작뮤지컬", "뮤지컬 개막", "뮤지컬 초연", "뮤지컬 공모"]
MAX_AGE_DAYS = 14
MAX_ITEMS = 80


def _google(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query + " when:7d")
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    res = fetch(url, debug_name=None)
    soup = BeautifulSoup(res.content, "xml")
    out = []
    for it in soup.find_all("item"):
        title = clean(it.title.get_text()) if it.title else ""
        press = clean(it.source.get_text()) if it.source else ""
        # 구글 뉴스 제목은 '기사 제목 - 언론사' 형태
        if press and title.endswith(" - " + press):
            title = title[: -len(press) - 3]
        try:
            published = parsedate_to_datetime(it.pubDate.get_text()).astimezone(KST)
        except (TypeError, ValueError, AttributeError):
            continue
        out.append({
            "title": title,
            "url": it.link.get_text().strip() if it.link else "",
            "press": press,
            "published": iso(published),
            "summary": "",
            "via": "Google 뉴스",
        })
    return out


def _naver(query, client_id, client_secret):
    res = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        params={"query": query, "display": 50, "sort": "date"},
        headers={**HEADERS, "X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
        timeout=20,
    )
    res.raise_for_status()
    out = []
    for it in res.json().get("items", []):
        strip = lambda s: clean(BeautifulSoup(html.unescape(s or ""), "lxml").get_text())
        try:
            published = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        except (TypeError, ValueError, KeyError):
            continue
        out.append({
            "title": strip(it.get("title")),
            "url": it.get("originallink") or it.get("link"),
            "press": "",
            "published": iso(published),
            "summary": strip(it.get("description"))[:200],
            "via": "네이버 뉴스",
        })
    return out


def _norm(title):
    return "".join(ch for ch in title if ch.isalnum())[:40]


def collect():
    """기사 목록과 출처별 상태를 돌려준다."""
    articles, errors = [], []
    nid, nsecret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    for q in QUERIES:
        try:
            articles += _google(q)
        except Exception as e:  # noqa: BLE001 - 한 검색어 실패가 전체를 막지 않게
            errors.append(f"Google '{q}': {e}")
        if nid and nsecret:
            try:
                articles += _naver(q, nid, nsecret)
            except Exception as e:  # noqa: BLE001
                errors.append(f"Naver '{q}': {e}")

    cutoff = iso(now_kst() - timedelta(days=MAX_AGE_DAYS))
    seen, result = set(), []
    for a in sorted(articles, key=lambda a: a["published"], reverse=True):
        key = _norm(a["title"])
        if not key or key in seen or a["published"] < cutoff:
            continue
        # 검색어가 넓어서 '뮤지컬'이 아예 없는 기사는 뺀다
        if "뮤지컬" not in a["title"] + a["summary"]:
            continue
        seen.add(key)
        result.append(a)
    return result[:MAX_ITEMS], errors
