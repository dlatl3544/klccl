/* KCCL 공통 스크립트: 읽기 화면의 보기 전환, 글자 크기, 찾기, 인용 복사, 각주 팝업 */
(function () {
  const $ = s => document.querySelector(s);
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d } catch (e) { return d } },
    set(k, v) { try { localStorage.setItem(k, v) } catch (e) {} }
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // 화면 언어: 영문판(/en/) 쪽은 <html lang="en">
  const EN = document.documentElement.lang === 'en';
  const T = (ko, en) => EN ? en : ko;

  // 색 모드: 라이트 / 다크 / 리딩. 고른 적이 없으면 기기 설정(라이트 또는 다크)을 따른다
  function curTheme() {
    const t = store.get('theme', '');
    if (t) return t;
    return matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    document.querySelectorAll('[data-theme-set]').forEach(b => b.classList.toggle('on', b.dataset.themeSet === t));
  }
  applyTheme(curTheme());
  document.querySelectorAll('[data-theme-set]').forEach(b => b.onclick = () => { store.set('theme', b.dataset.themeSet); applyTheme(b.dataset.themeSet) });

  // 모바일 서가 열기
  const menu = $('#menuBtn');
  if (menu) menu.onclick = () => $('#shelf').classList.toggle('open');

  // 서가: 갈래·시대·원어·상태 거르기
  const works = $('#works');
  if (works) {
    const sel = {};
    function runFilter() {
      let n = 0;
      works.querySelectorAll('.wk').forEach(c => {
        const ok = Object.entries(sel).every(([k, v]) => !v || c.dataset[k] === v);
        c.hidden = !ok; if (ok) n++;
      });
      $('#count').textContent = T(`${n}종`, `${n} work${n === 1 ? '' : 's'}`);
      $('#empty').hidden = n > 0;
    }
    document.querySelectorAll('.chips').forEach(g => g.addEventListener('click', ev => {
      const b = ev.target.closest('button'); if (!b) return;
      g.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
      sel[g.dataset.filter] = b.dataset.v; runFilter();
    }));
    runFilter();
  }

  // 찾기: 제목·구절 색인에서 고르고, "욥 16:2" 같은 구절은 성경 장으로 바로 보낸다
  const sq = $('#sq');
  if (sq && window.KLCCL_SEARCH) {
    const root = document.body.dataset.root || '';
    const box = $('#sr');
    function go() {
      const q = sq.value.trim();
      if (!q) { box.innerHTML = ''; return }
      let html = '';
      // 책 이름 + 장(:절). 영문판은 'Job 16:2', '1 Samuel 3', 'psalms 23' 같은 영어 이름도 받는다
      const m = q.match(/^([가-힣A-Za-z0-9 ]+?)\.?\s*(\d+)(?::(\d+))?$/);
      const B = window.KLCCL_BOOKS || {};
      const bk = m && (B[m[1]] || B[m[1].toLowerCase()] || B[m[1].toLowerCase().replace(/\s+/g, '')]);
      if (bk) {
        const u = `${root}bible/${bk}/${m[2]}.html${m[3] ? '#v' + m[3] : ''}`;
        html += `<a class="res" href="${u}"><b>${esc(q)}</b><span>${T('성경 본문으로 가기 (개역한글판)', 'Go to the Bible text (Korean Revised Version)')}</span></a>`;
      }
      const ws = q.toLowerCase().split(/\s+/);
      const hit = window.KLCCL_SEARCH.filter(x => ws.every(w => (x.t + ' ' + x.s + ' ' + (x.x || '')).toLowerCase().includes(w))).slice(0, 50);
      html += hit.map(x => `<a class="res" href="${root}${x.u}"><b>${esc(x.t)}</b><span>${esc(x.s)}</span></a>`).join('');
      box.innerHTML = html || `<p class="mini">${T('찾는 것이 없습니다.', 'Nothing found.')}</p>`;
    }
    sq.addEventListener('input', go);
    sq.addEventListener('keydown', ev => { if (ev.key === 'Enter') { const a = box.querySelector('a'); if (a) location.href = a.href } });
  }

  const reader = $('#reader');
  if (!reader) return;   // 읽기 화면이 아니면 여기서 끝

  let mode = store.get('mode', 'both'), fs = +store.get('fs', '17');
  function apply() {
    reader.className = 'reader mode-' + mode;
    document.querySelectorAll('[data-mode]').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
    document.documentElement.style.setProperty('--fs', fs + 'px');
  }
  apply();

  function toast(t) {
    const el = $('#toast'); el.textContent = t; el.classList.add('show');
    clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('show'), 1600);
  }
  async function copy(t, msg) {
    try { await navigator.clipboard.writeText(t); toast(msg) } catch (e) { toast(T('복사가 허용되지 않았습니다', 'Copying was not allowed')) }
  }

  // 이 설교 안에서 찾기
  function doSearch() {
    const q = $('#q').value.trim();
    reader.querySelectorAll('mark').forEach(m => m.replaceWith(m.textContent));
    reader.querySelectorAll('p,.verse div').forEach(p => p.normalize());
    if (!q) { $('#hits').textContent = ''; return }
    let n = 0;
    const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    reader.querySelectorAll('.row p, .verse div').forEach(p => {
      const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT), nodes = [];
      while (w.nextNode()) nodes.push(w.currentNode);
      nodes.forEach(t => {
        if (!re.test(t.data)) return; re.lastIndex = 0;
        const span = document.createElement('span');
        span.innerHTML = esc(t.data).replace(re, m => { n++; return `<mark>${m}</mark>` });
        t.replaceWith(...span.childNodes);
      });
    });
    $('#hits').textContent = n ? T(`${n}곳`, `${n} found`) : T('찾는 말이 없습니다', 'Not found');
    const first = reader.querySelector('mark'); if (first) first.scrollIntoView({ block: 'center' });
  }
  $('#q').addEventListener('input', () => { clearTimeout(doSearch._t); doSearch._t = setTimeout(doSearch, 250) });

  const info = reader.dataset;   // data-cite-title, data-no, data-vol
  // 미리보기처럼 스크립트가 다시 실행될 때 처리기가 겹치지 않게 앞의 것을 뗀다
  if (window.__kcclClick) document.removeEventListener('click', window.__kcclClick);
  window.__kcclClick = e => {
    const pop = $('#pop');
    const fn = e.target.closest('sup.fn');
    if (fn) {
      const li = document.getElementById('fn' + fn.dataset.n);
      pop.innerHTML = `<b style="color:var(--gold)">${T('각주', 'Note')} ${fn.dataset.n}</b><br>${li ? li.innerHTML : ''}`;
      const r = fn.getBoundingClientRect(); pop.style.display = 'block';
      pop.style.left = Math.max(8, Math.min(r.left, innerWidth - 360)) + 'px'; pop.style.top = (r.bottom + 8) + 'px';
      return;
    }
    pop.style.display = 'none';
    const c = e.target.closest('[data-cite]');
    if (c) {
      const label = info.label || `제${info.no}${info.unit}`, place = `${info.citePre || ('CO ' + info.vol + ':')}${c.dataset.cite}${info.citePost || ''}`;
      copy(EN ? `${info.author}, ${info.citeTitle}, ${label}, ${place}. ${info.site} Korean edition (CC0).`
              : `${info.author}, 「${info.citeTitle}」 ${label}, ${place}. ${info.site} 한국어판(CC0).`, T('인용 표기를 복사했습니다', 'Citation copied'));
    }
    const m = e.target.closest('[data-mode]');
    if (m) { mode = m.dataset.mode; store.set('mode', mode); apply() }
    const f = e.target.closest('[data-fs]');
    if (f) { fs = Math.max(14, Math.min(24, fs + +f.dataset.fs)); store.set('fs', fs); apply() }
  };
  document.addEventListener('click', window.__kcclClick);

  $('#copyText').onclick = () => {
    const parts = [...reader.querySelectorAll('.head .no, .head .sub, .verse .ko, .row .ko p')].map(el => {
      const c = el.cloneNode(true); c.querySelectorAll('sup').forEach(s => s.remove()); return c.textContent.trim();
    });
    copy(parts.join('\n\n') + T(`\n\n— ${info.site} 한국어판, CC0 1.0`, `\n\n— ${info.site} Korean edition, CC0 1.0`), T('이 설교의 한국어 본문을 복사했습니다', 'Copied the Korean text'));
  };
})();
