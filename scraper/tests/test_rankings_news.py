import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import news  # noqa: E402
import rankings  # noqa: E402
from common import now_kst  # noqa: E402

SRC = {"id": "t", "name": "테스트", "url": "https://t.example/rank",
       "link_re": r"/goods/(\w{6,})", "detail": "https://t.example/goods/{0}"}

NEXT = {"props": {"pageProps": {"menu": [{"a": 1}], "ranking": [
    {"goodsCode": "A000001", "goodsName": "뮤지컬 〈하나〉", "placeName": "샘플아트센터",
     "playStartDate": "20261001", "playEndDate": "20261231", "posterImageUrl": "//img.example/1.jpg"},
    {"goodsCode": "A000002", "goodsName": "뮤지컬 〈둘〉", "placeName": "샘플극장"},
    {"goodsCode": "A000003", "goodsName": "뮤지컬 〈셋〉"},
]}}}
JSON_PAGE = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(NEXT, ensure_ascii=False)}</script>'

INTERPARK_LIKE = """<ul><li><a href="https://nol.yanolja.com/ticket/products/26013995"><article>
 <img src="https://img.example/p.gif"><span>1위</span><h3>뮤지컬 〈하나〉</h3>
 <p><span>장소 </span>샘플아트센터</p><p><span>공연기간 </span>26.12.22 ~ 27.02.28</p>
 <span>예매율 25.6%</span></article></a></li></ul>"""

LINK_PAGE = """
<ul class="rank">
 <li><span>1</span><a href="/goods/B000001"><img src="https://img.example/b1.jpg" alt="뮤지컬 첫째"></a>
     <a href="/goods/B000001">뮤지컬 첫째</a> 2026.10.01 ~ 2026.12.31</li>
 <li><span>2</span><a href="/goods/B000002">뮤지컬 둘째</a></li>
 <li><a href="/notice/1">공지사항입니다</a></li>
</ul>"""


def test_ranking_from_embedded_json():
    items = rankings.from_json(JSON_PAGE, SRC)
    assert [i["title"] for i in items] == ["뮤지컬 〈하나〉", "뮤지컬 〈둘〉", "뮤지컬 〈셋〉"]
    first = items[0]
    assert first["rank"] == 1 and first["venue"] == "샘플아트센터"
    assert (first["start"], first["end"]) == ("2026-10-01", "2026-12-31")
    assert first["poster"] == "https://img.example/1.jpg"
    assert first["url"] == "https://t.example/goods/A000001"


def test_ranking_from_links():
    assert rankings.from_json(LINK_PAGE, SRC) == []
    items = rankings.from_links(LINK_PAGE, "https://t.example/rank", SRC)
    assert [(i["rank"], i["title"]) for i in items] == [(1, "뮤지컬 첫째"), (2, "뮤지컬 둘째")]
    assert items[0]["poster"] == "https://img.example/b1.jpg"
    assert items[0]["start"] == "2026-10-01"


def test_rank_changes():
    prev = [{"title": "뮤지컬 첫째", "rank": 3}]
    items = rankings.mark_changes([{"title": "첫째", "rank": 1}, {"title": "새작품", "rank": 2}], prev)
    assert [i["change"] for i in items] == [2, "new"]


def test_news_collect_categorizes(monkeypatch):
    when = now_kst().strftime("%a, %d %b %Y %H:%M:%S %z")
    titles = [
        "문체부, 내년 K-뮤지컬 지원 예산 확대",
        "한국뮤지컬협회 정기총회 개최",
        "창작뮤지컬 산업 활성화 포럼 열려",
        "뮤지컬 '샘플' 캐스팅 공개… 화려한 라인업",
    ]
    items = "".join(f"<item><title>{t} - 샘플일보</title><link>https://n.example/{i}</link>"
                    f"<pubDate>{when}</pubDate><source>샘플일보</source></item>"
                    for i, t in enumerate(titles))
    rss = f"<rss><channel>{items}</channel></rss>"
    monkeypatch.setattr(news, "fetch", lambda url, **kw: types.SimpleNamespace(content=rss.encode()))
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    result, errors = news.collect()
    got = {a["title"]: a["category"] for a in result}
    assert got == {
        "문체부, 내년 K-뮤지컬 지원 예산 확대": "정책·지원",
        "한국뮤지컬협회 정기총회 개최": "협회·단체",
        "창작뮤지컬 산업 활성화 포럼 열려": "포럼·행사",
        "뮤지컬 '샘플' 캐스팅 공개… 화려한 라인업": "작품 소식",
    }


