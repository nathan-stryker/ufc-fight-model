"""
Static, search-engine-readable pages for every fight and event, plus a
sitemap -- so Google can index "Buckley vs Malott prediction"-type searches.
The main site builds itself in the browser from one big embedded payload, so
Google only ever saw one page. These are plain HTML with everything written
into the page, but built from the site's own stylesheet and components
(masthead, nav, fight rows, flags, odds bar, method/round bars, tale of the
tape) so a visitor arriving from Google lands on something that looks like
Call the Card.

Writes (under docs/, served by GitHub Pages at callthecard.com):
  events/<event-slug>/index.html                 the whole card
  events/<event-slug>/<a>-vs-<b>/index.html      one fight
  events/<event-slug>/<a>-vs-<b>/og.png          1200x630 share image
  events/<event-slug>/event.json                 metadata for the index/sitemap
  events/index.html, sitemap.xml, robots.txt

Upcoming card: pick, win %, method and round odds (predict.py -- the same
numbers the site shows, see check_js_parity). Last week's card: rebuilt with
the real result and whether the pick was right. Older events stay as they were.

Run: python -m src.build_seo_pages   (also run at the end of web/build_site.py)
"""
import html
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
WEB = ROOT / "web"
SITE = "https://callthecard.com"
FONT_DIR = WEB / "fonts"
METHOD_NAMES = {"dec": "Decision", "ko": "KO/TKO", "sub": "Submission"}
METHOD_SHORT = {"dec": "Decision", "ko": "KO/TKO", "sub": "Sub"}
TIER_LABEL = {"main_event": "Main Event", "co_main": "Co-Main", "featured_prelim": "Featured Prelim"}
TIER_ROW_CLASS = {"main_event": "fc-row--main-event", "co_main": "fc-row--co-main", "featured_prelim": "fc-row--featured-prelim"}
FORM_VERB = {"W": "def.", "L": "lost to", "D": "drew", "NC": "no contest vs."}
STRIKE = {"Power": "Power Striker", "Pressure": "Pressure Striker", "Volume": "Volume Striker", "Counter": "Counter Striker",
          "Technical": "Technical Striker", "Balanced": "Balanced Striker", "Minimal": "Minimal Striking"}
GRAPPLE = {"Wrestler": "Wrestler", "Submission": "Submission Grappler", "Takedown Defense": "Takedown Defender",
           "Balanced": "Balanced Grappler", "Minimal": "Minimal Grappling"}

# Small additions on top of the site's own stylesheet.
EXTRA_CSS = """<style>
  .seo-main { max-width: 820px; margin: 0 auto; }
  .seo-intro { color: var(--ink-dim); line-height: 1.6; margin: 0.4rem 0 1.4rem; max-width: 62ch; }
  .seo-title { margin: 0.2rem 0 0.4rem; }
  .fc-fighter a, .seo-link { color: inherit; text-decoration: none; }
  .fc-fighter a:hover, .seo-link:hover { color: var(--gold); }
  .seo-section { margin-top: 2rem; }
  .seo-result { border-left: 3px solid var(--gold); background: var(--canvas-raised); padding: 0.8rem 1rem; margin: 1rem 0; }
  .seo-result .hit { color: var(--gold); font-weight: 700; }
  .seo-result .miss { color: var(--ink-dim); font-weight: 700; }
  .seo-row-cta { display: inline-block; margin-top: 0.6rem; font-size: 0.78rem; color: var(--gold); }
  .seo-track { color: var(--ink-dim); font-size: 0.8rem; margin-top: 1.6rem; line-height: 1.6; }
  .seo-more a { display: block; padding: 0.5rem 0; border-bottom: 1px solid var(--canvas-line); color: var(--ink); text-decoration: none; }
  .seo-more a:hover { color: var(--gold); }
  .seo-more .mono { color: var(--ink-dim); font-size: 0.75rem; margin-left: 0.4rem; }
  .seo-analysis { margin: 0.6rem 0 1.8rem; }
  .seo-h3 { font-family: 'Oswald', sans-serif; font-size: 0.95rem; letter-spacing: 0.06em; text-transform: uppercase;
            color: var(--gold); margin: 1.2rem 0 0.35rem; }
  .seo-para { line-height: 1.7; margin: 0; max-width: 68ch; }
</style>"""


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def esc(s):
    return html.escape(str(s), quote=True)


def pct(x):
    return f"{round(x * 100)}%"


