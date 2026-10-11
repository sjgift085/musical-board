"""예매 사이트 뮤지컬 순위 수집.

예매 사이트들은 화면을 자주 바꾸고 일부는 자바스크립트로 그리기 때문에 두 가지 방법을 함께 쓴다.
1) 페이지 안에 들어 있는 JSON(__NEXT_DATA__ 등)에서 '공연 목록'처럼 생긴 배열을 찾는다.
2) 없으면 HTML에서 상품 상세 링크(/goods/123, /Perf/123 ...)를 나온 순서대로 모은다.
링크가 나온 순서를 순위로 본다.
"""
import json
import re

import requests
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import os

from common import DEBUG_DIR, HEADERS, clean, fetch, find_dates, now_kst

SOURCES = [
    {
        # 페이지 안에 순위가 그려져 있음. 상품 링크는 nol.yanolja.com/ticket/products/123
        "id": "interpark",
        "name": "인터파크(NOL) 티켓",
        "url": "https://tickets.interpark.com/contents/ranking?genre=MUSICAL",
        "link_re": r"/(?:ticket/products|goods)/(\w{6,})",
        "detail": "https://nol.yanolja.com/ticket/products/{0}",
    },
    {
        # 화면은 자바스크립트로 그리고, 데이터는 아래 API(JSONP)에서 받음. 뮤지컬/연극이 섞여 있어 뮤지컬만 거른다.
        "id": "melon",
        "name": "멜론티켓",
        "url": "https://ticket.melon.com/ranking/index.htm",
        "api": "https://tktapi.melon.com/poc/ranking/listFromHourly.json",
        "detail": "https://ticket.melon.com/performance/index.htm?prodId={0}",
    },
]
TOP_N = 20

TITLE_KEYS = ("goodsName", "prdNm", "perfName", "productName", "performanceName", "title", "name")
CODE_KEYS = ("goodsCode", "prodId", "perfId", "productId", "performanceId", "perfCode", "id")
VENUE_KEYS = ("placeName", "placeNm", "venueName", "hallName", "place", "venue")
POSTER_KEYS = ("posterImageUrl", "posterUrl", "imageUrl", "poster", "imgUrl", "image")
START_KEYS = ("playStartDate", "startDate", "perfStartDay", "startDt", "playStartDt")
END_KEYS = ("playEndDate", "endDate", "perfEndDay", "endDt", "playEndDt")


