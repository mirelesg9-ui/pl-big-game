// Big Game front end. Static: reads JSON built by pipeline/build.py.
const app = document.getElementById('app');
const memo = {};
const get = (p) => memo[p] ??= fetch('data/' + p).then(r => r.json());
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sgn = (x, d = 2) => { const t = Math.abs(x).toFixed(d); return +t === 0 ? (0).toFixed(d) : (x > 0 ? '+' : '−') + t; };
const mood = (p) => p >= 0.7 ? 'up' : p <= 0.3 ? 'down' : 'flat';
const fmtDate = (s) => new Date(s + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const BACK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>';

window.addEventListener('hashchange', route);
route();

async function route() {
  const meta = await get('meta.json');
  const [, view, slug] = location.hash.split('/');
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('on',
    a.dataset.tab === (view === 'search' || view === 'p' ? 'search' : view === 'method' ? 'method' : 'home')));
  window.scrollTo(0, 0);
  if (view === 'p' && slug) return player(meta, slug);
  if (view === 'search') return search(meta);
  if (view === 'method') return method(meta);
  return home(meta);
}

// ------------------------------------------------------------------ home
async function home(meta) {
  const league = await get('league.json');
  const att = league.filter(p => p.group === 'attack');
  const neutral = att.filter(p => p.text.startsWith('No clear')).length;
  const share = Math.round(100 * neutral / att.length);
  // attacking roles only: a holding midfielder's tiny xGI can't "step up" much
  const pool = att.filter(p => p.elite_minutes >= 900 && p.base >= 0.25);
  const ups = [...pool].sort((a, b) => b.p_better - a.p_better).slice(0, 5);
  const downs = [...pool].sort((a, b) => a.p_better - b.p_better).slice(0, 5);
  const row = (p) => `<a class="item" href="#/p/${p.slug}"><div class="who"><div class="name">${esc(p.name)}</div>
    <div class="meta">${esc(p.team)} · ${p.pos}</div></div><div class="pill ${mood(p.p_better)}">${Math.round(p.p_better * 100)}%</div></a>`;
  app.innerHTML = `
    <div class="bar"><span class="mark">BIG<i>GAME</i></span><span class="tiny muted">Through ${fmtDate(meta.last_match)}</span></div>
    <div><div class="eyebrow">Premier League · attackers</div>
      <div class="hero" style="margin-top:10px">${share}%</div>
      <p class="soft" style="margin-top:10px">show no clear difference against elite teams once opponent, venue and team are accounted for. Big-game reputations mostly don't survive the numbers.</p></div>
    <a class="search" href="#/search" style="display:flex;align-items:center;color:var(--muted)">Search any player</a>
    <section class="card"><div class="section"><h2>Leaning up vs elite</h2>
      <p class="small muted">Chance each is genuinely better against top teams. Attacking players with 900+ elite minutes.</p></div>
      <div class="list">${ups.map(row).join('')}</div></section>
    <section class="card"><div class="section"><h2>Leaning down vs elite</h2>
      <p class="small muted">Same test, other end.</p></div>
      <div class="list">${downs.map(row).join('')}</div></section>`;
}

// ---------------------------------------------------------------- search
async function search() {
  const players = await get('players.json');
  const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  app.innerHTML = `<div class="title">Search</div>
    <input class="search" id="q" type="search" placeholder="Player name" aria-label="Search players" autocomplete="off">
    <div class="list" id="res"></div>`;
  const q = document.getElementById('q'), res = document.getElementById('res');
  const draw = () => {
    const s = norm(q.value.trim());
    const hits = (s ? players.filter(p => norm(p.name).includes(s)) : players).slice(0, 25);
    res.innerHTML = hits.map(p => `<a class="item" href="#/p/${p.slug}"><div class="who"><div class="name">${esc(p.name)}</div>
      <div class="meta">${esc(p.team)} · ${p.pos}</div></div><span class="tiny muted">${p.minutes.toLocaleString()} min</span></a>`).join('')
      || '<p class="muted">No players found.</p>';
  };
  q.addEventListener('input', draw); draw();
  if (matchMedia('(hover: hover)').matches) q.focus();
}

