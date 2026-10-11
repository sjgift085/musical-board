"""새로 개막하는 뮤지컬.

기본은 PlayDB(회원가입 불필요, playdb.py). KOPIS(공연예술통합전산망) Open API 키가
환경변수 KOPIS_API_KEY 로 주어지면 KOPIS 정보도 함께 쓴다.
"""
import os
from datetime import timedelta

from bs4 import BeautifulSoup

import playdb
from common import clean, fetch, now_kst

API = "http://www.kopis.or.kr/openApi/restful"
MUSICAL = "GGGA"  # KOPIS 장르 코드: 뮤지컬
PAST_DAYS = 30    # 최근 30일 안에 개막한 공연
FUTURE_DAYS = 30  # 30일 안에 개막할 공연


def _text(node, name):
    found = node.find(name)
    return clean(found.get_text()) if found else ""


def _https(url):
    return url.replace("http://", "https://", 1) if url else url


def _list(key, start, end):
    shows, page = [], 1
    while page <= 10:
        res = fetch(f"{API}/pblprfr", params={
            "service": key, "stdate": start.strftime("%Y%m%d"), "eddate": end.strftime("%Y%m%d"),
            "cpage": page, "rows": 100, "shcate": MUSICAL,
        })
        soup = BeautifulSoup(res.content, "xml")
        rows = soup.find_all("db")
        if not rows:
            if page == 1 and soup.find("returncode"):
                raise RuntimeError(_text(soup, "errmsg") or "KOPIS 오류 응답")
            break
        for db in rows:
            shows.append({
                "id": _text(db, "mt20id"),
                "title": _text(db, "prfnm"),
                "start": _text(db, "prfpdfrom").replace(".", "-"),
                "end": _text(db, "prfpdto").replace(".", "-"),
                "venue": _text(db, "fcltynm"),
                "area": _text(db, "area"),
                "poster": _https(_text(db, "poster")),
                "state": _text(db, "prfstate"),
                "openrun": _text(db, "openrun") == "Y",
            })
        if len(rows) < 100:
            break
        page += 1
    return shows


def _detail(key, show_id):
    res = fetch(f"{API}/pblprfr/{show_id}", params={"service": key})
    db = BeautifulSoup(res.content, "xml").find("db")
    if not db:
        return {}
    links = []
    for rel in db.find_all("relate"):
        url = _text(rel, "relateurl")
        if url:
            links.append({"name": _text(rel, "relatenm") or "예매", "url": url})
    return {
        "synopsis": _text(db, "sty"),
        "synopsisImages": [_https(clean(u.get_text())) for u in db.find_all("styurl")][:4],
        "cast": _text(db, "prfcast"),
        "crew": _text(db, "prfcrew"),
        "runtime": _text(db, "prfruntime"),
        "age": _text(db, "prfage"),
        "price": _text(db, "pcseguidance"),
        "producer": _text(db, "entrpsnm") or _text(db, "entrpsnmP"),
        "schedule": _text(db, "dtguidance"),
        "links": links[:4],
        "kopis": f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={show_id}",
    }


def _kopis(key, previous):
    today = now_kst().date()
    lo, hi = today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS)
    # KOPIS는 한 번에 31일까지만 조회되므로 둘로 나눠 묻는다
    found = _list(key, lo, today) + _list(key, today + timedelta(days=1), hi)

    cache = {s["id"]: s for s in previous}
    errors, result, seen = [], [], set()
    for s in found:
        if not s["id"] or s["id"] in seen or s["openrun"]:
            continue
        seen.add(s["id"])
        if not (lo.isoformat() <= s["start"] <= hi.isoformat()):
            continue  # 오래전에 개막해 계속 공연 중인 작품은 제외
        old = cache.get(s["id"])
        if old and "synopsis" in old:
            detail = {k: old[k] for k in old if k not in s}
        else:
            try:
                detail = _detail(key, s["id"])
            except Exception as e:  # noqa: BLE001
                errors.append(f"{s['title']} 상세: {e}")
                detail = {}
        result.append({**s, **detail, "via": "KOPIS"})
    return result, errors


def _same(a, b):
    norm = lambda t: "".join(ch for ch in t if ch.isalnum()).replace("뮤지컬", "")
    return norm(a["title"]) == norm(b["title"])


def collect(previous):
    """previous: 지난번 shows.json 의 items (상세정보를 다시 받지 않으려고 재사용).

    돌려주는 값: (공연 목록 또는 None(모든 출처 실패), 오류 목록)
    """
    result, errors, any_ok = [], [], False

    key = os.environ.get("KOPIS_API_KEY")
    if key:
        try:
            items, errs = _kopis(key, previous)
            result += items
            errors += errs
            any_ok = True
        except Exception as e:  # noqa: BLE001
            errors.append(f"KOPIS: {e}")

    items, errs = playdb.collect(previous, PAST_DAYS, FUTURE_DAYS)
    errors += errs
    if items:
        any_ok = True
    for show in items:  # KOPIS에 이미 있는 작품은 PlayDB 쪽을 빼고 줄거리만 보충
        twin = next((r for r in result if _same(r, show)), None)
        if twin is None:
            result.append(show)
        elif not twin.get("synopsis") and show.get("synopsis"):
            twin["synopsis"] = show["synopsis"]

    result.sort(key=lambda s: s["start"], reverse=True)
    return (result if any_ok else None), errors