def _pick(d, keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return ""


SHORT_DATE_RE = re.compile(r"(?<![\d.])(\d{2})\.(\d{2})\.(\d{2})(?![\d.])")


def _dates(text):
    """'2026.10.01' 과 '26.10.01' 둘 다 읽는다."""
    return find_dates(text) or [f"20{y}-{m}-{d}" for y, m, d in SHORT_DATE_RE.findall(text or "")]


def _date(s):
    found = _dates(s)
    if found:
        return found[0]
    m = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _json_lists(obj, depth=0):
    """JSON 안의 '딕셔너리 배열'을 모두 꺼낸다."""
    if depth > 12:
        return
    if isinstance(obj, list):
        if len(obj) >= 3 and all(isinstance(x, dict) for x in obj[:3]):
            yield obj
        for x in obj:
            yield from _json_lists(x, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _json_lists(v, depth + 1)


def from_json(html, source):
    soup = BeautifulSoup(html, "lxml")
    blobs = []
    for s in soup.find_all("script"):
        text = s.string or s.get_text() or ""
        if s.get("type") in ("application/json", "application/ld+json") or s.get("id") == "__NEXT_DATA__":
            blobs.append(text)
    for text in blobs:
        try:
            data = json.loads(text)
        except ValueError:
            continue
        for arr in _json_lists(data):
            rows = [x for x in arr if _pick(x, TITLE_KEYS)]
            if len(rows) < 3 or not any(_pick(x, CODE_KEYS) for x in rows):
                continue
            out = []
            for i, x in enumerate(rows[:TOP_N], 1):
                code = _pick(x, CODE_KEYS)
                poster = _pick(x, POSTER_KEYS)
                if poster.startswith("//"):
                    poster = "https:" + poster
                out.append({
                    "rank": i,
                    "title": clean(_pick(x, TITLE_KEYS)),
                    "venue": clean(_pick(x, VENUE_KEYS)),
                    "start": _date(_pick(x, START_KEYS)),
                    "end": _date(_pick(x, END_KEYS)),
                    "poster": poster if poster.startswith("http") else "",
                    "url": source["detail"].format(code) if code else source["url"],
                })
            return out
    return []


def from_links(html, base_url, source):
    soup = BeautifulSoup(html, "lxml")
    link_re = re.compile(source["link_re"], re.I)
    order, info = [], {}
    for a in soup.find_all("a"):
        m = link_re.search((a.get("href") or "") + " " + (a.get("onclick") or ""))
        if not m:
            continue
        code = m.group(1)
        img = a.find("img")
        head = a.find(["h2", "h3", "h4", "strong"])
        title = (clean(head.get_text(" ")) if head else "") or clean(a.get_text(" ")) \
            or clean((img.get("alt") if img else "") or a.get("title") or "")
        if code not in info:
            order.append(code)
            info[code] = {"title": "", "poster": "", "row": ""}
        cur = info[code]
        if len(title) > len(cur["title"]):
            cur["title"] = title
        if img and not cur["poster"]:
            src = img.get("src") or img.get("data-src") or ""
            cur["poster"] = urljoin(base_url, src) if src else ""
        if not cur["row"]:
            row = a
            for _ in range(4):
                if row.parent is None or row.parent.name in ("body", "html", "ul", "ol", "tbody"):
                    break
                row = row.parent
            cur["row"] = clean(a.get_text(" ")) if head else clean(row.get_text(" "))

    out = []
    for code in order:
        cur = info[code]
        if not cur["title"]:
            continue
        dates = _dates(cur["row"])
        venue = re.search(r"장소\s+(.+?)(?:\s+공연기간|$)", cur["row"])
        rate = re.search(r"예매율\s*([\d.]+)\s*%", cur["row"])
        out.append({
            "rank": len(out) + 1,
            "title": re.sub(r"^\d{1,2}\s+", "", cur["title"]),
            "venue": venue.group(1)[:60] if venue else "",
            "rate": rate.group(1) + "%" if rate else "",
            "start": dates[0] if dates else "",
            "end": dates[1] if len(dates) > 1 else "",
            "poster": cur["poster"] if cur["poster"].startswith("http") else "",
            "url": source["detail"].format(code),
        })
        if len(out) >= TOP_N:
            break
    return out


def melon(source):
    res = requests.post(source["api"], timeout=30, headers={**HEADERS, "Referer": source["url"]}, data={
        "v": "1", "rankType": "TR0006", "rankDt": now_kst().strftime("%Y%m%d"),
        "gCode": "NEW_GENRE_ART", "callback": "rankingListFromHourly",
    })
    if DEBUG_DIR:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(os.path.join(DEBUG_DIR, "rank-melon-api.txt"), "w", encoding="utf-8") as f:
            f.write(res.text)
    res.raise_for_status()
    body = res.text.strip()
    if not body.startswith("{"):  # JSONP: callback({...});
        body = body[body.index("(") + 1: body.rindex(")")]
    data = json.loads(body)
    out = []
    for x in data.get("data") or []:
        title = clean(x.get("subTitle") or x.get("title") or "")
        if "뮤지컬" not in title:
            continue
        poster = x.get("posterImg") or ""
        cur, prev = x.get("curRank"), x.get("prevRank")
        change = None
        if isinstance(cur, int) and isinstance(prev, int):
            change = "new" if prev == 0 else prev - cur
        out.append({
            "rank": len(out) + 1,
            "title": title,
            "venue": clean(x.get("placeName") or ""),
            "start": "", "end": "", "rate": "",
            "poster": ("https://cdnticket.melon.co.kr" + poster) if poster.startswith("/") else poster,
            "url": source["detail"].format(x.get("prodId")),
            "change": change,
        })
        if len(out) >= TOP_N:
            break
    return out


# 아직 지원하지 않는 사이트의 구조를 확인하려고, 디버그 모드에서만 원본을 저장해 둔다
PROBES = {
    "probe-yes24.html": "http://ticket.yes24.com/Rank/Musical",
    "probe-yes24-ranking.js": "https://tkfile.yes24.com/New/Js/ranking.js",
}


def save_probes():
    if not DEBUG_DIR:
        return
    for name, url in PROBES.items():
        try:
            fetch(url, retries=1, debug_name=name)
        except Exception as e:  # noqa: BLE001
            print(f"[순위] probe {url}: {e}")


def crawl_source(source):
    if source["id"] == "melon":
        return melon(source)
    res = fetch(source["url"], debug_name=f"rank-{source['id']}.html")
    return from_json(res.text, source) or from_links(res.text, res.url, source)


def mark_changes(items, previous):
    """지난번 순위와 비교해 변동(▲▼, NEW)을 붙인다."""
    norm = lambda t: re.sub(r"\W", "", t).replace("뮤지컬", "")
    prev = {norm(x["title"]): x["rank"] for x in previous}
    for it in items:
        if it.get("change") is not None:
            continue  # 사이트가 직접 알려 준 변동(멜론)은 그대로 쓴다
        before = prev.get(norm(it["title"]))
        it["change"] = "new" if before is None else before - it["rank"]
    return items