// ---------------------------------------------------------------- method
async function method(meta) {
  const rel = Object.entries(meta.reliability).map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td>${v.matches_to_0_7 ? v.matches_to_0_7 + ' matches' : 'Not yet'}</td></tr>`).join('');
  const val = Object.entries(meta.validation).map(([k, v]) =>
    `<tr><td>${{ attack: 'Attackers', defence: 'Defenders', keeper: 'Keepers' }[k]}</td><td>${v.repeatability_r == null ? 'Too little data' : 'r = ' + v.repeatability_r}</td></tr>`).join('');
  const src = meta.sources || {};
  const list = (a) => a && a.length ? a.join(', ') : 'not available yet';
  app.innerHTML = `<div class="title">How it works</div>
    <section class="card"><p class="soft">Every match, each player gets an <b>expected</b> output based on the opponent's strength, home or away, his team's strength and his own level that season. The big-game score is the chance he beats that expectation more against elite teams than against average ones. Small samples are pulled toward "no difference" until the evidence piles up.</p></section>
    <section class="card"><div class="section"><h2>Does big-game ability repeat?</h2>
      <p class="small muted">Early seasons vs later seasons, same players. 0.3+ would suggest a real trait.</p></div>
      <table>${val}</table></section>
    <section class="card"><div class="section"><h2>When does a stat mean something?</h2>
      <p class="small muted">Matches per half before split-half r reaches 0.7, within position.</p></div>
      <table>${rel}</table></section>
    <section class="card"><div class="section"><h2>Data</h2></div>
      <p class="small soft">FPL match data (Opta), ${meta.seasons[0]} to ${meta.seasons.at(-1)}. Team strength blends closing betting odds (football-data.co.uk: ${list(src.odds)}) with xG form. Penalties removed using ESPN goal data (${list(src.penalties)}). Built ${esc(meta.built)}.</p>
      <p class="small muted">Premier League only. Measures on-ball output and on-pitch results, not pressing or off-ball runs. Defender actions are tracked from 2025/26.</p></section>`;
}

// ---------------------------------------------------------------- player
async function player(meta, slug) {
  const p = await get(`p/${slug}.json`);
  const st = { range: 'All', filter: 'All' };
  const v = p.verdict;
  const pb = v ? v.p_better : 0.5;
  const m = mood(pb);
  const word = !v ? 'Not enough data' : v.text.startsWith('No clear') ? 'Neutral'
    : p.group === 'defence' ? (pb >= 0.5 ? 'Busier' : 'Quieter') : (pb >= 0.5 ? 'Steps up' : 'Fades');
  const val = meta.validation[p.group];

  const render = () => {
    app.innerHTML = `
      <div class="bar"><button class="back" id="back">${BACK}Back</button></div>
      <div><h1 class="title">${esc(p.name)}</h1><div class="sub">${p.teams.map(esc).join(' → ')} · ${p.position}</div></div>
      ${gauge(pb, m, word)}
      <p class="small muted" style="text-align:center;margin-top:-10px">Chance he's genuinely ${p.group === 'defence' ? 'busier' : 'better'} vs elite teams</p>
      ${v ? `<div class="stats">
        <div class="stat"><span class="k">Effect</span><span class="v ${m}">${sgn(v.delta)}</span><span class="tiny muted">${esc(p.short)}</span></div>
        <div class="stat"><span class="k">Elite games</span><span class="v">${v.elite_matches}</span><span class="tiny muted">${v.elite_minutes.toLocaleString()} min</span></div>
        <div class="stat"><span class="k">Confidence</span><span class="v">${v.confidence}</span><span class="tiny muted">±${((v.hi - v.lo) / 2).toFixed(2)}</span></div></div>` : ''}
      ${val && !val.trait_supported ? `<p class="tiny muted">League-wide this hasn't repeated season to season yet, so it describes what happened rather than a fixed trait.</p>` : ''}
      ${trend(p, st)}
      ${tiers(p)}
      ${system(p)}
      ${matches(p, st)}`;
    document.getElementById('back').onclick = () => history.length > 1 ? history.back() : (location.hash = '#/');
    app.querySelectorAll('[data-range]').forEach(b => b.onclick = () => { st.range = b.dataset.range; render(); });
    app.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { st.filter = b.dataset.f; render(); });
    scrub();
  };
  render();
}

function gauge(p, m, word) {
  const R = 96, C = 2 * Math.PI * R, arc = 0.75 * C;
  const color = { up: 'var(--up)', down: 'var(--down)', flat: 'var(--text)' }[m];
  return `<div class="gauge" role="img" aria-label="${Math.round(p * 100)} percent, ${word}">
    <svg viewBox="0 0 240 220" aria-hidden="true"><g transform="rotate(135 120 120)">
      <circle cx="120" cy="120" r="${R}" fill="none" stroke="#1F1F23" stroke-width="14" stroke-linecap="round" stroke-dasharray="${arc} ${C}"/>
      <circle cx="120" cy="120" r="${R}" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round" stroke-dasharray="${Math.max(0.001, arc * p)} ${C}"/></g></svg>
    <div class="center"><div class="val">${Math.round(p * 100)}<small>%</small></div><div class="lab ${m}">${word}</div></div></div>`;
}

// One match's value for the player's headline metric.
const metricOf = (p) => p.group === 'attack' ? (x => x.npxg + x.xa) : p.group === 'defence' ? (x => x.da) : (x => x.gp);

function series(p, range) {
  const f = metricOf(p);
  const rows = p.matches.filter(x => x.minutes >= 30 && f(x) != null).slice().reverse();
  const end = rows.length ? new Date(rows.at(-1).date) : new Date();
  const cut = range === 'All' ? null : new Date(end - (range === '1Y' ? 365 : 730) * 864e5);
  const pts = [];
  for (let i = Math.min(7, Math.max(0, rows.length - 3)); i < rows.length; i++) {
    const win = rows.slice(Math.max(0, i - 7), i + 1);
    const mins = win.reduce((a, x) => a + x.minutes, 0);
    const val = win.reduce((a, x) => a + f(x), 0) / mins * 90;
    if (!cut || new Date(rows[i].date) >= cut) pts.push({ d: rows[i].date, v: val, team: rows[i].team });
  }
  return pts;
}

let trendState = null;

function trend(p, st) {
  const pts = series(p, st.range);
  trendState = null;
  if (pts.length < 3) return '';
  const W = 440, H = 180, lo = Math.min(...pts.map(q => q.v)), hi = Math.max(...pts.map(q => q.v));
  const pad = (hi - lo) * 0.15 || 0.1;
  const x = i => i / (pts.length - 1) * W, y = v => H - 10 - (v - lo + pad) / (hi - lo + 2 * pad) * (H - 20);
  const path = pts.map((q, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(q.v).toFixed(1)}`).join('');
  const first = pts[0].v, last = pts.at(-1).v;
  const col = last >= first ? 'var(--up)' : 'var(--down)';
  const marks = pts.map((q, i) => i && q.team !== pts[i - 1].team
    ? `<line x1="${x(i)}" x2="${x(i)}" y1="0" y2="${H}" stroke="#3A3A40" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>` : '').join('');
  const moves = pts.map((q, i) => i && q.team !== pts[i - 1].team
    ? `<span style="position:absolute;top:0;left:calc(${100 * i / (pts.length - 1)}% + 6px)" class="tiny muted">→ ${esc(q.team)}</span>` : '').join('');
  trendState = { pts, x };
  return `<section class="card">
    <div><div class="eyebrow">Form · ${esc(p.short)} · 8-game rolling</div>
      <div style="display:flex;align-items:baseline;gap:10px;margin-top:8px"><span class="hero" id="tv" style="font-size:60px">${last.toFixed(2)}</span>
      <span class="num ${last >= first ? 'up' : 'down'}" id="td" style="font-size:22px">${sgn(last - first)}</span></div>
      <div class="tiny muted" id="tdate">${fmtDate(pts.at(-1).d)} · ${esc(pts.at(-1).team)}</div></div>
    <div class="chart" id="chart">${moves}<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Rolling form line chart">
      ${marks}<path d="${path}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      <line id="cur" x1="0" x2="0" y1="0" y2="${H}" stroke="#F2F2F4" stroke-width="1" vector-effect="non-scaling-stroke" visibility="hidden"/></svg></div>
    <div class="seg" role="group" aria-label="Time range">${['1Y', '2Y', 'All'].map(r => `<button data-range="${r}" class="${st.range === r ? 'on' : ''}">${r}</button>`).join('')}</div>
  </section>`;
}

