/* KLCCL 책 모양 성경 읽기: 펼친 책 두 쪽, 양옆 책 탭, 쪽 넘김, 글자 크기, 표지 색, 책갈피 */
(function () {
  const $ = s => document.querySelector(s);
  const root = document.body.dataset.root || '';
  // 성경 자료(data/)는 한국어판과 영문판이 함께 쓰므로 공용 뿌리(data-assets)에서 불러온다
  const assets = document.body.dataset.assets ?? root;
  const EN = document.documentElement.lang === 'en';
  const T = (ko, en) => EN ? en : ko;
  const BOOKS = window.KLCCL_BOOKLIST;          // [{code, abbr, name, ch, t}]
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d } catch (e) { return d } },
    set(k, v) { try { localStorage.setItem(k, v) } catch (e) {} }
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cache = {};
  const VERS = window.KLCCL_VERSIONS || [{ id: 'krv', name: '개역한글판' }];
  let code = 'gen', chap = 1, spread = 0, spreads = 1, fs = +store.get('bfs', '19');
  let ver = store.get('bver', 'krv'), par = store.get('bpar', window.KLCCL_DEFAULT_PAR || '');
  if (!VERS.find(v => v.id === ver)) ver = 'krv';
  // KJV 의 [ ] 는 번역자가 보충한 말: 기울임으로 표시
  const fmt = t => esc(t).replace(/\[([^\]]+)\]/g, '<i>$1</i>');

  // 양옆 책 탭: 왼쪽 구약, 오른쪽 신약
  function tabs() {
    const mk = t => BOOKS.filter(b => b.t === t).map(b =>
      `<button data-code="${b.code}" title="${esc(b.name)}">${esc(b.abbr)}</button>`).join('');
    $('#tabsOT').innerHTML = mk('구약');
    $('#tabsNT').innerHTML = mk('신약');
  }

  function selects() {
    $('#bkSel').innerHTML = BOOKS.map(b => `<option value="${b.code}">${esc(b.name)}</option>`).join('');
  }

  async function load(v, c) {
    const k = v + '/' + c;
    if (cache[k]) return cache[k];
    const r = await fetch(`${assets}data/${v}/${c}.json`);
    cache[k] = await r.json();
    return cache[k];
  }

  // 장 본문을 책 두 쪽에 흘려 넣고, 넘칠 만큼 쪽을 나눈다
  async function show(c, ch, toEnd, dir) {
    const b = BOOKS.find(x => x.code === c) || BOOKS[0];
    code = b.code; chap = Math.max(1, Math.min(ch, b.ch));
    const vs = ((await load(ver, code)).chapters[chap - 1]) || [];
    // 나란히 보기: 절 번호로 맞대어 아래에 작게 붙인다
    const pv = {};
    if (par && par !== ver) ((await load(par, code)).chapters[chap - 1] || []).forEach(([n, t]) => pv[n] = t);
    const mark = store.get('bmark', '');
    const en = (VERS.find(x => x.id === ver) || {}).lang === 'en';
    $('#flow').className = en ? 'en' : '';
    $('#flow').innerHTML =
      (chap === 1 ? `<h2 class="bk-title">${esc(b.name)}</h2>` : '') +
      `<h3 class="ch-title">${T(`제 ${chap} 장`, `Chapter ${chap}`)}</h3>` +
      vs.map(([n, t]) => `<p class="bv${mark === `${code}/${chap}/${n}` ? ' marked' : ''}" data-v="${n}"><span class="n">${chap}:${n}</span> ${fmt(t)}` +
        (par && par !== ver ? `<span class="pv">${pv[n] !== undefined ? fmt(pv[n]) : '—'}</span>` : '') + '</p>').join('');
    const vn = (VERS.find(x => x.id === ver) || {}).name || '';
    const pn = par && par !== ver ? ' · ' + ((VERS.find(x => x.id === par) || {}).name || '') : '';
    $('#runhead').textContent = `${vn}${pn} · ${b.name} ${chap}${T('장', '')}`;
    $('#bkSel').value = code;
    $('#chSel').innerHTML = Array.from({ length: b.ch }, (_, i) => `<option value="${i + 1}">${T(`${i + 1}장`, `Chapter ${i + 1}`)}</option>`).join('');
    $('#chSel').value = chap;
    document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('on', x.dataset.code === code));
    history.replaceState(null, '', `#${code}/${chap}`);
    store.set('blast', `${code}/${chap}`);
    layout(toEnd, dir);
  }

  function pageW() { return $('#viewport').clientWidth; }

  function layout(toEnd, dir) {
    const flow = $('#flow'), vp = $('#viewport');
    const two = innerWidth > 820;
    const gap = two ? 64 : 0;
    const colW = two ? (vp.clientWidth - gap) / 2 : vp.clientWidth;
    flow.style.transition = 'none';          // 새 장을 깔 때는 움직임 없이
    flow.style.columnWidth = colW + 'px';
    flow.style.columnGap = gap + 'px';
    flow.style.height = vp.clientHeight + 'px';
    flow.style.fontSize = fs + 'px';
    flow.style.transform = 'none';
    const total = Math.max(1, Math.round((flow.scrollWidth + gap) / (colW + gap)));
    spreads = Math.max(1, Math.ceil(total / (two ? 2 : 1)));
    spread = toEnd ? spreads - 1 : 0;
    const x = -spread * (vp.clientWidth + gap);
    if (dir) {
      // 장이 바뀔 때: 앞으로 가면 오른쪽에서 들어와 왼쪽으로, 뒤로 가면 왼쪽에서 들어온다
      const off = (dir === 'next' ? 1 : -1) * (vp.clientWidth + gap);
      flow.style.transform = `translateX(${x + off}px)`;
      flow.style.opacity = '0.2';
      void flow.offsetWidth;                  // 시작 위치를 먼저 그리게 한다
      flow.style.transition = 'transform .35s ease, opacity .35s ease';
      flow.style.transform = `translateX(${x}px)`;
      flow.style.opacity = '1';
      $('#pageno').textContent = `${spread + 1} / ${spreads}`;
    } else {
      flow.style.transform = `translateX(${x}px)`;
      void flow.offsetWidth;
      flow.style.transition = 'transform .35s ease, opacity .35s ease';
      $('#pageno').textContent = `${spread + 1} / ${spreads}`;
    }
  }

  function move() {
    const vp = $('#viewport'), two = innerWidth > 820, gap = two ? 64 : 0;
    $('#flow').style.transform = `translateX(${-spread * (vp.clientWidth + gap)}px)`;
    $('#pageno').textContent = `${spread + 1} / ${spreads}`;
  }

  function next() {
    if (spread < spreads - 1) { spread++; move(); return }
    const b = BOOKS.find(x => x.code === code), i = BOOKS.indexOf(b);
    if (chap < b.ch) show(code, chap + 1, false, 'next');
    else if (i < BOOKS.length - 1) show(BOOKS[i + 1].code, 1, false, 'next');
  }
  function prev() {
    if (spread > 0) { spread--; move(); return }
    const b = BOOKS.find(x => x.code === code), i = BOOKS.indexOf(b);
    if (chap > 1) show(code, chap - 1, true, 'prev');
    else if (i > 0) show(BOOKS[i - 1].code, BOOKS[i - 1].ch, true, 'prev');
  }

  // 표지 색
  const COVERS = EN ? { navy: 'navy leather', brown: 'brown leather', green: 'green cloth', wine: 'wine red', black: 'black' }
                     : { navy: '남색 가죽', brown: '갈색 가죽', green: '녹색 천', wine: '포도주색', black: '검정' };
  function cover(c) {
    document.querySelector('.bookwrap').dataset.cover = c; store.set('bcover', c);
    $('#coverSel').value = c;
  }

  function init() {
    tabs(); selects();
    $('#coverSel').innerHTML = Object.entries(COVERS).map(([k, v]) => `<option value="${k}">${T('표지', 'Cover')}: ${v}</option>`).join('');
    cover(store.get('bcover', 'navy'));
    document.addEventListener('click', e => {
      const t = e.target.closest('.tabs button'); if (t) show(t.dataset.code, 1);
      const v = e.target.closest('#flow p.bv');
      if (v) {   // 절을 누르면 책갈피(한 곳만 기억)
        const k = `${code}/${chap}/${v.dataset.v}`;
        const on = store.get('bmark', '') !== k;
        store.set('bmark', on ? k : '');
        document.querySelectorAll('#flow p.bv').forEach(p => p.classList.toggle('marked', on && p === v));
        const tt = $('#toast'); if (tt) { tt.textContent = on ? T('책갈피를 꽂았습니다', 'Bookmark set') : T('책갈피를 뺐습니다', 'Bookmark removed'); tt.classList.add('show'); setTimeout(() => tt.classList.remove('show'), 1400) }
      }
    });
    $('#nextBtn').onclick = next; $('#prevBtn').onclick = prev;
    $('#bkSel').onchange = e => show(e.target.value, 1);
    $('#chSel').onchange = e => show(code, +e.target.value);
    $('#coverSel').onchange = e => cover(e.target.value);
    $('#verSel').value = ver; $('#parSel').value = par;
    $('#verSel').onchange = e => { ver = e.target.value; store.set('bver', ver); show(code, chap) };
    $('#parSel').onchange = e => { par = e.target.value; store.set('bpar', par); show(code, chap) };
    $('#fsMinus').onclick = () => { fs = Math.max(14, fs - 1); store.set('bfs', fs); layout() };
    $('#fsPlus').onclick = () => { fs = Math.min(28, fs + 1); store.set('bfs', fs); layout() };
    $('#markBtn').onclick = () => {
      const m = store.get('bmark', '');
      if (!m) { const tt = $('#toast'); tt.textContent = T('절을 누르면 책갈피가 꽂힙니다', 'Click a verse to set a bookmark'); tt.classList.add('show'); setTimeout(() => tt.classList.remove('show'), 1600); return }
      const [c, ch] = m.split('/'); show(c, +ch);
    };
    document.addEventListener('keydown', e => {
      if (e.target.closest('select,input')) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') next();
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') prev();
    });
    // 손가락으로 넘기기
    let sx = null;
    $('#viewport').addEventListener('touchstart', e => { sx = e.touches[0].clientX }, { passive: true });
    $('#viewport').addEventListener('touchend', e => {
      if (sx === null) return; const dx = e.changedTouches[0].clientX - sx; sx = null;
      if (Math.abs(dx) > 50) (dx < 0 ? next : prev)();
    });
    let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => layout(), 150) });
    addEventListener('hashchange', () => {
      const [c, ch] = location.hash.slice(1).split('/');
      if (c && (c !== code || +ch !== chap)) show(c, +ch || 1);
    });
    const h = (location.hash.slice(1) || store.get('blast', 'gen/1')).split('/');
    show(h[0], +h[1] || 1);
  }
  init();
})();
