"""수집기 공통 도구: HTTP 요청, 날짜 파싱, JSON 저장."""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEBUG_DIR = os.environ.get("MH_DEBUG_DIR")  # 지정하면 받아온 원본 HTML을 저장

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}


def now_kst():
    return datetime.now(KST)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def fetch(url, *, params=None, retries=3, timeout=30, debug_name=None):
    """GET 요청. 실패하면 짧게 쉬었다가 재시도한다."""
    last = None
    for attempt in range(retries):
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            res.raise_for_status()
            if not res.encoding or res.encoding.lower() == "iso-8859-1":
                res.encoding = res.apparent_encoding
            if DEBUG_DIR and debug_name:
                os.makedirs(DEBUG_DIR, exist_ok=True)
                with open(os.path.join(DEBUG_DIR, debug_name), "w", encoding="utf-8") as f:
                    f.write(res.text)
            return res
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?")


def find_dates(text):
    """문자열에서 YYYY.MM.DD 형태 날짜를 모두 찾아 'YYYY-MM-DD' 목록으로 돌려준다."""
    out = []
    for y, m, d in DATE_RE.findall(text or ""):
        try:
            out.append(datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d"))
        except ValueError:
            pass
    return out


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_json(name, default):
    path = os.path.join(DATA_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