function scrub() {
  const el = document.getElementById('chart');
  if (!el || !trendState) return;
  const { pts, x } = trendState;
  const tv = document.getElementById('tv'), td = document.getElementById('td');
  const tdate = document.getElementById('tdate'), cur = document.getElementById('cur');
  const show = (i, on) => {
    const q = pts[i];
    tv.textContent = q.v.toFixed(2);
    td.textContent = sgn(q.v - pts[0].v);
    td.className = 'num ' + (q.v >= pts[0].v ? 'up' : 'down');
    tdate.textContent = fmtDate(q.d) + ' · ' + q.team;
    cur.setAttribute('x1', x(i)); cur.setAttribute('x2', x(i));
    cur.setAttribute('visibility', on ? 'visible' : 'hidden');
  };
  const at = (e) => {
    const r = el.getBoundingClientRect();
    show(Math.round(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (pts.length - 1)), true);
  };
  el.addEventListener('pointermove', at);
  el.addEventListener('pointerdown', at);
  el.addEventListener('pointerleave', () => show(pts.length - 1, false));
  el.addEventListener('pointerup', () => show(pts.length - 1, false));
}

function tiers(p) {
  const rows = p.tiers.filter(t => t.matches);
  if (!rows.length) return '';
  const max = Math.max(...rows.flatMap(t => [Math.abs(t.actual), Math.abs(t.expected)])) * 1.15 || 1;
  const higher = p.better === 'higher';
  return `<section class="card"><div class="section"><h2>vs opponent strength</h2>
    <p class="small muted">${esc(p.short)}, actual vs expected for those exact games.</p></div>
    <div>${rows.map(t => {
      const diff = t.actual - t.expected;
      const cls = Math.abs(diff) < 0.02 ? 'flat' : (diff > 0) === higher ? 'up' : 'down';
      return `<div class="tier"><div><div class="t">${t.tier}</div><div class="tiny muted">${t.matches} games</div>
        <div class="track" aria-hidden="true"><i style="width:${Math.max(0, 100 * t.actual / max)}%"></i><b style="left:${Math.max(0, 100 * t.expected / max)}%"></b></div></div>
        <div class="num" style="font-size:24px">${t.actual.toFixed(2)}</div>
        <div class="pill ${cls}" style="min-width:64px;font-size:17px">${sgn(diff)}</div></div>`;
    }).join('')}</div>
    <p class="tiny muted">Bar = actual, tick = expected. Tiers come from match-day strength (betting odds + xG form).</p></section>`;
}

