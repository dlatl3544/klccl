/* KLCCL 책 모양 성경 읽기: 펼친 책 두 쪽, 양옆 책 탭, 쪽 넘김, 글자 크기, 표지 색, 책갈피 */
(function () {
  const $ = s => document.querySelector(s);
  const root = document.body.dataset.root || '';
  const BOOKS = window.KLCCL_BOOKLIST;          // [{code, abbr, name, ch, t}]
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d } catch (e) { return d } },
    set(k, v) { try { localStorage.setItem(k, v) } catch (e) {} }
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cache = {};
  let code = 'gen', chap = 1, spread = 0, spreads = 1, fs = +store.get('bfs', '19');

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

  async function load(c) {
    if (cache[c]) return cache[c];
    const r = await fetch(`${root}data/krv/${c}.json`);
    cache[c] = await r.json();
    return cache[c];
  }

  // 장 본문을 책 두 쪽에 흘려 넣고, 넘칠 만큼 쪽을 나눈다
  async function show(c, ch, toEnd) {
    const b = BOOKS.find(x => x.code === c) || BOOKS[0];
    code = b.code; chap = Math.max(1, Math.min(ch, b.ch));
    const data = await load(code);
    const vs = data.chapters[chap - 1] || [];
    const mark = store.get('bmark', '');
    $('#flow').innerHTML =
      (chap === 1 ? `<h2 class="bk-title">${esc(b.name)}</h2>` : '') +
      `<h3 class="ch-title">제 ${chap} 장</h3>` +
      vs.map((t, i) => `<p class="bv${mark === `${code}/${chap}/${i + 1}` ? ' marked' : ''}" data-v="${i + 1}"><span class="n">${chap}:${i + 1}</span> ${esc(t)}</p>`).join('');
    $('#runhead').textContent = `개역한글판 · ${b.name} ${chap}장`;
    $('#bkSel').value = code;
    $('#chSel').innerHTML = Array.from({ length: b.ch }, (_, i) => `<option value="${i + 1}">${i + 1}장</option>`).join('');
    $('#chSel').value = chap;
    document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('on', x.dataset.code === code));
    history.replaceState(null, '', `#${code}/${chap}`);
    store.set('blast', `${code}/${chap}`);
    layout(toEnd);
  }

  function pageW() { return $('#viewport').clientWidth; }

  function layout(toEnd) {
    const flow = $('#flow'), vp = $('#viewport');
    const two = innerWidth > 820;
    const gap = two ? 64 : 0;
    const colW = two ? (vp.clientWidth - gap) / 2 : vp.clientWidth;
    flow.style.columnWidth = colW + 'px';
    flow.style.columnGap = gap + 'px';
    flow.style.height = vp.clientHeight + 'px';
    flow.style.fontSize = fs + 'px';
    flow.style.transform = 'none';
    const total = Math.max(1, Math.round((flow.scrollWidth + gap) / (colW + gap)));
    spreads = Math.max(1, Math.ceil(total / (two ? 2 : 1)));
    spread = toEnd ? spreads - 1 : 0;
    move();
  }

  function move() {
    const vp = $('#viewport'), two = innerWidth > 820, gap = two ? 64 : 0;
    $('#flow').style.transform = `translateX(${-spread * (vp.clientWidth + gap)}px)`;
    $('#pageno').textContent = `${spread + 1} / ${spreads}`;
  }

  function next() {
    if (spread < spreads - 1) { spread++; move(); return }
    const b = BOOKS.find(x => x.code === code), i = BOOKS.indexOf(b);
    if (chap < b.ch) show(code, chap + 1);
    else if (i < BOOKS.length - 1) show(BOOKS[i + 1].code, 1);
  }
  function prev() {
    if (spread > 0) { spread--; move(); return }
    const b = BOOKS.find(x => x.code === code), i = BOOKS.indexOf(b);
    if (chap > 1) show(code, chap - 1, true);
    else if (i > 0) show(BOOKS[i - 1].code, BOOKS[i - 1].ch, true);
  }

  // 표지 색
  const COVERS = { navy: '남색 가죽', brown: '갈색 가죽', green: '녹색 천', wine: '포도주색', black: '검정' };
  function cover(c) {
    document.querySelector('.bookwrap').dataset.cover = c; store.set('bcover', c);
    $('#coverSel').value = c;
  }

  function init() {
    tabs(); selects();
    $('#coverSel').innerHTML = Object.entries(COVERS).map(([k, v]) => `<option value="${k}">표지: ${v}</option>`).join('');
    cover(store.get('bcover', 'navy'));
    document.addEventListener('click', e => {
      const t = e.target.closest('.tabs button'); if (t) show(t.dataset.code, 1);
      const v = e.target.closest('#flow p.bv');
      if (v) {   // 절을 누르면 책갈피(한 곳만 기억)
        const k = `${code}/${chap}/${v.dataset.v}`;
        const on = store.get('bmark', '') !== k;
        store.set('bmark', on ? k : '');
        document.querySelectorAll('#flow p.bv').forEach(p => p.classList.toggle('marked', on && p === v));
        const tt = $('#toast'); if (tt) { tt.textContent = on ? '책갈피를 꽂았습니다' : '책갈피를 뺐습니다'; tt.classList.add('show'); setTimeout(() => tt.classList.remove('show'), 1400) }
      }
    });
    $('#nextBtn').onclick = next; $('#prevBtn').onclick = prev;
    $('#bkSel').onchange = e => show(e.target.value, 1);
    $('#chSel').onchange = e => show(code, +e.target.value);
    $('#coverSel').onchange = e => cover(e.target.value);
    $('#fsMinus').onclick = () => { fs = Math.max(14, fs - 1); store.set('bfs', fs); layout() };
    $('#fsPlus').onclick = () => { fs = Math.min(28, fs + 1); store.set('bfs', fs); layout() };
    $('#markBtn').onclick = () => {
      const m = store.get('bmark', '');
      if (!m) { const tt = $('#toast'); tt.textContent = '절을 누르면 책갈피가 꽂힙니다'; tt.classList.add('show'); setTimeout(() => tt.classList.remove('show'), 1600); return }
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
    const h = (location.hash.slice(1) || store.get('blast', 'gen/1')).split('/');
    show(h[0], +h[1] || 1);
  }
  init();
})();
