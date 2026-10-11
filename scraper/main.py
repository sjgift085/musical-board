"""모든 수집기를 실행해 data/*.json 을 갱신한다.

    python scraper/main.py            # 전부
    python scraper/main.py contests   # 공모만 (news, shows 도 가능)

MH_DEBUG_DIR=경로 를 주면 받아온 공모 사이트 HTML을 저장한다(구조가 바뀌었을 때 확인용).
"""
import sys
import traceback
from datetime import timedelta

import contests
import news
import shows
from common import iso, load_json, now_kst, save_json

KEEP_DAYS = 60  # 목록에서 사라진 공모를 이 기간까지는 보관


def run_contests(status):
    now = iso(now_kst())
    old = load_json("contests.json", {"items": []})
    by_id = {it["id"]: it for it in old.get("items", [])}
    known_sources = {it["source"] for it in by_id.values()}

    for source in contests.SOURCES:
        st = {"name": source["name"], "home": source["home"], "checkedAt": now}
        try:
            items = contests.crawl_source(source)
        except Exception as e:  # noqa: BLE001 - 한 사이트 실패가 전체를 막지 않게
            st.update(ok=False, count=0, error=f"{type(e).__name__}: {e}"[:300])
            traceback.print_exc()
            status["contests"][source["id"]] = st
            print(f"[공모] {source['name']}: 실패 - {st['error']}")
            continue

        if not items:
            st.update(ok=False, count=0, error="목록에서 공모 항목을 찾지 못함 (사이트 구조 확인 필요)")
            status["contests"][source["id"]] = st
            print(f"[공모] {source['name']}: 0건")
            continue

        # 처음 수집하는 사이트의 기존 공모는 '새 공모'로 표시하지 않는다
        baseline = source["id"] not in known_sources
        added = 0
        for it in items:
            it["id"] = contests.item_id(it)
            prev = by_id.get(it["id"])
            if prev:
                it["firstSeen"] = prev["firstSeen"]
                it["baseline"] = prev.get("baseline", False)
            else:
                it["firstSeen"] = now
                it["baseline"] = baseline
                added += 0 if baseline else 1
            it["lastSeen"] = now
            by_id[it["id"]] = it
        st.update(ok=True, count=len(items), added=added)
        status["contests"][source["id"]] = st
        print(f"[공모] {source['name']}: {len(items)}건 (새 공모 {added}건)")

    cutoff = iso(now_kst() - timedelta(days=KEEP_DAYS))
    kept = [it for it in by_id.values() if it["lastSeen"] >= cutoff]
    kept.sort(key=lambda it: (it["firstSeen"], it["lastSeen"]), reverse=True)
    save_json("contests.json", {"updatedAt": now, "items": kept})


def run_news(status):
    items, errors = news.collect()
    st = {"checkedAt": iso(now_kst()), "count": len(items), "errors": errors}
    if items:
        save_json("news.json", {"updatedAt": st["checkedAt"], "items": items})
    st["ok"] = bool(items)
    status["news"] = st
    print(f"[기사] {len(items)}건, 오류 {len(errors)}건")


def run_shows(status):
    old = load_json("shows.json", {"items": []})
    items, errors = shows.collect(old.get("items", []))
    st = {"checkedAt": iso(now_kst()), "errors": errors}
    if items is not None:
        save_json("shows.json", {"updatedAt": st["checkedAt"], "items": items})
        st.update(ok=True, count=len(items))
    else:
        st.update(ok=False, count=len(old.get("items", [])))
    status["shows"] = st
    print(f"[공연] {st['count']}건, 오류 {len(errors)}건")


def main(argv):
    targets = argv or ["contests", "news", "shows"]
    status = load_json("status.json", {})
    status.setdefault("contests", {})
    for name in targets:
        try:
            {"contests": run_contests, "news": run_news, "shows": run_shows}[name](status)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            status[name] = {**status.get(name, {}), "ok": False, "error": str(e)[:300],
                            "checkedAt": iso(now_kst())}
    status["updatedAt"] = iso(now_kst())
    save_json("status.json", status)


if __name__ == "__main__":
    main(sys.argv[1:])
