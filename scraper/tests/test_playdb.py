import os
import sys
import types
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import playdb  # noqa: E402
from common import now_kst  # noqa: E402

TODAY = now_kst().date()
SOON = (TODAY + timedelta(days=5)).strftime("%Y.%m.%d")
LATER = (TODAY + timedelta(days=90)).strftime("%Y.%m.%d")
OLD = "2020.01.01"

LIST = f"""
<table><tr><td><a href="javascript:goDetail('123456')"><img src="p.jpg" alt="뮤지컬 새작품"></a></td>
  <td><a href="javascript:goDetail('123456')">뮤지컬 &lt;새작품&gt;</a><br>{SOON} ~ 2027.01.31 샘플극장</td></tr>
<tr><td><a href="/playdb/playdbDetail.asp?sReqPlayno=222222">뮤지컬 오래된작품</a> {OLD} ~ 2027.12.31</td></tr>
<tr><td><a href="/playdb/playdbDetail.asp?sReqPlayno=333333">뮤지컬 먼작품</a> {LATER} ~ 2027.12.31</td></tr>
</table>"""

DETAIL = f"""<html><head><meta property="og:title" content="뮤지컬 &lt;새작품&gt; - PlayDB">
<meta property="og:image" content="http://ticketimage.example/p.jpg"></head><body>
<table>
 <tr><td>기간</td><td>{SOON} ~ 2027.01.31</td></tr>
 <tr><td>장소</td><td>샘플극장</td></tr>
 <tr><td>출연</td><td>배우1, 배우2</td></tr>
</table>
<div class="tab"><h4>줄거리</h4><p>1920년대 경성, 이름 없는 작곡가가 마지막 노래를 완성하기까지의 이야기.</p></div>
</body></html>"""


def test_list_plays():
    found = playdb.list_plays(LIST)
    assert set(found) == {"123456", "222222", "333333"}
    assert found["123456"][0] == "뮤지컬 <새작품>"


def test_collect_filters_by_opening_date(monkeypatch):
    def fake(url, **kw):
        if "Detail" in url:
            return types.SimpleNamespace(text=DETAIL)
        return types.SimpleNamespace(text=LIST if "Page=1" in url else "")
    monkeypatch.setattr(playdb, "fetch", fake)
    items, errors = playdb.collect([], 30, 30)
    assert errors == []
    assert [s["id"] for s in items] == ["playdb-123456"]
    show = items[0]
    assert show["title"] == "뮤지컬 <새작품>"
    assert show["venue"] == "샘플극장"
    assert show["cast"] == "배우1, 배우2"
    assert show["synopsis"].startswith("1920년대 경성")
    assert show["poster"].startswith("https://")