function system(p) {
  if (!p.system.length) return '';
  return `<div class="section"><h2>Player vs system</h2><p class="small muted">Rising raw numbers with a falling share usually means a better team, not a better player.</p></div>
    <div class="hscroll">${p.system.map(s => `<div class="stint"><div><div class="num">${esc(s.team)}</div><div class="tiny muted">${s.season} · ${s.minutes.toLocaleString()} min</div></div>
      <div class="kv"><span>npxGI/90</span><span class="num">${s.xgi90.toFixed(2)}</span></div>
      <div class="kv"><span>Team share</span><span class="num">${s.team_share == null ? '–' : Math.round(s.team_share * 100) + '%'}</span></div>
      <div class="kv"><span>xGC on / off</span><span class="num">${s.xgc90_on.toFixed(2)} / ${s.xgc90_off == null ? '–' : s.xgc90_off.toFixed(2)}</span></div></div>`).join('')}</div>`;
}

function matches(p, st) {
  const keep = { All: () => true, Elite: x => x.tier === 'Elite', Derbies: x => x.derby, Stakes: x => x.stakes }[st.filter];
  const f = metricOf(p);
  const rows = p.matches.filter(x => x.minutes > 0 && keep(x)).slice(0, 60);
  const right = (x) => p.group === 'attack'
    ? `<div class="num">${x.goals}G ${x.assists}A</div><div class="tiny muted">npxG ${x.npxg.toFixed(2)} · xA ${x.xa.toFixed(2)}${x.pens ? ' · pen' : ''}</div>`
    : `<div class="num">${f(x) == null ? '–' : (p.group === 'keeper' ? sgn(f(x)) : f(x))}</div><div class="tiny muted">${esc(p.short)}</div>`;
  return `<div class="section"><h2>Matches</h2></div>
    <div class="seg" role="group" aria-label="Filter matches">${['All', 'Elite', 'Derbies', 'Stakes'].map(k => `<button data-f="${k}" class="${st.filter === k ? 'on' : ''}">${k}</button>`).join('')}</div>
    <div>${rows.map(x => `<div class="match"><div><div style="font-weight:600"><span class="dot ${x.tier}" aria-hidden="true"></span>${x.home ? 'vs' : '@'} ${esc(x.opp)}${x.derby ? '<span class="tag">Derby</span>' : ''}</div>
      <div class="tiny muted" style="margin-top:3px">${fmtDate(x.date)} · ${x.score} · ${x.minutes}'${x.started === false ? ' sub' : ''} · ${x.tier}</div></div>
      <div style="text-align:right">${right(x)}</div></div>`).join('') || '<p class="muted small">No matches.</p>'}</div>
    <p class="tiny muted">Latest 60 shown. Rates use appearances of 30+ minutes.</p>`;
}
