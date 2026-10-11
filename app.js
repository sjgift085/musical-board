'use strict';

const NEW_DAYS = 7; // 이 기간 안에 처음 발견된 공모는 NEW 표시
const $ = (id) => document.getElementById(id);

const state = {
  contests: [],
  rankings: {},
  rankSource: null,
  newsCategory: '',
  news: [],
  status: {},
  sources: new Set(), // 비어 있으면 전체
  lastVisit: null,
};

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* 무시 */ } },
  sget(key) { try { return sessionStorage.getItem(key); } catch { return null; } },
  sset(key, value) { try { sessionStorage.setItem(key, value); } catch { /* 무시 */ } },
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// 외부에서 수집한 링크는 http(s)만 허용
function safeUrl(u) {
  return /^https?:\/\//i.test(u || '') ? esc(u) : '#';
}

function norm(s) {
  return String(s ?? '').toLowerCase().replace(/\s+/g, '');
}

function today() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function parseDay(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

function dday(deadline) {
  const d = parseDay(deadline);
  if (!d) return null;
  return Math.round((d - today()) / 86400000);
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

function fmtDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${hh}:${mm}`;
}

async function loadJSON(name, fallback) {
  try {
    const res = await fetch(`data/${name}?t=${Date.now()}`);
    if (!res.ok) throw new Error(res.status);
    return await res.json();
  } catch {
    return fallback;
  }
}

/* ---------- 공모 ---------- */

function isNew(item) {
  if (item.baseline) return false;
  const first = new Date(item.firstSeen);
  return Date.now() - first < NEW_DAYS * 86400000;
}

function isSinceLastVisit(item) {
  return !item.baseline && !!state.lastVisit && new Date(item.firstSeen) > new Date(state.lastVisit);
}

// 자동 수집이 막혀 있는 사이트: 버튼을 누르면 그 사이트를 새 창으로 연다
const EXTERNAL_CONTESTS = [
  { name: 'OTR', url: 'https://otr.co.kr/contest/' },
  { name: '충주문화관광재단', url: 'https://cjcf.or.kr/new/bbs/board.php?bo_table=offering&sca=%EA%B3%B5%EB%AA%A8%EC%A4%91' },
];
const EXTERNAL_RANKINGS = [
  { name: '티켓링크', url: 'https://www.ticketlink.co.kr/ranking' },
];

function externalChips(list) {
  return list.map((x) => `<a class="chip chip-link" href="${safeUrl(x.url)}" target="_blank" rel="noopener"
    title="자동 수집이 막혀 있어 사이트에서 직접 확인">${esc(x.name)} ↗</a>`).join('');
}

function sourceKey(c) {
  return c.group || c.source;
}

function renderSourceChips() {
  // 지역 재단처럼 group 이 있으면 버튼 하나로 묶는다
  const names = new Map();
  Object.entries(state.status.contests || {}).forEach(([id, s]) => {
    if (s && s.name) names.set(s.group || id, s.groupName || s.name);
  });
  state.contests.forEach((c) => names.set(sourceKey(c), c.groupName || c.sourceName));
  const chips = [['', '전체'], ...names.entries()];
  $('sourceChips').innerHTML = chips.map(([id, name]) => {
    const active = id === '' ? state.sources.size === 0 : state.sources.has(id);
    return `<button type="button" class="chip${active ? ' active' : ''}" data-source="${esc(id)}">${esc(name)}</button>`;
  }).join('') + externalChips(EXTERNAL_CONTESTS);
}

function renderContests() {
  const q = norm($('contestSearch').value);
  const onlyRelevant = $('onlyRelevant').checked;
  const onlyNew = $('onlyNew').checked;
  const hideClosed = $('hideClosed').checked;
  const sort = $('contestSort').value;

  let list = state.contests.filter((c) => {
    if (state.sources.size && !state.sources.has(sourceKey(c))) return false;
    if (onlyRelevant && !(c.tags || []).length) return false;
    if (onlyNew && !isNew(c)) return false;
    const left = dday(c.deadline);
    if (hideClosed && left !== null && left < 0) return false;
    if (q && !norm(`${c.title} ${c.meta} ${c.sourceName}`).includes(q)) return false;
    return true;
  });

  if (sort === 'new') {
    list = list.slice().sort((a, b) => new Date(b.firstSeen) - new Date(a.firstSeen));
  } else if (sort === 'deadline') {
    list = list.slice().sort((a, b) => {
      const da = dday(a.deadline); const db = dday(b.deadline);
      if (da === null) return 1;
      if (db === null) return -1;
      return da - db;
    });
  }

  $('contestList').innerHTML = list.map((c) => {
    const left = dday(c.deadline);
    let due = '';
    if (left !== null) {
      const cls = left < 0 ? 'closed' : left <= 7 ? 'soon' : '';
      const label = left < 0 ? '마감' : left === 0 ? 'D-DAY' : `D-${left}`;
      due = `<span class="dday ${cls}">${label}</span>`;
    }
    const badges = [
      isSinceLastVisit(c) ? '<span class="badge fresh">지난 방문 이후</span>'
        : isNew(c) ? '<span class="badge fresh">NEW</span>' : '',
      ...(c.tags || []).map((t) => `<span class="badge">${esc(t)}</span>`),
    ].join('');
    return `<li class="card${isNew(c) ? ' is-new' : ''}">
      <div class="card-top"><span class="src">${c.groupName ? `${esc(c.groupName)} · ` : ''}${esc(c.sourceName)}</span>${badges}${due}</div>
      <a class="title" href="${safeUrl(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>
      ${c.period ? `<p class="period">기간 ${esc(c.period)}</p>` : ''}
      ${c.meta ? `<p class="meta">${esc(c.meta)}</p>` : ''}
      <p class="seen">${c.baseline ? '처음 수집 때부터 있던 공모' : `${fmtDate(c.firstSeen)} 발견`}</p>
    </li>`;
  }).join('');

  const empty = $('contestEmpty');
  empty.hidden = list.length > 0;
  empty.textContent = state.contests.length
    ? '조건에 맞는 공모가 없어요. 필터를 바꿔 보세요.'
    : '아직 수집된 공모가 없어요. GitHub Actions에서 수집이 한 번 실행되면 채워집니다.';

  const newCount = state.contests.filter((c) => isSinceLastVisit(c) && (c.tags || []).length).length;
  $('newCount').hidden = !newCount;
  $('newCount').textContent = newCount;
}

/* ---------- 새 공연 ---------- */

/* ---------- 예매 순위 ---------- */


function rankingSources() {
  return Object.entries(state.rankings.sources || {}).filter(([, src]) => (src.items || []).length);
}

function renderRankChips() {
  const sources = rankingSources();
  if (!state.rankSource || !sources.some(([id]) => id === state.rankSource)) {
    state.rankSource = sources.length ? sources[0][0] : null;
  }
  $('rankChips').innerHTML = sources.map(([id, src]) => `<button type="button"
    class="chip${id === state.rankSource ? ' active' : ''}" data-rank="${esc(id)}">${esc(src.name)}</button>`).join('')
    + externalChips(EXTERNAL_RANKINGS);
}

function changeBadge(change) {
  if (change === 'new') return '<span class="move new">NEW</span>';
  if (typeof change !== 'number' || change === 0) return '<span class="move same">–</span>';
  return change > 0
    ? `<span class="move up">▲${change}</span>`
    : `<span class="move down">▼${-change}</span>`;
}

function renderRankings() {
  renderRankChips();
  const src = (state.rankings.sources || {})[state.rankSource];
  const items = src ? src.items : [];
  $('rankList').innerHTML = items.map((r) => `<li class="rank-row">
      <span class="rank-no">${r.rank}</span>
      ${r.poster ? `<img src="${safeUrl(r.poster)}" alt="" loading="lazy">` : '<div class="noposter">🎭</div>'}
      <div class="rank-body">
        <a href="${safeUrl(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>
        ${r.venue ? `<p>${esc(r.venue)}</p>` : ''}
        ${r.start ? `<p>${esc(r.start)}${r.end ? ` ~ ${esc(r.end)}` : ''}</p>` : ''}
        ${r.rate ? `<p>예매율 ${esc(r.rate)}</p>` : ''}
      </div>
      ${changeBadge(r.change)}
    </li>`).join('');
  $('rankMeta').innerHTML = src
    ? `<a href="${safeUrl(src.url)}" target="_blank" rel="noopener">${esc(src.name)} 순위 페이지</a> · ${fmtDateTime(src.updatedAt)} 기준 · 순위 변동은 지난 수집과 비교`
    : '';
  const empty = $('rankEmpty');
  empty.hidden = items.length > 0;
  empty.textContent = '아직 수집된 예매 순위가 없어요.';
}

/* ---------- 업계 소식 ---------- */

function newsItem(n) {
  return `<li>
      ${n.category ? `<span class="badge">${esc(n.category)}</span>` : ''}
      <a href="${safeUrl(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      ${n.summary ? `<p>${esc(n.summary)}</p>` : ''}
      <span class="byline">${esc(n.press || n.via)} · ${fmtDateTime(n.published)}</span>
    </li>`;
}

function renderNewsChips() {
  const ORDER = ['정책·지원', '포럼·행사', '협회·단체', '작품 소식'];
  const present = new Set(state.news.map((n) => n.category).filter(Boolean));
  const cats = [...ORDER.filter((c) => present.has(c)), ...[...present].filter((c) => !ORDER.includes(c))];
  $('newsChips').innerHTML = ['', ...cats].map((c) => `<button type="button"
    class="chip${(state.newsCategory || '') === c ? ' active' : ''}" data-cat="${esc(c)}">${esc(c || '전체')}</button>`).join('');
}

function renderNews() {
  renderNewsChips();
  const q = norm($('newsSearch').value);
  const list = state.news.filter((n) => {
    if (state.newsCategory && n.category !== state.newsCategory) return false;
    return !q || norm(`${n.title} ${n.summary} ${n.press}`).includes(q);
  });
  $('newsList').innerHTML = list.map(newsItem).join('');
  const empty = $('newsEmpty');
  empty.hidden = list.length > 0;
  empty.textContent = state.news.length ? '조건에 맞는 기사가 없어요.' : '아직 수집된 기사가 없어요.';
}

/* ---------- 상태 ---------- */

function renderStatus() {
  const rows = [];
  Object.values(state.status.contests || {}).forEach((s) => {
    if (!s || !s.name) return;
    rows.push(`<li class="${s.ok ? 'ok' : 'bad'}"><a href="${safeUrl(s.home)}" target="_blank" rel="noopener">${esc(s.name)}</a>
      — ${s.ok ? (s.note ? esc(s.note) : `${s.count}건 확인`) : esc(s.error || '실패')} <small>${fmtDateTime(s.checkedAt)}</small></li>`);
  });
  Object.values(state.status.rankings || {}).forEach((s) => {
    if (!s || !s.name) return;
    rows.push(`<li class="${s.ok ? 'ok' : 'bad'}">예매 순위 · ${esc(s.name)}
      — ${s.ok ? `${s.count}위까지` : esc(s.error || '실패')} <small>${fmtDateTime(s.checkedAt)}</small></li>`);
  });
  [['news', '업계 소식']].forEach(([key, name]) => {
    const s = state.status[key];
    if (!s) return;
    const err = s.error || (s.errors && s.errors[0]) || '';
    rows.push(`<li class="${s.ok ? 'ok' : 'bad'}">${name} — ${s.count ?? 0}건${err ? ` · ${esc(err)}` : ''}
      <small>${fmtDateTime(s.checkedAt)}</small></li>`);
  });
  $('statusList').innerHTML = rows.join('') || '<li>아직 수집 기록이 없어요.</li>';
  $('updated').textContent = state.status.updatedAt
    ? `마지막 수집 ${fmtDateTime(state.status.updatedAt)}`
    : '아직 수집 전입니다';
}

/* ---------- 이벤트 ---------- */

function switchTab(name) {
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) => { p.hidden = p.id !== `tab-${name}`; });
  store.set('mh.tab', name);
}

function bind() {
  $('tabs').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-tab]');
    if (b) switchTab(b.dataset.tab);
  });
  $('sourceChips').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-source]');
    if (!b) return;
    const id = b.dataset.source;
    if (!id) state.sources.clear();
    else if (state.sources.has(id)) state.sources.delete(id);
    else state.sources.add(id);
    renderSourceChips();
    renderContests();
  });
  ['contestSearch', 'contestSort', 'onlyRelevant', 'onlyNew', 'hideClosed'].forEach((id) => {
    $(id).addEventListener('input', renderContests);
  });
  $('newsSearch').addEventListener('input', renderNews);
  $('rankChips').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-rank]');
    if (!b) return;
    state.rankSource = b.dataset.rank;
    store.set('mh.rankSource', state.rankSource);
    renderRankings();
  });
  $('newsChips').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-cat]');
    if (!b) return;
    state.newsCategory = b.dataset.cat;
    renderNews();
  });
}

async function init() {
  // '지난 방문' 시각: 이번 탭을 닫기 전까지는 같은 값을 유지
  state.lastVisit = store.sget('mh.prevVisit') ?? store.get('mh.lastVisit');
  store.sset('mh.prevVisit', state.lastVisit ?? '');
  store.set('mh.lastVisit', new Date().toISOString());
  if (state.lastVisit === '') state.lastVisit = null;

  bind();
  const saved = store.get('mh.tab');
  if (saved && $(`tab-${saved}`)) switchTab(saved);

  state.rankSource = store.get('mh.rankSource');
  const [contests, rankings, news, status] = await Promise.all([
    loadJSON('contests.json', { items: [] }),
    loadJSON('rankings.json', { sources: {} }),
    loadJSON('news.json', { items: [] }),
    loadJSON('status.json', {}),
  ]);
  state.contests = contests.items || [];
  state.rankings = rankings || { sources: {} };
  state.news = news.items || [];
  state.status = status || {};

  renderSourceChips();
  renderContests();
  renderRankings();
  renderNews();
  renderStatus();
}

init();