def test_ranking_interpark_card():
    src = {**SRC, "link_re": r"/(?:ticket/products|goods)/(\w{6,})"}
    [item] = rankings.from_links(INTERPARK_LIKE, "https://t.example/rank", src)
    assert item["title"] == "뮤지컬 〈하나〉"
    assert item["venue"] == "샘플아트센터"
    assert (item["start"], item["end"]) == ("2026-12-22", "2027-02-28")
    assert item["rate"] == "25.6%"
    assert item["url"] == "https://t.example/goods/26013995"


def test_melon_jsonp(monkeypatch):
    body = 'rankingListFromHourly({"result":"0","data":[' + ",".join([
        '{"curRank":1,"prevRank":3,"subTitle":"뮤지컬 〈둘〉","placeName":"극장","posterImg":"/a.jpg","prodId":11}',
        '{"curRank":2,"prevRank":0,"subTitle":"연극 〈셋〉","placeName":"소극장","posterImg":"","prodId":12}',
        '{"curRank":3,"prevRank":0,"subTitle":"뮤지컬 〈넷〉","placeName":"홀","posterImg":"","prodId":13}',
    ]) + ']});'
    resp = types.SimpleNamespace(text=body, raise_for_status=lambda: None)
    monkeypatch.setattr(rankings.requests, "post", lambda *a, **k: resp)
    items = rankings.melon(rankings.SOURCES[1])
    assert [(i["rank"], i["title"], i["change"]) for i in items] == [(1, "뮤지컬 〈둘〉", 2), (2, "뮤지컬 〈넷〉", "new")]
    assert items[0]["poster"] == "https://cdnticket.melon.co.kr/a.jpg"


def test_categorize():
    c = news.categorize
    assert c("포즈 취하는 정영주 한국뮤지컬배우협회 이사장") is None          # 사진 설명
    assert c("제23회 군포예인예술제, 군포연예예술인협회 정기공연 10일 개최") is None  # 뮤지컬 없는 지역 행사
    assert c("제21회 동두천종합예술제, 창작뮤지컬 '동행' 공연") == "포럼·행사"   # 뮤지컬이 있는 지역 행사
    assert c("부산진문화재단, 베트남 호찌민시연극협회 초청작 선보여") is None
    assert c("한국뮤지컬배우협회 출범…초대 이사장에 정영주") == "협회·단체"
    assert c("뮤지컬 창작자, 협회 창립 나선다") == "협회·단체"
    assert c("문예진흥기금 공모 8일 시작…기초예술 지원예산 939억원") == "정책·지원"
    assert c("2026 부산국제공연예술마켓 개막") == "포럼·행사"
    assert c("뮤지컬 '레베카' 캐스팅 공개") == "작품 소식"
    assert c("하이브 3분기 매출 1조 돌파") is None


YES24 = """<div class='rank-best'><div><a href='/Perf/60521' title='뮤지컬 [하나]'><span class='rank-best-img'>
<img src='https://img.example/1.jpg'></span><p class='rlb-tit'>뮤지컬 [하나]</p>
<p class='rlb-sub-tit'>2026.12.22~2027.02.28<br>블루스퀘어</p><p class='rank-best-point'><strong>27.7%</strong></p>
<p class='rank-best-number'><span>1위</span><span>-</span></p></a></div></div>
<div class='rank-list'><div><div class='fluctuation'><p><span>4위</span></p><p class="rank-list-number-down">2</p></div>
<div><a href='/Perf/58563'><img src='https://img.example/4.jpg'></a></div>
<div><p class='rank-list-tit'><a href='/Perf/58563'>뮤지컬 [넷]</a></p></div>
<div><p>2026.08.13~2027.03.01<br>샤롯데씨어터</p></div><div>7%</div></div></div>"""


def test_yes24_parser():
    src = next(s for s in rankings.SOURCES if s["id"] == "yes24")
    items = rankings.parse_yes24(YES24, src)
    assert [(i["rank"], i["title"], i["venue"], i["rate"], i["change"]) for i in items] == [
        (1, "뮤지컬 [하나]", "블루스퀘어", "27.7%", 0),
        (4, "뮤지컬 [넷]", "샤롯데씨어터", "7%", -2),
    ]
    assert (items[1]["start"], items[1]["end"]) == ("2026-08-13", "2027-03-01")
    assert items[1]["url"] == "http://ticket.yes24.com/Perf/58563"
