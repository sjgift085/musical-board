"""새 뮤지컬: PlayDB(플레이디비) 공연 정보 페이지 수집 — 회원가입·키 불필요.

목록에서 작품 번호(sReqPlayno)를 모은 뒤, 상세 페이지에서 기간·장소·줄거리를 읽는다.
페이지 구조가 바뀌어도 버티도록 특정 CSS 선택자 대신 '줄거리', '장소' 같은
라벨 글자를 기준으로 찾는다.
"""
import re
from datetime import timedelta

from bs4 import BeautifulSoup

from common import clean, fetch, find_dates, now_kst

BASE = "http://www.playdb.co.kr/playdb"
LIST_URLS = [
    # 000001 = 뮤지컬. sPlayType 은 공연중/오픈예정 구분(무시되더라도 해가 없음)
    BASE + "/playdblist.asp?sReqMainCategory=000001&Page={page}",
    BASE + "/playdblist.asp?sReqMainCategory=000001&sPlayType=2&Page={page}",
    BASE + "/playdblist.asp?sReqMainCategory=000001&sPlayType=3&Page={page}",
]
PAGES = 3
DETAIL_URL = BASE + "/playdbDetail.asp?sReqPlayno={no}"
MAX_DETAILS = 60  # 한 번 실행에 새로 읽을 상세 페이지 수 상한

PLAY_NO_RE = re.compile(r"(?:sReqPlayno=|goDetail\(\s*['\"]?)(\d{4,})", re.I)
SYNOPSIS_LABELS = ("줄거리", "시놉시스", "작품소개", "작품 소개", "작품설명", "공연소개")


def list_plays(html):
    """목록 HTML에서 {작품번호: (제목, 줄 텍스트)} 를 뽑는다."""
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for a in soup.find_all("a"):
        m = PLAY_NO_RE.search((a.get("href") or "") + " " + (a.get("onclick") or ""))
        if not m:
            continue
        no = m.group(1)
        title = clean(a.get_text(" "))
        if not title:
            img = a.find("img")
            title = clean((img.get("alt") if img else "") or a.get("title") or "")
        row = a
        for _ in range(4):  # 날짜가 들어 있는 줄을 찾아 올라간다
            if row.parent is None or row.parent.name in ("body", "html"):
                break
            row = row.parent
            if find_dates(row.get_text(" ")):
                break
        row_text = clean(row.get_text(" "))
        prev_title, prev_row = found.get(no, ("", ""))
        found[no] = (title if len(title) > len(prev_title) else prev_title,
                     row_text if find_dates(row_text) else prev_row)
    return found


def _after_label(soup, labels, limit=1500, min_len=10):
    """'줄거리' 같은 라벨 바로 뒤에 오는 글을 찾는다."""
    for node in soup.find_all(string=True):
        text = clean(node)
        if not text or len(text) > 12 or not any(text.startswith(l) for l in labels):
            continue
        el = node.parent
        # 같은 요소 안에 라벨+본문이 같이 있으면 라벨만 떼어 낸다
        own = clean(el.get_text(" "))
        if len(own) > len(text) + min_len:
            return own[len(text):].lstrip(" :：")[:limit]
        # 아니면 다음 형제 요소들(또는 부모의 다음 형제)에서 본문을 찾는다
        for start in (el, el.parent):
            if start is None:
                continue
            for sib in start.find_next_siblings(limit=3):
                body = clean(sib.get_text(" "))
                if len(body) >= min_len:
                    return body[:limit]
    return ""


def _labelled(soup, labels):
    """'장소 : 샤롯데씨어터' 처럼 짧은 항목 값."""
    value = _after_label(soup, labels, limit=200, min_len=1)
    return value.split("  ")[0][:80]


def detail(no, fallback_title):
    url = DETAIL_URL.format(no=no)
    res = fetch(url, debug_name=f"playdb-detail-{no}.html")
    soup = BeautifulSoup(res.text, "lxml")
    meta = lambda prop: (soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop}) or {}).get("content", "")

    title = clean(meta("og:title")) or fallback_title
    title = re.sub(r"\s*[-|:]\s*(PlayDB|플레이디비).*$", "", title, flags=re.I)
    period_text = _after_label(soup, ("기간", "공연기간", "일시"), limit=120)
    dates = find_dates(period_text) or find_dates(soup.get_text(" "))[:2]
    synopsis = _after_label(soup, SYNOPSIS_LABELS) or clean(meta("og:description"))
    poster = meta("og:image")
    return {
        "id": f"playdb-{no}",
        "title": title,
        "start": dates[0] if dates else "",
        "end": dates[1] if len(dates) > 1 else (dates[0] if dates else ""),
        "venue": _labelled(soup, ("장소", "공연장")),
        "area": "",
        "poster": poster.replace("http://", "https://", 1) if poster else "",
        "synopsis": synopsis,
        "cast": _labelled(soup, ("출연", "캐스팅")),
        "runtime": _labelled(soup, ("관람시간", "러닝타임", "공연시간")),
        "age": _labelled(soup, ("관람등급", "관람연령")),
        "links": [{"name": "PlayDB 상세", "url": url}],
        "via": "PlayDB",
    }


def collect(previous, past_days, future_days):
    today = now_kst().date()
    lo = (today - timedelta(days=past_days)).isoformat()
    hi = (today + timedelta(days=future_days)).isoformat()

    candidates, errors = {}, []
    for template in LIST_URLS:
        for page in range(1, PAGES + 1):
            try:
                res = fetch(template.format(page=page),
                            debug_name=f"playdb-list{LIST_URLS.index(template)}-p{page}.html")
            except Exception as e:  # noqa: BLE001
                errors.append(f"PlayDB 목록: {e}")
                break
            found = list_plays(res.text)
            fresh = {k: v for k, v in found.items() if k not in candidates}
            if not fresh:
                break
            candidates.update(fresh)

    if not candidates:
        if not errors:
            errors.append("PlayDB 목록에서 작품을 찾지 못함 (사이트 구조 확인 필요)")
        return [], errors

    cache = {s["id"]: s for s in previous}
    result, fetched = [], 0
    for no, (title, row_text) in candidates.items():
        row_dates = find_dates(row_text)
        # 목록에 기간이 보이면 상세를 열기 전에 미리 거른다
        if row_dates and not (lo <= row_dates[0] <= hi):
            continue
        show = cache.get(f"playdb-{no}")
        if not show:
            if fetched >= MAX_DETAILS:
                continue
            fetched += 1
            try:
                show = detail(no, title)
            except Exception as e:  # noqa: BLE001
                errors.append(f"PlayDB {title or no}: {e}")
                continue
        if show["start"] and lo <= show["start"] <= hi:
            result.append(show)
    return result, errors
