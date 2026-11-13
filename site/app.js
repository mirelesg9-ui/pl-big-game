// Big Game: static front end. Reads JSON built by pipeline/build.py.
const app = document.getElementById('app');
const cache = {};
const get = async (p) => cache[p] ??= fetch('data/' + p).then(r => r.json());
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const f2 = (x) => { if (x == null) return '–'; const t = Math.abs(x).toFixed(2); return t === '0.00' ? '0.00' : (x > 0 ? '+' : '−') + t; };
const pct = (x) => x == null ? '–' : Math.round(x * 100) + '%';

const header = (meta) => `
  <div class="top"><a class="logo" href="#/">BIG<span>GAME</span></a>
  <span class="small muted">Data to ${esc(meta.last_match)}</span></div>`;

window.addEventListener('hashchange', route);
route();

async function route() {
  const meta = await get('meta.json');
  const [, view, slug] = location.hash.split('/');
  if (view === 'p' && slug) return player(meta, slug);
  return home(meta);
}

// ---------------------------------------------------------------- home
async function home(meta) {
  const [players, league] = await Promise.all([get('players.json'), get('league.json')]);
  app.innerHTML = `${header(meta)}
    <h1>Who shows up in big games?</h1>
    <p class="soft" style="margin:0;line-height:1.5">Premier League players, judged against what they were <em>expected</em> to produce given the opponent, venue and their team. Every verdict comes with a range.</p>
    <label class="small muted">Search a player
      <input type="search" id="q" placeholder="e.g. Eze, Saka, Haaland" autocomplete="off"></label>
    <div class="list" id="results"></div>
    ${funnel(league, meta)}
    ${reliabilityCard(meta)}
    <p class="small muted">Built from Fantasy Premier League data (Opta), ${meta.seasons[0]} to ${meta.seasons.at(-1)}. Premier League matches only. Measures on-ball output and on-pitch team results; pressing and off-ball runs aren't in free data.</p>`;
  const q = document.getElementById('q'), out = document.getElementById('results');
  const draw = () => {
    const s = q.value.trim().toLowerCase();
    const hits = (s ? players.filter(p => p.name.toLowerCase().includes(s)) : players).slice(0, 8);
    out.innerHTML = hits.map(p => `<a href="#/p/${p.slug}"><span>${esc(p.name)}</span>
      <span class="small muted">${esc(p.pos)} · ${esc(p.team)}</span></a>`).join('');
  };
  q.addEventListener('input', draw); draw();
}

function funnel(league, meta) {
  const pts = league.filter(p => p.group === 'attack');
  const W = 520, H = 260, pad = 36;
  const maxX = Math.max(...pts.map(p => p.elite_minutes));
  const ext = Math.max(0.02, ...pts.map(p => Math.abs(p.delta))) * 1.15;
  const x = m => pad + (W - pad - 10) * m / maxX;
  const y = v => H / 2 - (H / 2 - 20) * v / ext;
  const dots = pts.map(p => `<a href="#/p/${p.slug}"><circle cx="${x(p.elite_minutes).toFixed(1)}" cy="${y(p.delta).toFixed(1)}" r="3.2" fill="${p.text.startsWith('No') ? '#6B7483' : p.text.startsWith('Rises') ? '#3DD9C1' : '#FF9F43'}"><title>${esc(p.name)}: ${f2(p.delta)}</title></circle></a>`).join('');
  const v = meta.validation.attack;
  return `<section class="card"><div class="label">Attackers: big-game effect vs minutes against elite teams</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Funnel plot of big-game estimates">
      <line x1="${pad}" x2="${W - 10}" y1="${y(0)}" y2="${y(0)}" stroke="#2A303B"/>
      <text x="${pad}" y="14" fill="#9AA3B2" font-size="11">Better vs elite</text>
      <text x="${pad}" y="${H - 22}" fill="#9AA3B2" font-size="11">Worse vs elite</text>
      <text x="${W - 10}" y="${H - 4}" fill="#9AA3B2" font-size="11" text-anchor="end">minutes vs elite →</text>${dots}</svg>
    <p class="small soft" style="margin:0;line-height:1.5">${v.trait_supported ? '' : `<b>Honest result:</b> a player's big-game effect in early seasons barely predicts it in later ones (r = ${v.repeatability_r}). So far, "big-game player" looks more like noise than a skill, and verdicts here are descriptions, not traits.`}</p></section>`;
}

