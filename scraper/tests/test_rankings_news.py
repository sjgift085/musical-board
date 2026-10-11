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


def test_news_keeps_only_industry_articles(monkeypatch):
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
    }