def nice_date(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def fighters_by_id(payload):
    f = payload["fighters"]
    return {r[0]: dict(zip(f["fields"], r)) for r in f["rows"]}


def style_text(f):
    if f.get("strike_style") and f.get("grapple_style"):
        return f"{STRIKE[f['strike_style']]} · {GRAPPLE[f['grapple_style']]}"
    return f.get("style")


def age(f):
    d = f.get("dob_epoch_days")
    return int(((date.today() - date(1970, 1, 1)).days - d) // 365.25) if d is not None else None


def height(f):
    h = f.get("height_in")
    return f"{int(h // 12)}'{int(round(h % 12))}\"" if h else None


def reach(f):
    r = f.get("reach_in")
    return f'{r:g}"' if r else None


# ---------------------------------------------------------------- site shell
_STYLE = None


def site_style():
    global _STYLE
    if _STYLE is None:
        t = (WEB / "site_template.html").read_text(encoding="utf-8")
        m = re.search(r"<style>.*?</style>", t, re.S)
        _STYLE = (m.group(0) if m else "<style></style>") + EXTRA_CSS
    return _STYLE


# Favicon set from web/make_icons.py, copied to the docs/ root by build_site.py.
ICON_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="48x48">'
              '<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">'
              '<link rel="apple-touch-icon" href="/apple-touch-icon.png">')


def page(title, description, canonical, body, og_image=None, jsonld=None):
    og = (f'<meta property="og:image" content="{og_image}"><meta name="twitter:image" content="{og_image}">'
          f'<meta name="twitter:card" content="summary_large_image">') if og_image else '<meta name="twitter:card" content="summary">'
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{ICON_LINKS}
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Call the Card">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">{og}{ld}
{site_style()}</head><body>
<div class="page">
  <header class="masthead">
    <a href="/" style="text-decoration:none"><h1 class="logo-mark display" aria-label="Call the Card">
      <span class="logo-call" aria-hidden="true">Call</span>
      <span class="logo-the" aria-hidden="true">T<br>h<br>e</span>
      <span class="logo-card" aria-hidden="true">Card</span>
    </h1></a>
    <div class="masthead-rule"></div>
  </header>
  <nav class="site-nav">
    <a href="/#fight-card">This Week's Card</a>
    <a href="/news.html">News</a>
    <a href="/results.html">Last Week's Results</a>
    <a href="/predict.html">Fantasy Matchup</a>
  </nav>
  <main class="seo-main">
{body}
  </main>
</div>
</body></html>"""


# ---------------------------------------------------------------- components
def flag(f, payload):
    svg = (payload.get("flags") or {}).get(f.get("iso_code"))
    return f'<div class="fc-badge">{svg}</div>' if svg else ""


def rank_chip(rank):
    if not rank:
        return ""
    cls = "fc-rank-chip fc-rank-chip--champ" if rank == "C" else "fc-rank-chip"
    return f'<span class="{cls}">{esc(rank)}</span>'


def form_badges(fid, payload):
    results = (payload.get("recent_results") or {}).get(fid)
    if results is None:
        return ""
    if not results:
        return '<div class="fc-debut-label">UFC Debut</div>'
    out = []
    for r in results:
        cls = {"W": "fc-form-badge--w", "L": "fc-form-badge--l"}.get(r["result"], "fc-form-badge--nd")
        bits = [f"{FORM_VERB.get(r['result'], '')} {r['opponent']}"] + ([r["method"]] if r.get("method") else []) + \
               ([f"R{r['round']}"] if r.get("round") else [])
        out.append(f'<button type="button" class="fc-form-badge {cls}">{esc(r["result"])}'
                   f'<span class="fc-form-tip">{esc(" · ".join(bits))}</span></button>')
    return f'<div class="fc-form">{"".join(out)}</div>'


def fighter_block(f, name, rank, payload, link=None):
    nick = f'<div class="fc-nickname">"{esc(f["nickname"])}"</div>' if f.get("nickname") else ""
    label = f'<a href="{link}">{esc(name)}</a>' if link else esc(name)
    style = style_text(f)
    style_html = f'<div class="fc-style mono">{esc(style)}</div>' if style else ""
    return (f'<div class="fc-fighter-block">{nick}<div class="fc-fighter">{flag(f, payload)}{rank_chip(rank)}<span>{label}</span></div>'
            f'{style_html}{form_badges(f["fighter_id"], payload)}</div>')


def pick_line_html(win_name, win_p, m, top_m):
    chips = "".join(f'<span class="fc-method-chip{" is-top" if k == top_m else ""}">{METHOD_SHORT[k]} {pct(m[k])}</span>'
                    for k in ("dec", "ko", "sub"))
    return (f'<div class="fc-model-pick mono"><span class="fc-model-pick-label">Model predicts</span> {esc(win_name)} '
            f'<span class="fc-model-pick-pct">{round(win_p * 100)}%</span><div class="fc-method-split">{chips}</div></div>')


def bout_row(b, a, c, payload, inner, link_a=None, link_b=None, extra=""):
    tier = f'<div class="fc-tier-label">{esc(TIER_LABEL[b["tier"]])}</div>' if b.get("tier") in TIER_LABEL else ""
    cls = TIER_ROW_CLASS.get(b.get("tier"), "")
    title = " &middot; Title fight" if b.get("isTitleFight") else ""
    return (f'<div class="fc-row {cls}"><div class="fc-row-header">{tier}<div class="fc-weight mono">{esc(b.get("weightClass") or "")}{title}</div></div>'
            f'<div class="fc-matchup">{fighter_block(a, b["nameA"], b.get("rankA"), payload, link_a)}<div class="fc-vs">vs</div>'
            f'{fighter_block(c, b["nameB"], b.get("rankB"), payload, link_b)}</div>{inner}{extra}</div>')


def tape_row(label, p, predicted=False):
    chip = '<span class="predicted-chip">Predicted</span>' if predicted else ""
    return (f'<div class="tape-row{" predicted" if predicted else ""}"><div class="tape-row-label">{esc(label)}{chip}</div>'
            f'<div class="tape-row-track"><div class="tape-row-fill" style="width:{p * 100:.1f}%"></div></div>'
            f'<div class="tape-row-pct mono">{p * 100:.1f}%</div></div>')


def odds_html(a_name, b_name, r):
    p_a = r["prob_a_wins"]
    m = r["method"]
    ranked = sorted(m.items(), key=lambda kv: -kv[1])
    method_rows = "".join(tape_row(METHOD_NAMES[k], v, i == 0) for i, (k, v) in enumerate(ranked))
    rgf = r.get("round_given_finish") or {}
    p_fin = m["ko"] + m["sub"]
    if rgf:
        top_r = max(rgf, key=rgf.get)
        round_rows = "".join(tape_row(f"Round {k}", v, ranked[0][0] != "dec" and k == top_r) for k, v in sorted(rgf.items()))
    else:
        round_rows = '<div class="tape-row-label" style="color:var(--ink-dim)">Finish probability too low to break down by round.</div>'
    return (f'<div class="fc-predict-breakdown seo-section"><div class="odds-bar">'
            f'<div class="odds-fill odds-fill-a" style="width:{p_a * 100:.1f}%"></div>'
            f'<div class="odds-fill odds-fill-b" style="width:{(1 - p_a) * 100:.1f}%"></div></div>'
            f'<div class="odds-labels"><div class="side-a"><div class="pct mono">{p_a * 100:.1f}%</div><div>{esc(a_name)}</div></div>'
            f'<div class="side-b"><div class="pct mono">{(1 - p_a) * 100:.1f}%</div><div>{esc(b_name)}</div></div></div>'
            f'<div class="tape"><div class="tape-title"><span>Method of Victory</span></div><div>{method_rows}</div></div>'
            f'<div class="tape"><div class="tape-title"><span>Round</span><span class="mono">{round(p_fin * 100)}% chance of a finish</span></div>'
            f'<div>{round_rows}</div></div></div>')


def tott_section(title, sub, rows):
    s = f'<span class="mono">{esc(sub)}</span>' if sub else ""
    body = ""
    for label, x, y, better in rows:
        ca = " tott-better-a" if better == "a" else ""
        cb = " tott-better-b" if better == "b" else ""
        body += (f'<div class="tott-row"><div class="tott-val tott-a{ca}">{esc(x if x is not None else "—")}</div>'
                 f'<div class="tott-label">{esc(label)}</div><div class="tott-val tott-b{cb}">{esc(y if y is not None else "—")}</div></div>')
    return f'<div class="tape"><div class="tape-title"><span>{esc(title)}</span>{s}</div>{body}</div>'


def tale_of_tape(a, c, history, prefight):
    def rec(f):
        h = history.get(f["fighter_id"]) or []
        if h:
            w = sum(1 for x in h if x[1] == "W")
            return f"{w}-{len(h) - w}"
        p = prefight.get(f["fighter_id"])
        return f"Debut ({p['wins']}-{p['losses']} pro)" if p else "Debut"

    def better(x, y, high=True):
        if x is None or y is None or x == y:
            return None
        return "a" if (x > y) == high else "b"

    names = (f'<div class="tott-row tott-names"><div class="tott-val tott-a">{esc(a["name"])}</div><div class="tott-label"></div>'
             f'<div class="tott-val tott-b">{esc(c["name"])}</div></div>')
    tape = tott_section("Tale of the Tape", None, [
        ("UFC record", rec(a), rec(c), None), ("Age", age(a), age(c), None), ("Height", height(a), height(c), None),
        ("Reach", reach(a), reach(c), None), ("Stance", a.get("stance"), c.get("stance"), None)])
    tape = tape.replace('</span></div>', f'</span></div>{names}', 1)

    def stat(label, k, fmt, high=True):
        x, y = a.get(k), c.get(k)
        return (label, fmt(x) if x is not None else None, fmt(y) if y is not None else None, better(x, y, high))
    two = lambda v: f"{v:.2f}"
    striking = tott_section("Striking", "UFC career", [stat("Strikes landed / min", "career_slpm", two),
                                                       stat("Strike accuracy", "career_str_acc", pct),
                                                       stat("Strikes absorbed / min", "career_sapm", two, high=False)])
    grappling = tott_section("Grappling", "UFC career", [stat("Takedowns / 15 min", "career_td_avg", two),
                                                         stat("Takedown accuracy", "career_td_acc", pct),
                                                         stat("Takedown defense", "career_td_def", pct),
                                                         stat("Submission attempts / 15 min", "career_sub_avg", two),
                                                         stat("Control time", "career_ctrl_pct", pct)])
    styles = tott_section("Fighting Style", None, [("Striking", STRIKE.get(a.get("strike_style")) or a.get("style"),
                                                    STRIKE.get(c.get("strike_style")) or c.get("style"), None),
                                                   ("Grappling", GRAPPLE.get(a.get("grapple_style")), GRAPPLE.get(c.get("grapple_style")), None)])
    return f'<div class="seo-section">{tape}{striking}{grappling}{styles}</div>'


def track_record_html(metrics):
    if not metrics:
        return ""
    return (f'<p class="seo-track">Track record: {pct(metrics["accuracy"])} correct on {metrics["n_fights"]:,} UFC fights since '
            f'{metrics["since"][:4]} that the model never trained on, and {pct(metrics["accuracy_confident"])} when it gives '
            f'a fighter 60% or better.</p>')


def og_png(path, event_name, a_name, b_name, pick_line, p_a):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#16130E")
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(str(FONT_DIR / "oswald-700.woff2"), 74)
    mid = ImageFont.truetype(str(FONT_DIR / "barlow-700.woff2"), 40)
    small = ImageFont.truetype(str(FONT_DIR / "barlow-700.woff2"), 30)
    d.text((60, 50), "CALL THE CARD", font=small, fill="#C6963C")
    d.text((60, 100), event_name.upper()[:60], font=small, fill="#A99878")
    title = f"{a_name}  vs  {b_name}"
    while d.textlength(title, font=big) > W - 120 and big.size > 40:
        big = ImageFont.truetype(str(FONT_DIR / "oswald-700.woff2"), big.size - 4)
    d.text((60, 200), title, font=big, fill="#F0E6D2")
    d.text((60, 360), pick_line, font=mid, fill="#F0E6D2")
    if p_a is not None:
        x0, x1, y = 60, W - 60, 450
        split = x0 + int((x1 - x0) * p_a)
        d.rectangle([x0, y, split, y + 26], fill="#D20A0A")
        d.rectangle([split, y, x1, y + 26], fill="#6376E9")
        d.text((x0, y + 40), f"{a_name} {round(p_a * 100)}%", font=small, fill="#D20A0A")
        tb = f"{round((1 - p_a) * 100)}% {b_name}"
        d.text((x1 - d.textlength(tb, font=small), y + 40), tb, font=small, fill="#6376E9")
    img.save(path, optimize=True)


# ---------------------------------------------------------------- written breakdown
FACTOR_PHRASE = {
    "elo_diff": "recent form", "height_in_diff": "height", "reach_in_diff": "reach", "age_years_diff": "the age gap",
    "fights_entering_diff": "UFC experience", "win_pct_entering_diff": "win rate", "finish_rate_entering_diff": "finishing rate",
    "current_streak_entering_diff": "current streak", "layoff_days_entering_diff": "time between fights",
    "sig_str_landed_per_min_diff": "striking output", "sig_str_absorbed_per_min_diff": "absorbing fewer strikes",
    "sig_str_acc_diff": "striking accuracy", "td_avg_per15_diff": "takedown volume", "td_acc_diff": "takedown accuracy",
    "td_def_diff": "takedown defense", "sub_att_per15_diff": "submission threat", "ctrl_pct_diff": "control time",
}
SUFFIXES = {"Jr.", "Jr", "Sr.", "II", "III", "IV"}
KO_METHODS = {"KO/TKO", "TKO - Doctor's Stoppage"}


def last(name):
    p = name.split()
    if len(p) > 2 and p[-1] in SUFFIXES:
        return f"{p[-2]} {p[-1]}"
    return p[-1] if len(p) > 1 else name


def num(n):
    return ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"][n] if 0 <= n < 10 else str(n)


def join_words(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def ufc_wins_by(f, history):
    h = history.get(f["fighter_id"]) or []
    return {"n": len(h), "w": sum(1 for x in h if x[1] == "W"),
            "ko": sum(1 for x in h if x[1] == "W" and x[2] in KO_METHODS),
            "sub": sum(1 for x in h if x[1] == "W" and x[2] == "Submission")}


def form_sentence(nm, f, payload):
    res = (payload.get("recent_results") or {}).get(f["fighter_id"]) or []
    dec = [x for x in res if x["result"] in ("W", "L")]
    if not dec:
        return ""
    first = dec[0]["result"]
    run = 0
    for x in dec:
        if x["result"] != first:
            break
        run += 1
    opps = [x["opponent"] for x in dec[:run]][:2]
    if run >= 2:
        verb = "has won" if first == "W" else "has lost"
        tail = f", most recently over {opps[0]}" if first == "W" else f", most recently to {opps[0]}"
        return f"{nm} {verb} {num(run)} straight{tail}."
    w = sum(1 for x in dec if x["result"] == "W")
    last_one = f"beat {opps[0]}" if first == "W" else f"lost to {opps[0]}"
    return f"{nm} is {w}-{len(dec) - w} over the last {num(len(dec))} and {last_one} last time out."


def band_for(p, metrics):
    for bd in (metrics or {}).get("bands", []):
        if bd["lo"] <= p < bd["hi"]:
            return bd
    return None


def analysis_html(b, a, c, r, payload, metrics, short_ev, ev_date, rounds):
    hist, pre = payload["fighter_history"], payload.get("prefight_records", {})
    na, nc = last(a["name"]), last(c["name"])
    wa, wc_ = ufc_wins_by(a, hist), ufc_wins_by(c, hist)
    secs = []

    # --- the setup
    def who(f, name, rank, w):
        bits = []
        if rank == "C":
            bits.append("the champion")
        elif rank:
            bits.append(f"ranked No. {rank.lstrip('#')}")
        if w["n"]:
            bits.append(f"{w['w']}-{w['n'] - w['w']} in the UFC")
        else:
            p = pre.get(f["fighter_id"])
            bits.append(f"debuting at {p['wins']}-{p['losses']} pro" if p else "debuting")
        return f"{name} ({', '.join(bits)})"
    kind = {"main_event": "main event", "co_main": "co-main event"}.get(b.get("tier"), "bout")
    title = "title " if b.get("isTitleFight") else ""
    s = [f"{who(a, b['nameA'], b.get('rankA'), wa)} faces {who(c, b['nameB'], b.get('rankB'), wc_)} in a "
         f"{num(rounds)}-round {(b.get('weightClass') or '').lower()} {title}{kind} at {short_ev} on {nice_date(ev_date)}."]
    for nm, f in ((na, a), (nc, c)):
        fs = form_sentence(nm, f, payload)
        if fs:
            s.append(fs)
        lf = f.get("last_fight_epoch_days")
        if lf is not None and (hist.get(f["fighter_id"])):
            months = int(((date.today() - date(1970, 1, 1)).days - lf) / 30.44)
            if months >= 12:
                s.append(f"It's {nm}'s first fight in {months} months.")
    ag, cg = age(a), age(c)
    if ag and cg and abs(ag - cg) >= 4:
        s.append(f"{na if ag < cg else nc} is the younger fighter by {abs(ag - cg)} years.")
    ha, hc, ra, rc = a.get("height_in"), c.get("height_in"), a.get("reach_in"), c.get("reach_in")
    h_gap = abs(ha - hc) if ha and hc else 0
    r_gap = abs(ra - rc) if ra and rc else 0
    taller = na if (ha or 0) > (hc or 0) else nc
    longer = na if (ra or 0) > (rc or 0) else nc
    shorter_of = lambda x: nc if x == na else na
    if h_gap >= 2 and r_gap >= 2 and taller == longer:
        s.append(f"{taller} has {h_gap:g} inches of height and {r_gap:g} inches of reach on {shorter_of(taller)}.")
    else:
        if h_gap >= 2:
            s.append(f"{taller} is {h_gap:g} inches taller.")
        if r_gap >= 2:
            s.append(f"{longer} has a {r_gap:g}-inch reach advantage.")
    sa, sc = a.get("stance"), c.get("stance")
    if sa and sc and sa != sc and "Switch" not in (sa, sc):
        art = "an" if sa.lower()[0] in "aeiou" else "a"
        s.append(f"It's {art} {sa.lower()} vs {sc.lower()} matchup.")
    secs.append(("The setup", s))

    # --- on the feet
    s = []
    have = lambda f: f.get("career_slpm") is not None and (hist.get(f["fighter_id"]))
    def pre_line(nm, f):
        p = pre.get(f["fighter_id"])
        wins = [x for x in (p or {}).get("fights", []) if x.get("result") == "win"]
        if not wins:
            return None
        ko = sum(1 for x in wins if re.search(r"KO", x.get("method") or ""))
        sb = sum(1 for x in wins if "Submission" in (x.get("method") or ""))
        return f"{nm} won {len(wins)} fights before the UFC, {ko} by knockout and {sb} by submission."

    if have(a) and have(c):
        s.append(f"{na} lands {a['career_slpm']:.2f} significant strikes per minute at {pct(a['career_str_acc'])} accuracy "
                 f"and absorbs {a['career_sapm']:.2f}. {nc} lands {c['career_slpm']:.2f} at {pct(c['career_str_acc'])} "
                 f"and absorbs {c['career_sapm']:.2f}.")
        da, dc = a["career_slpm"] - a["career_sapm"], c["career_slpm"] - c["career_sapm"]
        if abs(da - dc) >= 0.3:
            hi, lo, dh, dl = (na, nc, da, dc) if da > dc else (nc, na, dc, da)
            s.append(f"That gives {hi} the better striking differential, {dh:+.2f} per minute to {lo}'s {dl:+.2f}.")
        else:
            s.append("Their striking differentials are close, so neither has a clear edge on volume.")
        if a.get("career_str_def") is not None and c.get("career_str_def") is not None and abs(a["career_str_def"] - c["career_str_def"]) >= 0.05:
            hi, lo = (na, nc) if a["career_str_def"] > c["career_str_def"] else (nc, na)
            s.append(f"{hi} is the harder target, avoiding {pct(max(a['career_str_def'], c['career_str_def']))} of strikes "
                     f"to {lo}'s {pct(min(a['career_str_def'], c['career_str_def']))}.")
        kos = [(nm, w["ko"], w["n"]) for nm, w in ((na, wa), (nc, wc_)) if w["ko"] >= 2]
        if kos:
            s.append(" ".join(f"{nm} has {k} knockout wins in {n} UFC fights." for nm, k, n in kos))
        if a.get("strike_style") and c.get("strike_style"):
            if a["strike_style"] == c["strike_style"]:
                s.append(f"By our numbers both are {STRIKE[a['strike_style']].lower()}s." if a["strike_style"] != "Minimal"
                         else "Neither does much on the feet by our numbers.")
            else:
                s.append(f"By our numbers {na} is a {STRIKE[a['strike_style']].lower()} and {nc} a {STRIKE[c['strike_style']].lower()}."
                         .replace("a minimal striking", "light on striking"))
    elif not have(a) and not have(c):
        s.append("Both fighters are making their UFC debuts, so there's no UFC striking data on either. "
                 "The model goes mostly on age, size and record.")
        s += [x for x in (pre_line(na, a), pre_line(nc, c)) if x]
    else:
        (debut, df), (other, of) = ((na, a), (nc, c)) if not have(a) else ((nc, c), (na, a))
        s.append(f"There's no UFC striking data on {debut} yet, so the model goes on age, size and record there.")
        s.append(f"{other} lands {of['career_slpm']:.2f} significant strikes per minute at {pct(of['career_str_acc'])} "
                 f"accuracy and absorbs {of['career_sapm']:.2f}.")
        s += [x for x in (pre_line(debut, df),) if x]
    secs.append(("On the feet", s))

    # --- on the mat
    s = []
    if have(a) and have(c):
        tda, tdc = a.get("career_td_avg") or 0, c.get("career_td_avg") or 0
        if max(tda, tdc) < 1.0:
            s.append(f"Neither leans on wrestling ({tda:.2f} and {tdc:.2f} takedowns per 15 minutes), so this should mostly "
                     f"be fought standing.")
        elif abs(tda - tdc) < 0.6 and max(tda, tdc) < 2.5:
            s.append(f"Both mix in takedowns at a similar rate ({tda:.2f} and {tdc:.2f} per 15 minutes), and "
                     f"{na} stops {pct(a.get('career_td_def') or 0)} of attempts to {nc}'s {pct(c.get('career_td_def') or 0)}.")
        else:
            wr, df_ = (a, c) if tda >= tdc else (c, a)
            nw, nd = (na, nc) if tda >= tdc else (nc, na)
            acc = f" at {pct(wr['career_td_acc'])} accuracy" if wr.get("career_td_acc") is not None else ""
            tdd = (f", and {nd} stops {pct(df_['career_td_def'])} of takedown attempts" if df_.get("career_td_def") is not None else "")
            s.append(f"{nw} brings more of the wrestling, averaging {wr['career_td_avg']:.2f} takedowns per 15 minutes{acc}{tdd}.")
            if df_.get("career_td_def") is not None and df_["career_td_def"] >= 0.75:
                s.append(f"That defense is a real obstacle, so {nw} may have to work hard to get it down.")
            elif df_.get("career_td_def") is not None and df_["career_td_def"] < 0.6:
                s.append(f"{nd} gets taken down often, which plays into {nw}'s hands.")
        sa_, sc_ = a.get("career_sub_avg") or 0, c.get("career_sub_avg") or 0
        if max(sa_, sc_) >= 0.5 or max(wa["sub"], wc_["sub"]) >= 2:
            hi, w_hi, sub_hi = (na, wa, sa_) if (sa_, wa["sub"]) >= (sc_, wc_["sub"]) else (nc, wc_, sc_)
            s.append(f"{hi} carries the bigger submission threat: {sub_hi:.2f} attempts per 15 minutes and "
                     f"{w_hi['sub']} submission win{'s' if w_hi['sub'] != 1 else ''} in the UFC.")
        ca, cc = a.get("career_ctrl_pct"), c.get("career_ctrl_pct")
        if ca is not None and cc is not None and abs(ca - cc) >= 0.15:
            hi, lo = (na, nc) if ca > cc else (nc, na)
            s.append(f"{hi} spends {pct(max(ca, cc))} of fight time in control, to {pct(min(ca, cc))} for {lo}.")
        # record against this opponent's grappling style
        for me, nm, opp in ((a, na, c), (c, nc, a)):
            g = opp.get("grapple_style")
            if g and g not in ("Balanced", "Minimal"):
                h = [x for x in (hist.get(me["fighter_id"]) or []) if len(x) > 9 and x[9] == g]
                if len(h) >= 2:
                    w = sum(1 for x in h if x[1] == "W")
                    s.append(f"Against {GRAPPLE[g].lower()}s, {nm} is {w}-{len(h) - w} in the UFC.")
    elif have(a) or have(c):
        nm, f = (na, a) if have(a) else (nc, c)
        s.append(f"{nm} averages {f.get('career_td_avg') or 0:.2f} takedowns per 15 minutes and stops "
                 f"{pct(f.get('career_td_def') or 0)} of takedown attempts. With the other fighter debuting, "
                 f"there's nothing in the UFC to compare that against yet.")
    else:
        s.append("Neither fighter has UFC grappling numbers yet.")
    secs.append(("On the mat", s))

    # --- how it ends
    s = []
    ma, mc = r.get("method_given_a") or {}, r.get("method_given_b") or {}
    if ma and mc:
        ka, kc = max(ma, key=ma.get), max(mc, key=mc.get)
        pa_, pc_ = METHOD_NAMES[ka].replace("KO/TKO", "knockout").lower(), METHOD_NAMES[kc].replace("KO/TKO", "knockout").lower()
        if ka == kc:
            s.append(f"The likeliest way for either fighter to win is by {pa_}: {pct(ma[ka])} for {na}, {pct(mc[kc])} for {nc}.")
        else:
            s.append(f"{na}'s likeliest path is by {pa_} ({pct(ma[ka])}), while {nc}'s is by {pc_} ({pct(mc[kc])}).")
    pf = r["method"]["ko"] + r["method"]["sub"]
    rgf = r.get("round_given_finish") or {}
    if rgf:
        top = max(rgf, key=rgf.get)
        early = sum(v for k, v in rgf.items() if k <= 2)
        s.append(f"The model gives it a {pct(pf)} chance of ending early. If it does, round {top} is the most likely "
                 f"({pct(rgf[top])} of finishes), and {pct(early)} come in the first two rounds.")
    if pf < 0.45:
        s.append("More often than not, this one goes to the judges.")
    secs.append(("How it ends", s))

    # --- the pick
    s = []
    p_a = r["prob_a_wins"]
    win, lose, p, sign = (na, nc, p_a, 1) if p_a >= 0.5 else (nc, na, 1 - p_a, -1)
    tone = ("close to a coin flip" if p < 0.55 else "a slight lean" if p < 0.6 else "a clear lean" if p < 0.65
            else "a confident pick" if p < 0.7 else "one of the model's stronger calls")
    s.append(f"The model takes {win} at {pct(p)}, {tone}.")
    bd = band_for(p, metrics)
    if bd and bd["n"] >= 50:
        s.append(f"Picks in the {round(bd['lo'] * 100)}-{min(round(bd['hi'] * 100), 100)}% range have been right "
                 f"{pct(bd['accuracy'])} of the time on {bd['n']} UFC fights since 2024.")
    fc = dict(r.get("factor_contribs") or {})
    stance = sum(v for k, v in fc.items() if k.startswith("stance_"))
    fc = {k: v for k, v in fc.items() if k in FACTOR_PHRASE}
    fc["stance"] = stance
    phrase = lambda k: "the stance matchup" if k == "stance" else FACTOR_PHRASE[k]
    pro = [k for k, v in sorted(fc.items(), key=lambda kv: -kv[1] * sign) if v * sign > 0.03][:3]
    con = [k for k, v in sorted(fc.items(), key=lambda kv: kv[1] * sign) if v * sign < -0.03][:2]
    if pro:
        s.append(f"What's pushing it toward {win}: {join_words(phrase(k) for k in pro)}.")
    if con:
        s.append(f"{lose}'s case rests on {join_words(phrase(k) for k in con)}.")
    secs.append(("The pick", s))

    body = "".join(f'<h3 class="seo-h3">{esc(t)}</h3><p class="seo-para">{esc(" ".join(x))}</p>' for t, x in secs if x)
    return f'<!--analysis--><div class="seo-analysis"><div class="tape-title"><span>Breakdown</span></div>{body}</div><!--/analysis-->'


# ---------------------------------------------------------------- pages
def build_event(card, payload, metrics, preds=None, graded=None):
    """preds: {(idA, idB): predict_full result} for an upcoming card; graded:
    the last_results payload bouts for a card that has happened."""
    fb = fighters_by_id(payload)
    hist, pre = payload["fighter_history"], payload.get("prefight_records", {})
    ev_name, ev_date = card["eventName"], card["eventDate"]
    ev_slug = slug(ev_name)
    ev_dir = DOCS / "events" / ev_slug
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_url = f"/events/{ev_slug}/"
    short_ev = ev_name.split(" - ")[0]
    location = card.get("eventLocation")
    when_where = nice_date(ev_date) + (f" · {location}" if location else "")

    bouts = []  # (b, a, c, f_slug, row_inner, summary)
    for b in card["bouts"]:
        a, c = fb.get(b["idA"]), fb.get(b["idB"])
        if not a or not c:
            continue
        f_slug = f"{slug(a['name'])}-vs-{slug(c['name'])}"
        if preds is not None:
            r = preds.get((b["idA"], b["idB"]))
            if not r:
                continue
            p_a = r["prob_a_wins"]
            win, p = (b["nameA"], p_a) if p_a >= 0.5 else (b["nameB"], 1 - p_a)
            top_m = max(r["method"], key=r["method"].get)
            bouts.append((b, a, c, f_slug, r, pick_line_html(win, p, r["method"], top_m)))
        else:
            g = next((x for x in graded if x["idA"] == b["idA"] and x["idB"] == b["idB"]), None)
            if not g:
                continue
            mp = g.get("modelPick") or {}
            winner = b["nameA"] if g["outcome"] == "a" else b["nameB"] if g["outcome"] == "b" else None
            picked = b["nameA"] if mp.get("side") == "a" else b["nameB"] if mp.get("side") == "b" else None
            res = f"{winner} won by {g['method']}, round {g['round']} ({g['time']})" if winner else (g.get("method") or "Draw / no contest")
            verdict = ('<span class="hit">Model was right</span>' if picked and winner and picked == winner
                       else '<span class="miss">Model missed</span>' if picked and winner else "")
            inner = (f'<div class="seo-result">{esc(res)}<br><span class="mono">Model picked {esc(picked or "—")}'
                     f'{" by " + METHOD_NAMES[mp["method"]] if mp.get("method") in METHOD_NAMES else ""}</span> &nbsp;{verdict}</div>')
            bouts.append((b, a, c, f_slug, None, inner))

    # one page per fight
    for i, (b, a, c, f_slug, r, inner) in enumerate(bouts):
        f_dir = ev_dir / f_slug
        f_dir.mkdir(exist_ok=True)
        f_url = f"{SITE}{ev_url}{f_slug}/"
        rounds = 5 if b.get("isFiveRounds") or b.get("tier") == "main_event" or b.get("isTitleFight") else 3
        bout_kind = {"main_event": "main event", "co_main": "co-main event"}.get(b.get("tier"), "fight")
        wc = (b.get("weightClass") or "").lower()
        if r is not None:
            p_a = r["prob_a_wins"]
            win, lose, p = (b["nameA"], b["nameB"], p_a) if p_a >= 0.5 else (b["nameB"], b["nameA"], 1 - p_a)
            top_m = max(r["method"], key=r["method"].get)
            rgf = r.get("round_given_finish") or {}
            when = f" in round {max(rgf, key=rgf.get)}" if top_m != "dec" and rgf else ""
            intro = (f"{b['nameA']} and {b['nameB']} meet in a {rounds}-round {wc} {bout_kind} at {short_ev} on "
                     f"{nice_date(ev_date)}. The model has {win} at {round(p * 100)}%, most likely by {METHOD_NAMES[top_m] if top_m == 'ko' else METHOD_NAMES[top_m].lower()}{when}.")
            desc = (f"{b['nameA']} vs {b['nameB']} prediction for {short_ev}: the model picks {win} ({round(p * 100)}%) over {lose}, "
                    f"most likely by {METHOD_NAMES[top_m]}. Odds, stats and the tale of the tape.")
            details = odds_html(b["nameA"], b["nameB"], r)
            writeup = analysis_html(b, a, c, r, payload, metrics, short_ev, ev_date, rounds)
            og_line, og_p = f"Pick: {win} ({round(p * 100)}%)", p_a
            h1 = f"{b['nameA']} vs {b['nameB']} Prediction"
        else:
            intro = f"{b['nameA']} vs {b['nameB']}, a {wc} {bout_kind} at {short_ev} on {nice_date(ev_date)}."
            desc = f"{b['nameA']} vs {b['nameB']} at {short_ev}: the result, our model's pick and the full stat comparison."
            details, og_line, og_p = "", "Result and model pick", None
            h1 = f"{b['nameA']} vs {b['nameB']}"
            # keep the pre-fight breakdown written when this was the upcoming card
            writeup = ""
            old = f_dir / "index.html"
            if old.exists():
                m_ = re.search(r"<!--analysis-->.*?<!--/analysis-->", old.read_text(encoding="utf-8"), re.S)
                if m_:
                    writeup = m_.group(0).replace("<span>Breakdown</span>", "<span>Pre-fight breakdown</span>")
        others = "".join(f'<a href="{ev_url}{o[3]}/">{esc(o[0]["nameA"])} vs {esc(o[0]["nameB"])}'
                         f'<span class="mono">{esc(o[0].get("weightClass") or "")}</span></a>' for j, o in enumerate(bouts) if j != i)
        body = (f'<div class="results-page-header"><a class="results-back-link" href="{ev_url}">&larr; {esc(ev_name)}</a></div>'
                f'<div class="fc-header"><div class="fc-eyebrow">{esc(short_ev)}</div>'
                f'<h2 class="fc-event-name display seo-title">{esc(h1)}</h2><div class="fc-event-meta mono">{esc(when_where)}</div></div>'
                f'{writeup or f"<p class=seo-intro>{esc(intro)}</p>"}'
                f'{bout_row(b, a, c, payload, inner)}{details}{tale_of_tape(a, c, hist, pre)}{track_record_html(metrics)}'
                f'<div class="seo-section"><div class="tape-title"><span>More from this card</span></div><div class="seo-more">{others}</div></div>')
        jsonld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{b['nameA']} vs {b['nameB']}",
                  "startDate": ev_date, "sport": "Mixed martial arts", "superEvent": {"@type": "SportsEvent", "name": ev_name},
                  "competitor": [{"@type": "Person", "name": b["nameA"]}, {"@type": "Person", "name": b["nameB"]}]}
        if location:
            jsonld["location"] = {"@type": "Place", "name": location}
        og_png(f_dir / "og.png", ev_name, b["nameA"], b["nameB"], og_line, og_p)
        (f_dir / "index.html").write_text(
            page(f"{h1}: {short_ev} | Call the Card", desc, f_url, body, f"{f_url}og.png", jsonld), encoding="utf-8")

    # the event page: the card, in the same layout as the home page
    def rows(sel):
        return "".join(bout_row(b, a, c, payload, inner, f"{ev_url}{fs}/", f"{ev_url}{fs}/",
                                f'<a class="seo-row-cta" href="{ev_url}{fs}/">Full breakdown &rarr;</a>')
                       for b, a, c, fs, r, inner in bouts if b.get("tier") in sel)
    main_ev = rows({"main_event"})
    main_card = rows({"co_main", "main_card"})
    prelims = rows({"featured_prelim", "prelim"})
    card_html = main_ev
    if main_card:
        card_html += f'<div class="fc-group-label">Main Card</div><div class="fc-rows">{main_card}</div>'
    if prelims:
        card_html += f'<div class="fc-group-label">Prelims</div><div class="fc-rows">{prelims}</div>'
    kind = "Predictions" if preds is not None else "Results"
    ev_desc = (f"{short_ev} predictions for every fight ({nice_date(ev_date)}): win odds, method and round for "
               if preds is not None else f"{short_ev} results and how our model's picks did: ")
    ev_desc += ", ".join(f"{b['nameA']} vs {b['nameB']}" for b, *_ in bouts[:3]) + " and the rest of the card."
    body = (f'<div class="fc-header"><div class="fc-eyebrow">{"Predictions" if preds is not None else "Results"}</div>'
            f'<h2 class="fc-event-name display seo-title">{esc(ev_name)}</h2><div class="fc-event-meta mono">{esc(when_where)}</div></div>'
            f'<section class="fight-card">{card_html}</section>{track_record_html(metrics)}')
    (ev_dir / "index.html").write_text(page(f"{short_ev} {kind}: Every Fight | Call the Card", ev_desc, f"{SITE}{ev_url}", body),
                                       encoding="utf-8")
    (ev_dir / "event.json").write_text(json.dumps({"name": ev_name, "date": ev_date, "updated": date.today().isoformat(),
                                                   "fights": len(bouts), "graded": graded is not None}), encoding="utf-8")
    return len(bouts)


def build_index_and_sitemap():
    events = []
    for meta in (DOCS / "events").glob("*/event.json"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        m["slug"] = meta.parent.name
        events.append(m)
    events.sort(key=lambda m: m["date"], reverse=True)
    items = "".join(f'<a href="/events/{m["slug"]}/">{esc(m["name"])}<span class="mono">{nice_date(m["date"])}'
                    f'{" · results" if m["graded"] else " · predictions"}</span></a>' for m in events)
    body = (f'<div class="fc-header"><div class="fc-eyebrow">Archive</div><h2 class="fc-event-name display seo-title">'
            f'UFC Predictions by Event</h2></div><div class="seo-more">{items}</div>')
    (DOCS / "events" / "index.html").write_text(page(
        "UFC Predictions & Picks by Event | Call the Card",
        "Every UFC card we've called: fight-by-fight predictions, win odds and how the model did.",
        f"{SITE}/events/", body), encoding="utf-8")
    today = date.today().isoformat()
    urls = [(f"{SITE}/", today), (f"{SITE}/results.html", today), (f"{SITE}/predict.html", today), (f"{SITE}/events/", today)]
    for m in events:
        urls.append((f"{SITE}/events/{m['slug']}/", m["updated"]))
        for fdir in sorted((DOCS / "events" / m["slug"]).iterdir()):
            if fdir.is_dir() and (fdir / "index.html").exists():
                urls.append((f"{SITE}/events/{m['slug']}/{fdir.name}/", m["updated"]))
    xml = "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
    (DOCS / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>'
                                      f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>', encoding="utf-8")
    (DOCS / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    return len(urls)


def main():
    sys.path.insert(0, str(ROOT))
    import contextlib
    import io

    from src.models.predict import predict_full_by_id

    payload = json.loads((WEB / "model_data.json").read_text(encoding="utf-8"))
    mpath = ROOT / "models" / "artifacts" / "holdout_metrics.json"
    metrics = json.loads(mpath.read_text()) if mpath.exists() else None

    card = payload.get("upcoming_card")
    if card and card.get("bouts"):
        preds = {}
        for b in card["bouts"]:
            if b.get("idA") and b.get("idB"):
                rounds = 5 if b.get("isFiveRounds") else 3
                with contextlib.redirect_stdout(io.StringIO()):  # predict.py prints debut notes
                    preds[(b["idA"], b["idB"])] = predict_full_by_id(b["idA"], b["idB"], scheduled_rounds=rounds,
                                                                     weightclass=b.get("weightClass"))
        n = build_event(card, payload, metrics, preds=preds)
        print(f"seo pages: {card['eventName']} -- {n} fight pages")
    last = payload.get("last_results")
    if last and last.get("bouts"):
        n = build_event({"eventName": last["eventName"], "eventDate": last["eventDate"], "bouts": last["bouts"]},
                        payload, metrics, graded=last["bouts"])
        print(f"seo pages: {last['eventName']} (graded) -- {n} fight pages")
    print(f"sitemap: {build_index_and_sitemap()} urls")


if __name__ == "__main__":
    main()
