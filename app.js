'use strict';

const NEW_DAYS = 7; // 이 기간 안에 처음 발견된 공모는 NEW 표시
const $ = (id) => document.getElementById(id);

const state = {
  contests: [],
  shows: [],
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

function renderSourceChips() {
  const names = new Map();
  state.contests.forEach((c) => names.set(c.source, c.sourceName));
  Object.entries(state.status.contests || {}).forEach(([id, s]) => {
    if (s && s.name) names.set(id, s.name);
  });
  const chips = [['', '전체'], ...names.entries()];
  $('sourceChips').innerHTML = chips.map(([id, name]) => {
    const active = id === '' ? state.sources.size === 0 : state.sources.has(id);
    return `<button type="button" class="chip${active ? ' active' : ''}" data-source="${esc(id)}">${esc(name)}</button>`;
  }).join('');
}

function renderContests() {
  const q = norm($('contestSearch').value);
  const onlyRelevant = $('onlyRelevant').checked;
  const onlyNew = $('onlyNew').checked;
  const hideClosed = $('hideClosed').checked;
  const sort = $('contestSort').value;

  let list = state.contests.filter((c) => {
    if (state.sources.size && !state.sources.has(c.source)) return false;
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
      <div class="card-top"><span class="src">${esc(c.sourceName)}</span>${badges}${due}</div>
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

function renderShows() {
  const q = norm($('showSearch').value);
  const range = $('showRange').value;
  const now = today();
  const list = state.shows.filter((s) => {
    const start = parseDay(s.start);
    if (range === 'opened' && start && start > now) return false;
    if (range === 'upcoming' && start && start <= now) return false;
    if (q && !norm(`${s.title} ${s.venue} ${s.area} ${s.cast}`).includes(q)) return false;
    return true;
  });
  if (range === 'upcoming') list.reverse(); // 곧 개막하는 것부터

  $('showList').innerHTML = list.map((s) => {
    const synopsis = s.synopsis || (s.synopsisImages?.length ? '줄거리 이미지가 있어요 — 눌러서 보기' : '줄거리 정보 없음');
    return `<li class="show" data-id="${esc(s.id)}" tabindex="0">
      ${s.poster ? `<img src="${safeUrl(s.poster)}" alt="" loading="lazy">` : '<div class="noposter">🎭</div>'}
      <div class="show-body">
        <h3>${esc(s.title)}</h3>
        <p class="when">${esc(s.start)} ~ ${esc(s.end)}</p>
        <p class="where">${esc(s.venue)}${s.area ? ` · ${esc(s.area)}` : ''}</p>
        <p class="synopsis">${esc(synopsis)}</p>
      </div>
    </li>`;
  }).join('');

  const empty = $('showEmpty');
  empty.hidden = list.length > 0;
  empty.textContent = state.shows.length
    ? '조건에 맞는 공연이 없어요.'
    : '아직 수집된 공연 정보가 없어요. 아래 개막 소식 기사를 참고하세요.';

  const opening = state.news.filter((n) => OPENING_RE.test(n.title));
  $('openingNews').innerHTML = opening.length
    ? opening.map(newsItem).join('')
    : '<li class="empty">관련 기사가 아직 없어요.</li>';
}

function openShow(id) {
  const s = state.shows.find((x) => x.id === id);
  if (!s) return;
  const row = (label, value) => (value ? `<dt>${label}</dt><dd>${esc(value)}</dd>` : '');
  const links = [...(s.links || []), ...(s.kopis ? [{ name: 'KOPIS 상세', url: s.kopis }] : [])];
  $('showDetail').innerHTML = `
    <div class="detail-head">
      ${s.poster ? `<img src="${safeUrl(s.poster)}" alt="">` : ''}
      <div>
        <h2>${esc(s.title)}</h2>
        <dl>
          ${row('기간', `${s.start} ~ ${s.end}`)}
          ${row('공연장', s.venue)}
          ${row('출연', s.cast)}
          ${row('제작진', s.crew)}
          ${row('제작사', s.producer)}
          ${row('러닝타임', s.runtime)}
          ${row('관람연령', s.age)}
          ${row('가격', s.price)}
          ${row('공연시간', s.schedule)}
        </dl>
      </div>
    </div>
    <h3>줄거리</h3>
    <p class="synopsis-full">${s.synopsis ? esc(s.synopsis) : '등록된 줄거리 글이 없어요.'}</p>
    ${(s.synopsisImages || []).map((u) => `<img class="sty" src="${safeUrl(u)}" alt="소개 이미지" loading="lazy">`).join('')}
    <p class="links">${links.map((l) => `<a href="${safeUrl(l.url)}" target="_blank" rel="noopener">${esc(l.name)}</a>`).join('')}</p>`;
  $('showDialog').showModal();
}

/* ---------- 기사 ---------- */

const OPENING_RE = /개막|초연|막을? 올|프리뷰|첫 공연|재연|귀환|돌아온/;

function newsItem(n) {
  return `<li>
      <a href="${safeUrl(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      ${n.summary ? `<p>${esc(n.summary)}</p>` : ''}
      <span class="byline">${esc(n.press || n.via)} · ${fmtDateTime(n.published)}</span>
    </li>`;
}

function renderNews() {
  const q = norm($('newsSearch').value);
  const list = state.news.filter((n) => !q || norm(`${n.title} ${n.summary} ${n.press}`).includes(q));
  $('newsList').innerHTML = list.map(newsItem).join('');
  const empty = $('newsEmpty');
  empty.hidden = list.length > 0;
  empty.textContent = state.news.length ? '검색 결과가 없어요.' : '아직 수집된 기사가 없어요.';
}

/* ---------- 상태 ---------- */

function renderStatus() {
  const rows = [];
  Object.values(state.status.contests || {}).forEach((s) => {
    if (!s || !s.name) return;
    rows.push(`<li class="${s.ok ? 'ok' : 'bad'}"><a href="${safeUrl(s.home)}" target="_blank" rel="noopener">${esc(s.name)}</a>
      — ${s.ok ? `${s.count}건 확인` : esc(s.error || '실패')} <small>${fmtDateTime(s.checkedAt)}</small></li>`);
  });
  const other = [['shows', '새 공연(PlayDB)'], ['news', '업계 기사']];
  other.forEach(([key, name]) => {
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
  ['showSearch', 'showRange'].forEach((id) => $(id).addEventListener('input', renderShows));
  $('newsSearch').addEventListener('input', renderNews);
  $('showList').addEventListener('click', (e) => {
    const li = e.target.closest('li[data-id]');
    if (li) openShow(li.dataset.id);
  });
  $('showList').addEventListener('keydown', (e) => {
    const li = e.target.closest('li[data-id]');
    if (li && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openShow(li.dataset.id); }
  });
  $('showDialog').addEventListener('click', (e) => {
    if (e.target === $('showDialog')) $('showDialog').close();
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

  const [contests, shows, news, status] = await Promise.all([
    loadJSON('contests.json', { items: [] }),
    loadJSON('shows.json', { items: [] }),
    loadJSON('news.json', { items: [] }),
    loadJSON('status.json', {}),
  ]);
  state.contests = contests.items || [];
  state.shows = shows.items || [];
  state.news = news.items || [];
  state.status = status || {};

  renderSourceChips();
  renderContests();
  renderShows();
  renderNews();
  renderStatus();
}

init();
