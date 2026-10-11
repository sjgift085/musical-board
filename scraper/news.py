"""뮤지컬·공연 업계 소식 수집: 구글 뉴스 RSS(키 불필요) + 네이버 뉴스 검색 API(키가 있으면).

작품 홍보·캐스팅 기사가 아니라 정책·지원, 포럼·컨퍼런스, 협회·단체, 산업 동향 기사만 남긴다.
"""
import re
import html
import os
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from common import HEADERS, KST, clean, fetch, iso, now_kst

QUERIES = [
    "뮤지컬 정책", "뮤지컬 지원사업", "공연예술 지원 정책", "문체부 공연예술", "K-뮤지컬",
    "예술경영지원센터 뮤지컬", "한국문화예술위원회 공연", "한국뮤지컬협회", "공연 협회",
    "뮤지컬 포럼", "뮤지컬 컨퍼런스", "공연예술 토론회", "공연 세미나", "공연예술 마켓",
    "뮤지컬 산업", "공연 시장 매출", "공연계 제도",
]
# '공연'만으로는 축제·시장 행사 기사까지 걸려서, 공연예술계를 가리키는 말이 있어야 한다
FIELD_RE = re.compile(
    r"뮤지컬|공연예술|공연계|공연 ?업계|공연 ?산업|공연 ?시장|연극|무대예술|예술인|예술위|아르코|ARKO|"
    r"예술경영|문예진흥|기초예술|대학로|공연장|문체부|문화체육관광부"
)
# (분류, 이 말이 들어가면 해당) — 위에서부터 먼저 맞는 것으로 분류
CATEGORIES = [
    ("포럼·행사", r"포럼|컨퍼런스|콘퍼런스|세미나|토론회|심포지엄|간담회|공청회|워크숍|마켓|페어|박람회|쇼케이스|아카데미"),
    ("정책·지원", r"정책|지원사업|지원 사업|문체부|문화체육관광부|예술위|예술위원회|예술경영지원센터|"
                 r"예산|법안|개정|제도|공모|육성|기금|바우처|진흥"),
    ("협회·단체", r"협회|협의회|연합회|노조|조합|단체|학회|위원회"),
    ("산업·시장", r"산업(?!안전)|시장|매출|관객 수|관객수|티켓 판매|점유율|통계|보고서|해외 진출|수출|투자|제작사"),
]
CATEGORY_RES = [(name, re.compile(rx)) for name, rx in CATEGORIES]
MAX_AGE_DAYS = 30
MAX_ITEMS = 80


def _google(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query + f" when:{MAX_AGE_DAYS}d")
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
        text = a["title"] + " " + a["summary"]
        if not FIELD_RE.search(text):
            continue
        category = next((name for name, rx in CATEGORY_RES if rx.search(text)), None)
        if not category:
            continue  # 작품 홍보·캐스팅 기사 등은 뺀다
        a["category"] = category
        seen.add(key)
        result.append(a)
    return result[:MAX_ITEMS], errors
