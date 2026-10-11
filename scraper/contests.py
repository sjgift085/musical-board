"""공모 사이트 수집기.

사이트마다 HTML 구조가 다르고 수시로 바뀌기 때문에, 특정 CSS 선택자에 의존하지 않는
범용 추출기(extract_items)를 기본으로 쓴다. 목록 화면에서 '날짜가 들어 있는 줄(li/tr/...)
안의 링크'를 공모 항목으로 본다. 사이트별로 더 정확한 선택자를 알게 되면 SOURCES의
item_selector / title_selector 에 적어 주면 그것을 먼저 쓴다.
"""
import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import DATE_RE, clean, fetch, find_dates

SOURCES = [
    {
        "id": "artnuri",
        "name": "아트누리",
        "home": "https://artnuri.or.kr",
        "url": (
            "https://artnuri.or.kr/crawler/info/search.do?docid=&source=&pageSetting=1&sc_seNo="
            "&key=2301170002&sc_orderBy=&recordCountPerPage=10&pageIndex={page}&sc_hash=&sc_list="
            "&seNo=&sw=&sc_genre=&sc_genre=%EB%AE%A4%EC%A7%80%EC%BB%AC&sc_target=&sc_local="
            "&sc_field=&sc_isDo="
        ),
        "pages": 3,
        "musical_filtered": True,  # 사이트 검색 조건에 이미 '뮤지컬' 장르가 걸려 있음
    },
    {
        "id": "culture",
        "name": "문화포털",
        "home": "https://www.culture.go.kr",
        "url": (
            "https://www.culture.go.kr/portal/cltBnf/cltSup/list.do?menuNo=200104"
            "&searchFldCd=01&pageIndex={page}"
        ),
        "pages": 3,
        "musical_filtered": False,
    },
    {
        "id": "arko",
        "name": "아르코 통합플랫폼",
        "home": "https://thearts.arko.or.kr",
        "url": (
            "https://thearts.arko.or.kr/thearts/news/contest?page={page}&pageSize=10&condition="
            "&genreName=%EB%AE%A4%EC%A7%80%EC%BB%AC&searchOrder=createDate&keyword="
        ),
        "pages": 3,
        "musical_filtered": True,
    },
    {
        "id": "storyum",
        "name": "스토리움",
        "home": "https://www.storyum.kr",
        "url": (
            "https://www.storyum.kr/story/progrm/master/listStartN.do?menuNo=500024&searchCnd="
            "&prgSe=&prgNm=&sdate=&edate=&reqstMthd=&progrsSttus=&deptId=&useAt=&prgCn="
            "&siteSe=story&degree=&viewType=&siteId=5&inoutSe=&pageIndex={page}"
        ),
        "pages": 2,
        "musical_filtered": False,
    },
    {
        "id": "otr",
        "name": "OTR",
        "home": "https://otr.co.kr",
        "url": "https://otr.co.kr/contest/",
        "pages": 1,
        "musical_filtered": False,
    },
]

# 제목이 이런 말이면 메뉴/버튼이지 공모가 아님
NAV_WORDS = {
    "더보기", "목록", "이전", "다음", "처음", "마지막", "검색", "로그인", "회원가입", "홈",
    "사이트맵", "닫기", "자세히", "자세히보기", "바로가기", "top", "prev", "next", "more",
    "신청하기", "공유하기", "개인정보처리방침", "이용약관",
}

# 목록 본문이 아닌 영역(머리말, 메뉴, 꼬리말 등)으로 보이는 id/class 조각
NOISE_HINTS = (
    "header", "footer", "gnb", "lnb", "snb", "nav", "menu", "breadcrumb", "location",
    "paging", "pagination", "quick", "banner", "popup", "sitemap", "skip", "family",
)

DETAIL_HREF_RE = re.compile(
    r"(view|detail|read|show|seq|idx|sn=|no=|id=|/\d{3,}|/contest/[^/?#]+)", re.I
)
JS_ARGS_RE = re.compile(r"""['"]?([A-Za-z0-9_\-]+)['"]?""")

MUSICAL_WORDS = ("뮤지컬", "musical")
WRITING_WORDS = (
    "극본", "희곡", "대본", "창작", "작가", "스토리", "시나리오", "음악극", "공연예술",
    "공연", "무대", "작곡", "가사", "리딩", "쇼케이스", "레지던시", "창작산실", "신진",
)


def _is_noise(tag):
    for parent in [tag, *tag.parents]:
        if parent.name in ("body", "html", "[document]"):
            return False
        if parent.name in ("header", "footer", "nav", "script", "style", "noscript"):
            return True
        attrs = " ".join(
            [parent.get("id") or "", *(parent.get("class") or [])]
        ).lower() if hasattr(parent, "get") else ""
        if attrs and any(h in attrs for h in NOISE_HINTS):
            return True
    return False


def _title_of(a):
    title = clean(a.get_text(" "))
    if len(title) < 6 and a.get("title"):
        title = clean(a["title"])
    title = re.sub(r"^(new|N|NEW|진행중|접수중|마감임박|모집중)\s+", "", title)
    return title


