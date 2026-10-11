# 🎭 뮤지컬 작가 공모 알림판

뮤지컬 작가가 볼 만한 공모를 여러 사이트에서 모아 **새로 올라온 것만 골라 볼 수 있게** 해 주는 정적 웹사이트입니다.
예매 사이트 뮤지컬 순위와 정책·포럼·협회 등 업계 소식도 함께 보여 줍니다.

## 무엇을 모으나

| 탭 | 출처 | 비고 |
| --- | --- | --- |
| 공모 | [아트누리](https://artnuri.or.kr) · [문화포털](https://www.culture.go.kr) · [아르코 통합플랫폼](https://thearts.arko.or.kr) · [스토리움](https://www.storyum.kr) | 각 사이트 목록 첫 1~3페이지. [OTR](https://otr.co.kr/contest/)은 자동 접속을 막아 화면에 링크만 안내 |
| 예매 순위 | 인터파크(NOL)·멜론티켓 뮤지컬 순위 | 사이트별 상위 20위, 지난 수집 대비 ▲▼/NEW |
| 업계 소식 | Google 뉴스 RSS (+ 네이버 뉴스 API, 선택) | 최근 45일 정책·지원 / 포럼·행사(뮤지컬이 들어간 지역 예술제·축제 포함) / 협회·단체 기사, 그 뒤에 최근 14일 뮤지컬 작품 소식(개막·캐스팅·티켓 오픈 등, 최대 40건). 사진 설명만 있는 기사는 뺌 |

## 주요 기능

- **새 공모 표시** — 처음 발견된 지 7일 안 된 공모에 `NEW`, 지난번 방문 이후 올라온 공모에 `지난 방문 이후` 표시, 탭에 개수 표시
- 사이트별 필터, **뮤지컬·창작 관련만** 보기(문화포털·스토리움처럼 장르 필터가 없는 곳은 제목 키워드로 판단), 마감 지난 공모 숨기기
- 새로 올라온 순 / **마감 임박순(D-day)** 정렬, 검색
- 예매 순위는 사이트별로 골라 보고, 업계 소식은 분류별로 골라 보기
- 화면 아래 **수집 상태**에서 사이트별 수집 성공/실패 확인

## 작동 방식

```
GitHub Actions (3시간마다)
  └─ scraper/main.py  ──>  data/contests.json, rankings.json, news.json, status.json 커밋
GitHub Pages
  └─ index.html + app.js 가 data/*.json 을 읽어 화면에 표시
```

브라우저에서 다른 사이트를 직접 읽을 수 없어서(CORS) 서버 대신 GitHub Actions가 주기적으로 수집해 JSON으로 저장합니다.
공모마다 처음 발견한 시각(`firstSeen`)을 기록해 두기 때문에 '새 공모'를 구분할 수 있습니다.
어떤 사이트를 처음 수집할 때 이미 올라와 있던 공모는 '새 공모'로 치지 않습니다.

## 설정 방법

1. **Actions 켜기** — 저장소의 Actions 탭에서 워크플로 사용을 허용합니다(처음 한 번).
2. *(선택)* 네이버 기사도 받으려면 [네이버 개발자센터](https://developers.naver.com)에서 검색 API 앱을 만들고 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`를 등록합니다.
3. **GitHub Pages 켜기** — Settings → Pages → Source: *Deploy from a branch*, `main` / `(root)`.
   주소는 `https://<사용자명>.github.io/musical-board/` 입니다.
4. Actions 탭 → **뮤지컬 공모 수집** → *Run workflow*로 첫 수집을 바로 실행할 수 있습니다.

## 사이트 구조가 바뀌었거나 0건이 나올 때

공모 수집기(`scraper/contests.py`)와 순위 수집기(`scraper/rankings.py`)는 특정 CSS 선택자에 묶이지 않고 '날짜가 적힌 줄 안의 링크'를 공모로 보는 범용 방식이라
사이트 개편에 비교적 잘 버티지만, 완벽하지는 않습니다.

- 화면 아래 **수집 상태**에 실패 사유가 나옵니다.
- 매 실행마다 받아온 원본 HTML이 `debug-html` 브랜치(최근 1회분)와 Actions 실행 결과의 **crawl-debug-html** 아티팩트(7일)에 보관됩니다.
- 그 HTML을 보고 `SOURCES`의 해당 사이트에 다음을 적어 주면 그것을 우선 사용합니다.
  - `item_selector` / `title_selector` — 공모 한 줄과 제목 링크의 CSS 선택자
  - `js_link` — 링크가 `onclick="fn_view('123')"` 같은 자바스크립트인 경우 상세 주소 템플릿 (예: `https://.../view.do?id={0}`).
    없으면 목록 페이지로 연결됩니다.
- 해외 IP 접속을 막는 사이트는 GitHub Actions(미국 서버)에서 실패할 수 있습니다.
  이 경우 국내 PC/서버에서 `python scraper/main.py`를 주기적으로 실행해 커밋하는 방식으로 바꿀 수 있습니다.

## 로컬에서 실행

```bash
pip install -r scraper/requirements.txt
python scraper/main.py                                # contests / news / rankings 하나만 지정 가능
python -m http.server 8000                                       # http://localhost:8000
python -m pytest scraper/tests                      # 수집기 테스트
```
