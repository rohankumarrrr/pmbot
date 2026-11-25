"""A one-page view of an account: equity, positions, resting quotes, fills, rewards.

Kalshi's own site does not show subaccounts, so this is the bot's portfolio screen. `collect` reads
only the ledger (no exchange calls), so the page can be built on the machine that holds it at any
time; it is as fresh as the bot's last cycle. `render` returns one self-contained HTML file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .ledger.db import Ledger
from .portfolio import mark_price, position_value, positions

MAX_POINTS = 500


def _title(ledger: Ledger, ticker: str) -> dict:
    m = ledger.one("SELECT title, yes_sub_title, close_ts FROM markets WHERE ticker=?", [ticker])
    return {"title": (m["title"] if m else None) or ticker, "sub": (m["yes_sub_title"] if m else None) or "",
            "close_ts": m["close_ts"] if m else None}


def collect(ledger: Ledger, cfg) -> dict:
    mode = cfg.mode
    key = mode if mode == "shadow" else f"{mode}:v2"
    initial = float(cfg.bankroll_usd) if mode == "shadow" else ledger.get_state(f"initial_cash:{mode}")
    strategy_of = {r["ticker"]: r["strategy"] for r in ledger.query(
        "SELECT DISTINCT ticker, strategy FROM decisions WHERE mode=? AND action='order'", [mode])}

    held, settled_n, realized = [], 0, 0.0
    for p in positions(ledger, mode):
        realized += p.paired_gain
        if p.settled:
            settled_n += 1
            realized += p.payout - p.cost
            continue
        if p.contracts <= 0:
            continue
        value, priced = position_value(ledger, p)
        held.append({"ticker": p.ticker, "side": p.side, "contracts": p.contracts, "cost": p.cost, "value": value,
                     "priced": priced, "strategy": strategy_of.get(p.ticker, ""), **_title(ledger, p.ticker)})
    held.sort(key=lambda r: r["value"] - r["cost"])

    resting = []
    for o in ledger.query(
            """SELECT o.ticker, o.side, o.price, o.contracts, o.created_ts, o.expires_ts, d.strategy, d.reasons, d.kind,
                      o.contracts - COALESCE((SELECT SUM(f.contracts) FROM fills f WHERE f.client_order_id = o.client_order_id), 0) AS remaining
               FROM orders o JOIN decisions d ON d.id = o.decision_id
               WHERE o.mode=? AND o.status IN ('resting','partial') ORDER BY o.price * o.contracts DESC""", [mode]):
        reasons = o["reasons"] if isinstance(o["reasons"], list) else json.loads(o["reasons"] or "[]")
        reward = next((float(x.split("=")[1]) for x in reasons if isinstance(x, str) and x.startswith("reward_day=")), None)
        resting.append({"ticker": o["ticker"], "side": o["side"], "price": o["price"], "contracts": o["remaining"],
                        # An offer on a held position pairs it off when it fills: nothing new at risk.
                        "at_risk": 0.0 if o["kind"] == "lp_close" else o["price"] * o["remaining"], "reward_day": reward, "created_ts": o["created_ts"],
                        "expires_ts": o["expires_ts"], "strategy": o["strategy"], **_title(ledger, o["ticker"])})

    fills = [{"ts": f["ts"], "ticker": f["ticker"], "side": f["side"], "price": f["price"], "contracts": f["contracts"],
              "fee": f["fee"], **_title(ledger, f["ticker"])}
             for f in ledger.query("SELECT f.* FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id "
                                   "WHERE o.mode=? ORDER BY f.ts DESC LIMIT 40", [mode])]
    n_fills = ledger.one("SELECT COUNT(*) AS n FROM fills f JOIN orders o ON o.client_order_id = f.client_order_id WHERE o.mode=?", [mode])["n"]

    history = ledger.query("SELECT ts, cash, positions_value, equity, resting_at_risk, estimated_rewards, credited "
                           "FROM equity_history WHERE mode=? ORDER BY ts", [mode])
    step = max(1, len(history) // MAX_POINTS)
    series = [dict(r) for i, r in enumerate(history) if i % step == 0 or i == len(history) - 1]
    latest = dict(history[-1]) if history else None

    # Controls: what is quoted and held per family, and the settings changed while the bot runs.
    from . import lp as lp_rules, overrides
    base = dict(cfg["lp"])
    in_force, changed = overrides.effective(base, ledger, mode), overrides.load(ledger, mode)
    paused = list(in_force.get("exclude_families") or [])
    fams: dict[str, dict] = {}
    for r in resting:
        f = fams.setdefault(lp_rules.family(r["ticker"], in_force), {"markets": set(), "resting": 0.0, "cost": 0.0, "value": 0.0})
        f["markets"].add(r["ticker"]); f["resting"] += r["at_risk"]
    for h in held:
        f = fams.setdefault(lp_rules.family(h["ticker"], in_force), {"markets": set(), "resting": 0.0, "cost": 0.0, "value": 0.0})
        f["markets"].add(h["ticker"]); f["cost"] += h["cost"]; f["value"] += h["value"]
    families = sorted(({"family": k, "markets": len(v["markets"]), "resting": v["resting"], "cost": v["cost"], "value": v["value"],
                        "paused": any(k.startswith(x) or x.startswith(k) for x in paused)} for k, v in fams.items()),
                      key=lambda f: -(f["resting"] + f["cost"]))
    which = "twin" if "twin" in str(cfg.ledger_path) else {"shadow": "paper"}.get(mode, mode)
    controls = {
        "which": which, "paused": paused, "family_cap": in_force.get("max_markets_per_family") or 0, "families": families,
        "changed": [{"setting": f"lp.{k}", "config": json.dumps(base.get(k)), "now": json.dumps(in_force.get(k))} for k in sorted(changed)],
        "locked": [f"lp.{k}" for k in sorted(overrides.LOCKED) if k in base],
    }

    events = [dict(r) for r in ledger.query("SELECT ts, kind, substr(detail, 1, 220) AS detail FROM risk_events ORDER BY id DESC LIMIT 12")]
    peak = ledger.get_state(f"peak_equity:{key}")
    day_open = ledger.get_state(f"day_open_equity:{key}:{time.strftime('%Y-%m-%d', time.gmtime())}")
    return {
        "mode": mode, "generated_ts": int(time.time()), "last_cycle_ts": ledger.get_state(f"lp_last_step:{mode}"),
        "halted": ledger.get_state(f"halted:{mode}"), "initial": initial, "latest": latest,
        "peak": peak, "day_open": day_open, "max_drawdown": cfg.risk.max_drawdown, "daily_loss_limit": cfg.risk.daily_loss_limit,
        "positions": held, "settled_positions": settled_n, "realized": realized,
        "resting": resting, "fills": fills, "fills_total": n_fills, "events": events, "series": series,
        "controls": controls,
    }


def render(data: dict) -> str:
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    return PAGE.replace("__DATA__", payload).replace("__MODE__", {"shadow": "paper"}.get(data["mode"], data["mode"]))


def write(ledger: Ledger, cfg, out: str | Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect(ledger, cfg)))
    return out


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>pmbot · __MODE__</title>
<style>
.viz-root{color-scheme:light;--plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
  --axis:#c3c2b7;--border:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--up:#006300;--down:#d03b3b;
  --good:#0ca30c;--warning:#fab219;--critical:#d03b3b;--wash:rgba(11,11,11,.04)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;
  --ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;
  --up:#0ca30c;--down:#e66767;--wash:rgba(255,255,255,.05)}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--up:#0ca30c;--down:#e66767;--wash:rgba(255,255,255,.05)}
*{box-sizing:border-box}
body{margin:0}
.viz-root{background:var(--plane);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh;padding:24px}
.wrap{max-width:1120px;margin:0 auto;display:grid;gap:16px}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between}
h1{font-size:18px;font-weight:600;margin:0}
h2{font-size:14px;font-weight:600;margin:0 0 2px}
.sub{color:var(--ink2);font-size:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;min-width:0}
.status{display:inline-flex;gap:6px;align-items:center;font-weight:600}
.status i{width:10px;height:10px;border-radius:50%;display:inline-block}
.hero{display:flex;flex-wrap:wrap;gap:8px 32px;align-items:flex-end}
.hero .num{font-size:52px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums}
.delta{font-weight:600;font-variant-numeric:tabular-nums}
.up{color:var(--up)} .down{color:var(--down)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(142px,1fr));gap:12px}
.tile .label{color:var(--ink2);font-size:12px}
.tile .value{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.tile .note{color:var(--muted);font-size:12px}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:16px}
.chart{position:relative;margin-top:8px}
.chart svg{display:block;width:100%;height:230px;overflow:visible}
.legend{display:flex;gap:16px;color:var(--ink2);font-size:12px;margin-top:6px}
.legend span::before{content:"";display:inline-block;width:14px;height:2px;margin-right:6px;vertical-align:middle;background:var(--c)}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 10px;
  font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.12);white-space:nowrap;display:none;z-index:2}
.tip b{font-variant-numeric:tabular-nums}
.tip .k{display:inline-block;width:12px;height:2px;margin-right:6px;vertical-align:middle}
.empty{color:var(--muted);padding:28px 0;text-align:center}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{color:var(--ink2);font-weight:500;text-align:left;border-bottom:1px solid var(--axis);padding:6px 10px 6px 0;white-space:nowrap}
td{border-bottom:1px solid var(--grid);padding:7px 10px 7px 0;vertical-align:top}
td.n,th.n{text-align:right;padding-right:0;padding-left:10px;white-space:nowrap}
tr:hover td{background:var(--wash)}
.mk{max-width:420px}.mk small{color:var(--muted);display:block}
details summary{cursor:pointer;color:var(--ink2);font-size:12px;margin-top:8px}
</style></head>
<body><div class="viz-root"><div class="wrap">
<header><div><h1>pmbot · __MODE__ account</h1><div class="sub" id="asof"></div></div><div class="status" id="status"></div></header>
<section class="card"><div class="hero"><div><div class="sub">Equity (cash plus positions at current prices)</div><div class="num" id="equity"></div></div>
<div><div class="delta" id="pnl"></div><div class="sub" id="pnlnote"></div></div></div></section>
<section class="tiles" id="tiles"></section>
<section class="charts">
<div class="card"><h2>Equity over time</h2><div class="sub">Dollars, one point per bot cycle</div><div class="chart" id="c-equity"></div></div>
<div class="card"><h2>Rewards, cumulative</h2><div class="sub" id="rw-sub"></div><div class="chart" id="c-rewards"></div></div>
</section>
<section class="card"><h2>Open positions</h2><div class="sub" id="pos-sub"></div><div class="scroll" id="t-pos"></div></section>
<section class="card"><h2>Resting quotes</h2><div class="sub" id="rest-sub"></div><div class="scroll" id="t-rest"></div></section>
<section class="card"><h2>Recent fills</h2><div class="sub" id="fill-sub"></div><div class="scroll" id="t-fill"></div></section>
<section class="card"><h2>Controls</h2><div class="sub" id="ctl-sub"></div>
<div class="scroll" id="t-fam"></div><div class="scroll" id="t-chg"></div>
<div class="sub" style="margin-top:12px">Run these in the project folder. A change takes effect on the bot's next cycle, with no restart, and is written to the events below with its reason.</div>
<pre id="ctl-cmd" style="white-space:pre-wrap;font:12px ui-monospace,Menlo,monospace;color:var(--ink2);margin:8px 0 0"></pre></section>
<section class="card"><h2>Risk events</h2><div class="sub">Halts, resumes, rejections and other things the bot flagged, newest first</div><div class="scroll" id="t-ev"></div></section>
</div></div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
const WJ = '\u2060';     // word joiner: keeps a sign and its amount on one line
const usd = (v, d = 2) => v == null ? '–' : (v < 0 ? '−' + WJ + '$' : '$') + Math.abs(v).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
const signed = v => v == null ? '–' : Math.abs(v) < 0.005 ? '$0.00' : (v > 0 ? '+' : '−') + WJ + '$' + Math.abs(v).toFixed(2);
const tone = v => v == null || Math.abs(v) < 0.005 ? '' : v > 0 ? 'up' : 'down';
const cents = p => String(Math.round(p * 1000) / 10) + '¢';
const when = ts => ts ? new Date(ts * 1000).toLocaleString([], {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}) : '–';
const ago = ts => { const m = Math.round((D.generated_ts - ts) / 60); return m < 90 ? m + ' min' : m < 2880 ? Math.round(m / 60) + ' h' : Math.round(m / 1440) + ' d'; };
const L = D.latest, sum = (a, f) => a.reduce((s, x) => s + f(x), 0);

// header
$('asof').textContent = 'Built ' + when(D.generated_ts) + (D.last_cycle_ts ? ' · bot last ran ' + ago(D.last_cycle_ts) + ' earlier' : '');
const stale = D.last_cycle_ts && D.generated_ts - D.last_cycle_ts > 1800;
const st = D.halted ? ['critical', '⏸ Halted: ' + D.halted] : stale ? ['warning', '⚠ No cycle for ' + ago(D.last_cycle_ts)] : ['good', '✓ Running'];
const dot = el('i'); dot.style.background = 'var(--' + st[0] + ')'; $('status').append(dot, el('span', st[1]));

// hero + tiles
const posCost = sum(D.positions, p => p.cost), posVal = sum(D.positions, p => p.value), atRisk = sum(D.resting, r => r.at_risk);
const equity = L ? L.equity : null, total = equity != null && D.initial != null ? equity - D.initial : null;
$('equity').textContent = usd(equity);
$('pnl').textContent = signed(total); if (tone(total)) $('pnl').classList.add(tone(total));
$('pnlnote').textContent = D.initial != null ? 'since it started with ' + usd(D.initial) : '';
const tile = (label, value, note) => { const t = el('div', null, 'card tile'); t.append(el('div', label, 'label'), el('div', value, 'value'), el('div', note || '', 'note')); $('tiles').append(t); };
tile('Cash', usd(L && L.cash), 'not tied up in positions');
tile('Open positions', usd(posVal), D.positions.length + ' held, cost ' + usd(posCost));
tile('Resting quotes', usd(atRisk), D.resting.length + ' orders waiting to fill');
tile('Trading result', signed(D.realized + posVal - posCost), 'realised ' + signed(D.realized) + ', open ' + signed(posVal - posCost));
if (D.mode !== 'shadow') tile('Rewards credited', usd(L && L.credited), 'cash Kalshi added, not from trading');
tile('Rewards estimated', usd(L && L.estimated_rewards), "the bot's own estimate");
if (D.peak != null) tile('Halts below', usd(D.peak * (1 - D.max_drawdown)), Math.round(D.max_drawdown * 100) + '% under the peak of ' + usd(D.peak));

// line chart: one y axis, crosshair, one tooltip for every series
function chart(host, series, fmt) {
  host.textContent = '';
  const pts = series[0].points;
  if (pts.length < 2) { host.append(el('div', 'Not enough history yet. A point is added every cycle.', 'empty')); return; }
  const NS = 'http://www.w3.org/2000/svg', W = host.clientWidth || 480, H = 230, m = {l: 54, r: 66, t: 12, b: 26};
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', series.map(s => s.name + ' now ' + fmt(s.points[s.points.length - 1][1])).join('; '));
  const mk = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; svg.append(e); return e; };
  const all = series.flatMap(s => s.points.map(p => p[1])).filter(v => v != null);
  let lo = Math.min(...all), hi = Math.max(...all); if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map(x => x * mag).find(x => x >= raw);
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  const x = t => m.l + (t - t0) / (t1 - t0 || 1) * (W - m.l - m.r), y = v => H - m.b - (v - lo) / (hi - lo) * (H - m.t - m.b);
  const dec = step < 1 ? 2 : 0;
  for (let v = lo; v <= hi + 1e-9; v += step) {
    mk('line', {x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: 'var(--grid)', 'stroke-width': 1});
    mk('text', {x: m.l - 8, y: y(v) + 4, 'text-anchor': 'end', fill: 'var(--muted)', 'font-size': 11}, usd(v, dec));
  }
  mk('line', {x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: 'var(--axis)', 'stroke-width': 1});
  const span = t1 - t0, tf = span > 172800 ? {month: 'short', day: 'numeric'} : {hour: 'numeric', minute: '2-digit'};
  [0, .5, 1].forEach((f, i) => mk('text', {x: x(t0 + f * span), y: H - 8, 'text-anchor': ['start', 'middle', 'end'][i], fill: 'var(--muted)', 'font-size': 11},
    new Date((t0 + f * span) * 1000).toLocaleString([], tf)));
  const ends = [];
  series.forEach(s => {
    const p = s.points.filter(q => q[1] != null); if (!p.length) return;
    mk('path', {d: p.map((q, i) => (i ? 'L' : 'M') + x(q[0]).toFixed(1) + ' ' + y(q[1]).toFixed(1)).join(''), fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'});
    const e = p[p.length - 1];
    mk('circle', {cx: x(e[0]), cy: y(e[1]), r: 4, fill: s.color, stroke: 'var(--surface)', 'stroke-width': 2});
    ends.push({y: y(e[1]), text: fmt(e[1]), x: x(e[0])});
  });
  ends.sort((a, b) => a.y - b.y);                       // end labels: keep them apart, or drop the second if they would collide
  ends.forEach((e, i) => { if (i && e.y - ends[i - 1].y < 14) return; mk('text', {x: e.x + 9, y: e.y + 4, fill: 'var(--ink)', 'font-size': 12, 'font-weight': 600}, e.text); });
  const cross = mk('line', {y1: m.t, y2: H - m.b, stroke: 'var(--axis)', 'stroke-width': 1, visibility: 'hidden'});
  const tip = el('div', null, 'tip');
  host.append(svg, tip);
  const move = ev => {
    const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) / r.width * W, t = t0 + (px - m.l) / (W - m.l - m.r) * span;
    let i = 0; for (let k = 1; k < pts.length; k++) if (Math.abs(pts[k][0] - t) < Math.abs(pts[i][0] - t)) i = k;
    cross.setAttribute('x1', x(pts[i][0])); cross.setAttribute('x2', x(pts[i][0])); cross.setAttribute('visibility', 'visible');
    tip.textContent = ''; tip.append(el('div', when(pts[i][0]), 'sub'));
    series.forEach(s => { const row = el('div'), k = el('span', null, 'k'); k.style.background = s.color; row.append(k, el('b', s.points[i][1] == null ? '–' : fmt(s.points[i][1])), document.createTextNode(' ' + s.name)); tip.append(row); });
    tip.style.display = 'block';
    const left = x(pts[i][0]) / W * r.width; tip.style.left = Math.min(Math.max(left + 12, 0), r.width - tip.offsetWidth) + 'px'; tip.style.top = '8px';
  };
  svg.addEventListener('pointermove', move); svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); });
  if (series.length > 1) { const lg = el('div', null, 'legend'); series.forEach(s => { const sp = el('span', s.name); sp.style.setProperty('--c', s.color); lg.append(sp); }); host.append(lg); }
  const det = el('details'); det.append(el('summary', 'Show these numbers as a table'));
  const n = Math.max(1, Math.ceil(pts.length / 24));
  det.append(table(['Time', ...series.map(s => s.name)], pts.map((p, i) => i).filter(i => i % n === 0 || i === pts.length - 1)
    .map(i => [when(pts[i][0]), ...series.map(s => ({n: s.points[i][1] == null ? '–' : fmt(s.points[i][1])}))])));
  host.append(det);
}
function table(head, rows, emptyText) {
  if (!rows.length) return el('div', emptyText || 'None.', 'empty');
  const t = el('table'), hr = el('tr'); t.append(hr);
  rows.forEach((r, ri) => { const tr = el('tr'); r.forEach((c, ci) => {
    const numeric = c && typeof c === 'object' && 'n' in c;
    if (!ri) hr.append(el('th', head[ci], numeric ? 'n' : ''));
    const td = el('td', null, numeric ? 'n' : '');
    if (c && c.market) { td.className = 'mk'; td.append(document.createTextNode(c.market.title + (c.market.sub ? ' [' + c.market.sub + ']' : '')), el('small', c.market.ticker)); }
    else if (numeric) { td.textContent = c.n; if (c.cls) td.classList.add(c.cls); }
    else td.textContent = c;
    tr.append(td); }); t.append(tr); });
  return t;
}
const S = D.series, eq = [{name: 'Equity', color: 'var(--s1)', points: S.map(p => [p.ts, p.equity])}];
const rw = [{name: 'Estimated by the bot', color: 'var(--s1)', points: S.map(p => [p.ts, p.estimated_rewards])}];
if (D.mode !== 'shadow') rw.push({name: 'Credited by Kalshi', color: 'var(--s2)', points: S.map(p => [p.ts, p.credited])});
$('rw-sub').textContent = D.mode === 'shadow' ? "Dollars. Paper trading: the bot's estimate only, nothing is credited" : 'Dollars. The gap between the two lines is what this test measures';
const draw = () => { chart($('c-equity'), eq, v => usd(v)); chart($('c-rewards'), rw, v => usd(v)); };
draw(); let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(draw, 150); });

// tables
const pl = v => ({n: signed(v), cls: tone(v)});
$('pos-sub').textContent = D.positions.length ? 'Worst first. Held until the market settles; value uses the latest tight order book.' + (D.settled_positions ? ' ' + D.settled_positions + ' more have settled. Realised so far, pair-offs included: ' + signed(D.realized) + '.' : '') : '';
$('t-pos').append(table(['Market', 'Side', 'Contracts', 'Avg price', 'Cost', 'Value now', 'Gain / loss', 'Closes'],
  D.positions.map(p => [{market: p}, p.side.toUpperCase(), {n: p.contracts.toLocaleString()}, {n: cents(p.cost / p.contracts)}, {n: usd(p.cost)},
    {n: usd(p.value) + (p.priced ? '' : ' (at cost)')}, pl(p.value - p.cost), {n: when(p.close_ts)}]), 'No open positions.'));
$('rest-sub').textContent = D.resting.length ? 'Bids waiting in the book. Each lapses on its own if the bot stops renewing it.' : '';
$('t-rest').append(table(['Market', 'Side', 'Price', 'Contracts', 'At risk', 'Est. reward / day', 'Placed', 'Lapses'],
  D.resting.map(r => [{market: r}, r.side.toUpperCase(), {n: cents(r.price)}, {n: r.contracts.toLocaleString()}, {n: usd(r.at_risk)},
    {n: r.reward_day == null ? '–' : usd(r.reward_day)}, {n: when(r.created_ts)}, {n: when(r.expires_ts)}]), 'No orders resting.'));
$('fill-sub').textContent = D.fills_total ? D.fills_total + ' in total; the latest ' + D.fills.length + ' shown' : '';
$('t-fill').append(table(['Time', 'Market', 'Side', 'Price', 'Contracts', 'Cost'],
  D.fills.map(f => [when(f.ts), {market: f}, f.side.toUpperCase(), {n: cents(f.price)}, {n: f.contracts.toLocaleString()}, {n: usd(f.price * f.contracts + (f.fee || 0))}]), 'No fills yet.'));
const C = D.controls, top = C.families.length ? C.families[0].family : 'KXAAAGAS';
$('ctl-sub').textContent = 'Markets grouped by family (the first letters of the series name). At most ' + (C.family_cap || 'any number of') +
  ' markets per family are quoted or held.' + (C.paused.length ? ' Paused: ' + C.paused.join(', ') + '.' : ' No family is paused.');
$('t-fam').append(table(['Family', 'Markets', 'Resting at risk', 'Positions cost', 'Positions value now', 'State'],
  C.families.map(f => [f.family, {n: String(f.markets)}, {n: usd(f.resting)}, {n: usd(f.cost)}, {n: usd(f.value)}, f.paused ? 'paused' : 'quoting']),
  'Nothing quoted or held.'));
if (C.changed.length) $('t-chg').append(table(['Setting changed while running', 'Config file', 'Now'], C.changed.map(c => [c.setting, c.config, c.now])));
$('ctl-cmd').textContent = [
  './scripts/control.sh ' + C.which + ' settings',
  './scripts/control.sh ' + C.which + ' pause ' + top + ' --why "reason"',
  './scripts/control.sh ' + C.which + ' unpause ' + top,
  './scripts/control.sh ' + C.which + ' set lp.max_markets_per_family 2 --why "reason"',
  './scripts/control.sh ' + C.which + ' set lp.contracts_per_side 100 --why "reason"',
  './scripts/control.sh ' + C.which + ' unset lp.contracts_per_side',
  '',
  'Not adjustable here (hard limits, changed in the config file): ' + C.locked.join(', ') + ', and everything under risk and trading.',
].join('\n');
$('t-ev').append(table(['Time', 'Event', 'Detail'], D.events.map(e => [when(e.ts), e.kind.replace(/_/g, ' '), e.detail || '']), 'Nothing flagged.'));
</script></body></html>
"""
