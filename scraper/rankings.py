"""예매 사이트 뮤지컬 순위 수집.

예매 사이트들은 화면을 자주 바꾸고 일부는 자바스크립트로 그리기 때문에 두 가지 방법을 함께 쓴다.
1) 페이지 안에 들어 있는 JSON(__NEXT_DATA__ 등)에서 '공연 목록'처럼 생긴 배열을 찾는다.
2) 없으면 HTML에서 상품 상세 링크(/goods/123, /Perf/123 ...)를 나온 순서대로 모은다.
링크가 나온 순서를 순위로 본다.
"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean, fetch, find_dates

SOURCES = [
    {
        "id": "interpark",
        "name": "인터파크(NOL) 티켓",
        "url": "https://tickets.interpark.com/contents/ranking?genre=MUSICAL",
        "link_re": r"/goods/(\w{6,})",
        "detail": "https://tickets.interpark.com/goods/{0}",
    },
    {
        "id": "yes24",
        "name": "예스24 티켓",
        "url": "http://ticket.yes24.com/New/Rank/Ranking.aspx?genre=15457",
        "link_re": r"/Perf/(\d{4,})",
        "detail": "http://ticket.yes24.com/Perf/{0}",
    },
    {
        "id": "melon",
        "name": "멜론티켓",
        "url": "https://ticket.melon.com/ranking/index.htm?genreType=GENRE_ART",
        "link_re": r"prodId=(\d{4,})",
        "detail": "https://ticket.melon.com/performance/index.htm?prodId={0}",
    },
    {
        "id": "ticketlink",
        "name": "티켓링크",
        "url": "https://www.ticketlink.co.kr/ranking?type=PERFORMANCE&categoryId=16",
        "link_re": r"/product/(\d{4,})",
        "detail": "https://www.ticketlink.co.kr/product/{0}",
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


def _date(s):
    found = find_dates(s)
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
        title = clean(a.get_text(" ")) or clean((img.get("alt") if img else "") or a.get("title") or "")
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
            cur["row"] = clean(row.get_text(" "))

    out = []
    for code in order:
        cur = info[code]
        if not cur["title"]:
            continue
        dates = find_dates(cur["row"])
        out.append({
            "rank": len(out) + 1,
            "title": re.sub(r"^\d{1,2}\s+", "", cur["title"]),
            "venue": "",
            "start": dates[0] if dates else "",
            "end": dates[1] if len(dates) > 1 else "",
            "poster": cur["poster"] if cur["poster"].startswith("http") else "",
            "url": source["detail"].format(code),
        })
        if len(out) >= TOP_N:
            break
    return out


def crawl_source(source):
    res = fetch(source["url"], debug_name=f"rank-{source['id']}.html")
    return from_json(res.text, source) or from_links(res.text, res.url, source)


def mark_changes(items, previous):
    """지난번 순위와 비교해 변동(▲▼, NEW)을 붙인다."""
    norm = lambda t: re.sub(r"\W", "", t).replace("뮤지컬", "")
    prev = {norm(x["title"]): x["rank"] for x in previous}
    for it in items:
        before = prev.get(norm(it["title"]))
        it["change"] = "new" if before is None else before - it["rank"]
    return items
