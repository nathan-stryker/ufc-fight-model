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


def page(title, description, canonical, body, og_image=None, jsonld=None):
    og = (f'<meta property="og:image" content="{og_image}"><meta name="twitter:image" content="{og_image}">'
          f'<meta name="twitter:card" content="summary_large_image">') if og_image else '<meta name="twitter:card" content="summary">'
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
            og_line, og_p = f"Pick: {win} ({round(p * 100)}%)", p_a
            h1 = f"{b['nameA']} vs {b['nameB']} Prediction"
        else:
            intro = f"{b['nameA']} vs {b['nameB']}, a {wc} {bout_kind} at {short_ev} on {nice_date(ev_date)}."
            desc = f"{b['nameA']} vs {b['nameB']} at {short_ev}: the result, our model's pick and the full stat comparison."
            details, og_line, og_p = "", "Result and model pick", None
            h1 = f"{b['nameA']} vs {b['nameB']}"
        others = "".join(f'<a href="{ev_url}{o[3]}/">{esc(o[0]["nameA"])} vs {esc(o[0]["nameB"])}'
                         f'<span class="mono">{esc(o[0].get("weightClass") or "")}</span></a>' for j, o in enumerate(bouts) if j != i)
        body = (f'<div class="results-page-header"><a class="results-back-link" href="{ev_url}">&larr; {esc(ev_name)}</a></div>'
                f'<div class="fc-header"><div class="fc-eyebrow">{esc(short_ev)}</div>'
                f'<h2 class="fc-event-name display seo-title">{esc(h1)}</h2><div class="fc-event-meta mono">{esc(when_where)}</div></div>'
                f'<p class="seo-intro">{esc(intro)}</p>'
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