function reliabilityCard(meta) {
  const rows = Object.entries(meta.reliability).map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td>${v.matches_to_0_7 ?? '19+'}</td></tr>`).join('');
  return `<section class="card"><div class="label">How many matches before a stat means something</div>
    <table><tr><th>Stat (per 90)</th><th>Matches per half to r ≥ 0.7</th></tr>${rows}</table>
    <p class="small muted" style="margin:0">Split-half test within position, on this site's own data.</p></section>`;
}

// -------------------------------------------------------------- player
async function player(meta, slug) {
  const p = await get(`p/${slug}.json`);
  const state = { team: 'all', filter: 'all' };
  const render = () => {
    const ms = p.matches.filter(m => state.team === 'all' || m.team === state.team);
    app.innerHTML = `${header(meta)}
      <div><h1>${esc(p.name)}</h1>
      <div class="small muted" style="margin-top:6px">${esc(p.position)} · ${p.teams.map(esc).join(' → ')} · ${p.minutes.toLocaleString()} PL minutes</div></div>
      ${verdictCard(p, meta)}
      ${tiersCard(p)}
      ${systemCard(p)}
      <section class="card"><div class="label">Every match</div>
        <div class="chips">${p.teams.length > 1 ? ['all', ...p.teams].map(t => `<button class="chip ${state.team === t ? 'on' : ''}" data-team="${esc(t)}">${t === 'all' ? 'All clubs' : esc(t)}</button>`).join('') : ''}</div>
        <div class="chips">${[['all', 'All'], ['Elite', 'Elite opp'], ['derby', 'Derbies'], ['stakes', 'High stakes'], ['home', 'Home'], ['away', 'Away']].map(([k, l]) => `<button class="chip ${state.filter === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('')}</div>
        ${matchLog(ms, state.filter, p)}</section>
      <p class="small muted">Rates use appearances of 30+ minutes. FPL xG includes penalties (it isn't split), so a penalty can lift a single match.</p>`;
    app.querySelectorAll('[data-team]').forEach(b => b.onclick = () => { state.team = b.dataset.team; render(); });
    app.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { state.filter = b.dataset.f; render(); });
  };
  render();
  window.scrollTo(0, 0);
}

function verdictCard(p, meta) {
  const v = p.verdict;
  if (!v) return `<section class="card"><div class="label">Big-game verdict</div><p class="soft">Not enough minutes yet.</p></section>`;
  const val = meta.validation[p.group];
  const ext = Math.max(0.1, Math.abs(v.lo), Math.abs(v.hi)) * 1.2;
  const pos = x => 50 + 50 * x / ext;
  const better = p.better === 'higher';
  return `<section class="card"><div class="label">Big-game verdict</div>
    <div class="big" style="font-size:24px;line-height:1.15">${esc(v.text)}</div>
    <div style="display:flex;align-items:baseline;gap:8px"><span class="big" style="font-size:40px;color:var(--accent)">${f2(v.delta)}</span>
      <span class="small muted">${esc(p.metric)} vs a top-10% opponent, compared with an average one</span></div>
    <div style="position:relative;height:28px" aria-hidden="true">
      <div style="position:absolute;left:0;right:0;top:13px;height:2px;background:var(--line)"></div>
      <div style="position:absolute;left:50%;top:4px;width:2px;height:20px;background:#6B7483"></div>
      <div style="position:absolute;left:${pos(v.lo)}%;width:${pos(v.hi) - pos(v.lo)}%;top:9px;height:10px;border-radius:6px;background:rgba(61,217,193,.35)"></div>
      <div style="position:absolute;left:calc(${pos(v.delta)}% - 6px);top:8px;width:12px;height:12px;border-radius:50%;background:var(--accent)"></div></div>
    <div class="small muted" style="display:flex;justify-content:space-between"><span>${better ? 'Less' : 'Less conceded'}</span><span>${better ? 'More' : 'More conceded'}</span></div>
    <div class="soft small" style="line-height:1.5">80% range ${f2(v.lo)} to ${f2(v.hi)}. Chance he's genuinely better in big games: ${pct(v.p_better)}. Already adjusts for opponent, venue, his team's strength and his level in each season.</div>
    <div class="chips"><span class="tag ${v.confidence === 'Low' ? 'warn' : ''}">${v.confidence} confidence</span>
      <span class="tag">${v.elite_matches} elite matches · ${v.elite_minutes.toLocaleString()} min</span></div>
    ${val.trait_supported ? '' : `<div class="small muted" style="line-height:1.5">League-wide, this effect hasn't repeated season to season (r = ${val.repeatability_r}), so read it as what happened, not a fixed trait.</div>`}
  </section>`;
}

function tiersCard(p) {
  const rows = p.tiers.filter(t => t.matches);
  const max = Math.max(...rows.flatMap(t => [t.actual, t.expected])) * 1.1;
  return `<section class="card"><div class="label">By opponent strength · ${esc(p.metric)}</div>
    ${rows.map(t => `<div class="row"><span class="soft">${t.tier}</span>
      <div class="bar"><i style="width:${100 * Math.max(0, t.actual) / max}%"></i><b style="left:${100 * t.expected / max}%"></b></div>
      <span style="text-align:right;font-variant-numeric:tabular-nums">${t.actual.toFixed(2)} <span class="muted small">/ ${t.expected.toFixed(2)}</span></span></div>
      <div class="small muted" style="margin:-6px 0 0 72px">${t.matches} matches</div>`).join('')}
    <div class="small muted" style="line-height:1.5">Bar = actual. White line = expected for those exact fixtures, given opponent, venue, his team and his level that season. Tiers come from each team's xG-based strength on match day.</div></section>`;
}