def _resolve_link(a, base_url, source):
    href = (a.get("href") or "").strip()
    if href and not href.startswith("#") and not href.lower().startswith("javascript"):
        return urljoin(base_url, href)
    # 자바스크립트 링크: 사이트별 템플릿이 있으면 인자로 상세 주소를 만든다
    script = (a.get("onclick") or "") + " " + href
    template = source.get("js_link")
    if template:
        call = re.search(r"\(([^)]*)\)", script)
        if call:
            args = JS_ARGS_RE.findall(call.group(1))
            try:
                return template.format(*args)
            except (IndexError, KeyError):
                pass
    return None


def _container_of(a):
    """링크를 감싸는 '한 줄'(li, tr, article ...)을 찾는다."""
    node = a
    for _ in range(6):
        node = node.parent
        if node is None or node.name in ("body", "html", "ul", "ol", "tbody", "table"):
            return None
        if node.name in ("li", "tr", "article", "dl"):
            return node
        if node.name == "div" and find_dates(node.get_text(" ")):
            # 날짜가 들어 있는 가장 작은 div — 단, 링크를 너무 많이 품으면 목록 전체임
            if len(node.find_all("a")) <= 4:
                return node
    return None


def _make_item(source, title, url, container_text, list_url):
    dates = find_dates(container_text)
    # 부가 정보(기관, 상태 등): 제목·날짜·글번호를 뺀 나머지
    meta = container_text.replace(title, " ", 1)
    meta = DATE_RE.sub(" ", meta)
    meta = re.sub(r"\s*[~\-–]\s*(?=\s|$)", " ", meta)
    meta = re.sub(r"^\s*\d{1,6}\s+", "", clean(meta))
    meta = clean(meta)[:160]
    period = ""
    if len(dates) >= 2:
        period = f"{dates[0]} ~ {dates[-1]}"
    elif dates:
        period = dates[0]
    return {
        "source": source["id"],
        "sourceName": source["name"],
        "title": title,
        "url": url or list_url,
        "period": period,
        "deadline": dates[-1] if dates else "",
        "meta": meta,
    }


def extract_items(html, base_url, source):
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()

    # 1) 사이트별로 지정한 선택자가 있으면 우선 사용
    if source.get("item_selector"):
        for row in soup.select(source["item_selector"]):
            a = row.select_one(source.get("title_selector") or "a")
            if not a:
                continue
            title = _title_of(a)
            if len(title) < 4 or title in seen:
                continue
            seen.add(title)
            url = _resolve_link(a, base_url, source)
            items.append(_make_item(source, title, url, row.get_text(" "), base_url))
        if items:
            return items

    # 2) 범용 추출: 날짜가 있는 줄 안의 링크
    items = _generic(soup, base_url, source, skip_noise=True)
    if not items:
        # 본문 전체가 'menu' 같은 이름의 영역 안에 있는 사이트도 있어 한 번 더 시도
        items = _generic(soup, base_url, source, skip_noise=False)
    return items


def _generic(soup, base_url, source, skip_noise):
    items = []
    seen = set()
    best = {}  # container id -> (title, a, container)
    order = []
    for a in soup.find_all("a"):
        title = _title_of(a)
        if len(title) < 6 or len(title) > 200 or title.lower() in NAV_WORDS:
            continue
        if skip_noise and _is_noise(a):
            continue
        container = _container_of(a)
        href = (a.get("href") or "") + " " + (a.get("onclick") or "")
        has_date = bool(container and find_dates(container.get_text(" ")))
        if not has_date and not (container and DETAIL_HREF_RE.search(href)):
            continue
        key = id(container)
        if key not in best:
            order.append(key)
            best[key] = (title, a, container)
        elif len(title) > len(best[key][0]):
            best[key] = (title, a, container)

    for key in order:
        title, a, container = best[key]
        if title in seen:
            continue
        seen.add(title)
        url = _resolve_link(a, base_url, source)
        items.append(_make_item(source, title, url, container.get_text(" "), base_url))
    return items


def tag_item(item, source):
    text = item["title"] + " " + item.get("meta", "")
    tags = []
    if source.get("musical_filtered") or any(w in text.lower() for w in MUSICAL_WORDS):
        tags.append("뮤지컬")
    if any(w in text for w in WRITING_WORDS):
        tags.append("창작·공연")
    item["tags"] = tags
    return item


def item_id(item):
    key = item["source"] + "|" + re.sub(r"\s+", "", item["title"])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def crawl_source(source):
    items = []
    titles = set()
    for page in range(1, source.get("pages", 1) + 1):
        url = source["url"].format(page=page)
        res = fetch(url, debug_name=f"{source['id']}-p{page}.html")
        page_items = extract_items(res.text, res.url, source)
        new = [it for it in page_items if it["title"] not in titles]
        if not new:
            break  # 다음 페이지가 없거나 같은 내용 반복
        for it in new:
            titles.add(it["title"])
            items.append(tag_item(it, source))
        if "{page}" not in source["url"]:
            break
    return items
