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
    # 업계 소식
    "뮤지컬 정책", "뮤지컬 지원사업", "공연예술 지원 정책", "문체부 공연예술", "K-뮤지컬",
    "예술경영지원센터 뮤지컬", "한국문화예술위원회 공연", "한국뮤지컬협회", "뮤지컬 협회", "연극 협회",
    "뮤지컬 포럼", "뮤지컬 컨퍼런스", "공연예술 토론회", "공연 세미나", "공연예술 마켓", "공연계 제도",
    # 작품 소식(홍보)
    "뮤지컬 개막", "뮤지컬 캐스팅", "뮤지컬 티켓 오픈", "창작뮤지컬 초연", "뮤지컬 재연",
]
# '공연'만으로는 축제·시장 행사 기사까지 걸려서, 공연예술계를 가리키는 말이 있어야 한다
FIELD_RE = re.compile(
    r"뮤지컬|공연예술|공연계|공연 ?업계|공연 ?산업|공연 ?시장|연극|무대예술|예술인|예술위|아르코|ARKO|"
    r"예술경영|문예진흥|기초예술|대학로|공연장|문체부|문화체육관광부"
)
# 사진 설명만 있는 기사
PHOTO_RE = re.compile(r"^\[?(포토|사진)|포토뉴스|사진=|^(인터뷰하는|포즈 취하는|인사말하는|발언하는|미소 짓는|손 흔드는) ")
# 지역 예술제·정기공연 같은 행사 공연 — 단체 이름이 있어도 '협회·단체' 소식으로 보지 않는다
LOCAL_SHOW_RE = re.compile(r"정기공연|초청작|초청 공연|예술제|페스타|축제|공연 개최|공연을 펼")
# 공연예술 쪽 단체 이름 (예: 한국뮤지컬배우협회, 한국연극협회, 공연프로듀서협회)
ASSOC_RE = re.compile(
    r"(뮤지컬|연극|공연|공연예술|극장|프로듀서|배우|창작자|예술인)\S*(협회|협의회|연합회|노조|노동조합|조합)"
    r"|(협회|협의회|연합회|노조)\S*\s.*(창립|출범|설립|이사장|총회|성명|회장|선출)"
)

# (분류, 조건) — 위에서부터 먼저 맞는 것으로 분류
CATEGORIES = [
    ("포럼·행사", re.compile(r"포럼|컨퍼런스|콘퍼런스|세미나|토론회|심포지엄|간담회|공청회|워크숍|마켓|페어|박람회|아카데미")),
    ("정책·지원", re.compile(r"정책|지원사업|지원 사업|문체부|문화체육관광부|예술위|예술위원회|예술경영지원센터|"
                            r"예산(?!군|교육|시)|법안|개정|제도|공모|육성|기금|바우처|진흥")),
    ("협회·단체", ASSOC_RE),
]
PROMO = "작품 소식"
PROMO_RE = re.compile(r"뮤지컬")
PROMO_MAX_AGE_DAYS = 14
PROMO_MAX = 40
MAX_AGE_DAYS = 30
MAX_ITEMS = 120


def categorize(title, summary=""):
    """기사 분류. 업계 소식 분류가 우선이고, 아니면 뮤지컬 작품 소식, 둘 다 아니면 None."""
    text = title + " " + summary
    if PHOTO_RE.search(title) or not FIELD_RE.search(text):
        return None
    for name, rx in CATEGORIES:
        if name == "협회·단체" and LOCAL_SHOW_RE.search(title):
            continue
        if rx.search(text):
            return name
    return PROMO if PROMO_RE.search(title) else None


def _words(title):
    # '한국뮤지컬창작자협회'와 '뮤지컬창작자협회'를 같은 말로 보도록 앞의 '한국'은 뗀다
    return {re.sub(r"^한국", "", w) for w in re.findall(r"[0-9A-Za-z가-힣]{2,}", title)}


def _similar(a, b):
    """같은 소식을 다른 언론사가 낸 기사인지: 제목 단어가 많이 겹치거나, 긴 고유명사를 함께 쓰면 같은 소식으로 본다."""
    if not a or not b:
        return False
    common = a & b
    return len(common) / min(len(a), len(b)) >= 0.5 or any(len(w) >= 6 for w in common)


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
    promo_cutoff = iso(now_kst() - timedelta(days=PROMO_MAX_AGE_DAYS))
    seen, kept_words, result, promo_count = set(), [], [], 0
    for a in sorted(articles, key=lambda a: a["published"], reverse=True):
        key = _norm(a["title"])
        if not key or key in seen or a["published"] < cutoff:
            continue
        category = categorize(a["title"], a["summary"])
        if not category:
            continue
        if category == PROMO and (promo_count >= PROMO_MAX or a["published"] < promo_cutoff):
            continue
        words = _words(a["title"])
        if any(_similar(words, w) for w in kept_words):
            continue  # 같은 소식의 다른 언론사 기사
        seen.add(key)
        kept_words.append(words)
        a["category"] = category
        promo_count += category == PROMO
        result.append(a)
    return result[:MAX_ITEMS], errors