function systemCard(p) {
  if (!p.system.length) return '';
  const body = p.system.map(s => `<tr><td>${s.season.slice(2)} ${esc(s.team)}</td><td>${s.xgi90.toFixed(2)}</td><td>${pct(s.team_share)}</td><td>${s.xgc90_on.toFixed(2)} / ${s.xgc90_off == null ? '–' : s.xgc90_off.toFixed(2)}</td></tr>`).join('');
  return `<section class="card"><div class="label">Player vs system</div>
    <div class="scroll"><table><tr><th>Season</th><th>xGI/90</th><th>Team share</th><th>xGC/90 on / off</th></tr>${body}</table></div>
    <div class="small muted" style="line-height:1.5">Team share = his xG + xA as a share of his team's while he played. xGC on/off = chances his team conceded per 90 with him on vs. off the pitch. Rising raw numbers with a falling share usually means a better team, not a better player.</div></section>`;
}

function matchLog(ms, f, p) {
  const keep = {
    all: () => true, Elite: m => m.tier === 'Elite', derby: m => m.derby, stakes: m => m.stakes,
    home: m => m.home, away: m => !m.home,
  }[f];
  const rows = ms.filter(keep).filter(m => m.minutes > 0);
  const mins = rows.reduce((a, m) => a + m.minutes, 0);
  const sum = k => rows.reduce((a, m) => a + (m[k] || 0), 0);
  const per90 = k => mins ? (sum(k) / mins * 90).toFixed(2) : '–';
  const att = p.group === 'attack';
  const summary = `<div class="grid2"><div class="tile"><span class="small muted">Matches · minutes</span><span class="big" style="font-size:20px">${rows.length} · ${mins.toLocaleString()}</span></div>
    <div class="tile"><span class="small muted">${att ? 'xG + xA per 90' : 'xGC per 90 on pitch'}</span><span class="big" style="font-size:20px">${att ? (mins ? ((sum('xg') + sum('xa')) / mins * 90).toFixed(2) : '–') : per90('xgc')}</span></div></div>`;
  return summary + rows.slice(0, 80).map(m => `<div class="m">
    <div>${m.home ? 'vs' : '@'} ${esc(m.opp)}<span class="pill ${m.tier}">${m.tier}</span>${m.derby ? '<span class="pill d">Derby</span>' : ''}${m.stakes ? '<span class="pill">Stakes</span>' : ''}
      <div class="small muted">${m.date} · ${m.team} · ${m.score} · ${m.minutes}'${m.started === false ? ' (sub)' : ''}</div></div>
    <div style="text-align:right;font-variant-numeric:tabular-nums">${att ? `${m.goals}G ${m.assists}A` : `xGC ${m.xgc.toFixed(2)}`}
      <div class="small muted">${att ? `xG ${m.xg.toFixed(2)} · xA ${m.xa.toFixed(2)}` : (m.defcon != null ? `Def. actions ${m.defcon}` : '')}</div></div></div>`).join('')
    + (rows.length > 80 ? `<p class="small muted">Showing the latest 80.</p>` : '');
}
