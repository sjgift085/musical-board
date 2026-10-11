"""범용 추출기가 흔한 게시판 형태(표, 카드 목록, 자바스크립트 링크)를 읽어 내는지 확인.

    python -m pytest scraper/tests
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contests  # noqa: E402
from common import find_dates  # noqa: E402

SRC = {"id": "t", "name": "테스트", "home": "https://ex.kr", "musical_filtered": False}

MENU = """
<header><ul class="gnb"><li><a href="/a">지원사업 공모 안내 메뉴</a></li></ul></header>
<div id="lnb"><a href="/b">공모전 전체 목록 보기</a></div>
"""

TABLE = MENU + """
<table class="board"><tbody>
 <tr><td>3</td><td class="subject"><a href="view.do?seq=103">2026 창작뮤지컬 극본 공모</a></td>
     <td>한국문화예술위원회</td><td>2026.10.01 ~ 2026.10.31</td></tr>
 <tr><td>2</td><td class="subject"><a href="view.do?seq=102">지역 공연예술 지원사업 공고</a></td>
     <td>서울문화재단</td><td>2026-09-20 ~ 2026-10-20</td></tr>
</tbody></table>
<div class="paging"><a href="?page=2">2</a><a href="?page=3">다음 페이지로 이동</a></div>
<footer><a href="/privacy">개인정보처리방침 안내 링크</a></footer>
"""

CARDS = MENU + """
<ul class="list">
 <li><div class="card"><span class="badge">접수중</span>
   <a href="/contest/musical-writer-2026/"><strong>신진 뮤지컬 작가 발굴 프로젝트</strong></a>
   <p>마감 2026년 11월 5일</p></div></li>
 <li><div class="card"><a href="/contest/short-story/"><strong>단편소설 공모전</strong></a>
   <p>접수기간 2026.10.10 - 2026.11.30</p></div></li>
</ul>
"""

JS = MENU + """
<ul class="board_list">
 <li><a href="javascript:void(0);" onclick="fn_view('PRG0001','5')">스토리 창작자 레지던시 참가자 모집</a>
   <span class="date">2026.10.02 ~ 2026.10.25</span></li>
</ul>
"""


def titles(items):
    return [it["title"] for it in items]


def test_find_dates():
    assert find_dates("2026.10.01 ~ 2026-10-31, 2026년 11월 5일") == [
        "2026-10-01", "2026-10-31", "2026-11-05"]


def test_table_board():
    items = contests.extract_items(TABLE, "https://ex.kr/list.do", SRC)
    assert titles(items) == ["2026 창작뮤지컬 극본 공모", "지역 공연예술 지원사업 공고"]
    first = items[0]
    assert first["url"] == "https://ex.kr/view.do?seq=103"
    assert first["deadline"] == "2026-10-31"
    assert first["period"] == "2026-10-01 ~ 2026-10-31"
    assert "한국문화예술위원회" in first["meta"]


def test_card_list():
    items = contests.extract_items(CARDS, "https://ex.kr/contest/", SRC)
    assert titles(items) == ["신진 뮤지컬 작가 발굴 프로젝트", "단편소설 공모전"]
    assert items[0]["url"] == "https://ex.kr/contest/musical-writer-2026/"
    assert items[0]["deadline"] == "2026-11-05"


def test_js_link_falls_back_to_list_then_uses_template():
    items = contests.extract_items(JS, "https://ex.kr/list.do", SRC)
    assert items[0]["url"] == "https://ex.kr/list.do"
    src = {**SRC, "js_link": "https://ex.kr/view.do?prgId={0}&siteId={1}"}
    items = contests.extract_items(JS, "https://ex.kr/list.do", src)
    assert items[0]["url"] == "https://ex.kr/view.do?prgId=PRG0001&siteId=5"


def test_custom_selector():
    src = {**SRC, "item_selector": "table.board tr", "title_selector": "td.subject a"}
    items = contests.extract_items(TABLE, "https://ex.kr/list.do", src)
    assert len(items) == 2


def test_tags():
    items = contests.extract_items(CARDS, "https://ex.kr/contest/", SRC)
    tagged = [contests.tag_item(it, SRC)["tags"] for it in items]
    assert "뮤지컬" in tagged[0] and "창작·공연" in tagged[0]
    assert "뮤지컬" not in tagged[1]
    assert contests.item_id(items[0]) == contests.item_id(dict(items[0]))
