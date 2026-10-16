"""
Static, search-engine-readable pages for every fight and event, plus a
sitemap -- so Google can index "Buckley vs Malott prediction"-type searches.
The main site builds itself in the browser from one big embedded payload, so
Google only ever saw one page; these are plain HTML with the pick, the odds
and the stats written into the page itself.

Writes (under docs/, served by GitHub Pages at callthecard.com):
  events/<event-slug>/index.html                 every pick for the card
  events/<event-slug>/<a>-vs-<b>/index.html      one fight
  events/<event-slug>/<a>-vs-<b>/og.png          1200x630 share image
  events/<event-slug>/event.json                 metadata for the index/sitemap
  events/index.html, sitemap.xml, robots.txt

Upcoming card: pick, win %, method and round odds (predict.py -- the same
numbers the site shows, see check_js_parity). Last week's card: its pages are
rebuilt with the real result and whether the pick was right. Older events'
pages stay as they were.

Run: python -m src.build_seo_pages   (also run at the end of web/build_site.py)
"""
import html
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = "https://callthecard.com"
FONT_DIR = ROOT / "web" / "fonts"
METHOD_NAMES = {"dec": "Decision", "ko": "KO/TKO", "sub": "Submission"}

CSS = """
:root{--canvas:#16130E;--raised:#211A12;--line:#3A2F1F;--ink:#F0E6D2;--dim:#A99878;--red:#D20A0A;--blue:#6376E9;--gold:#C6963C}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--gold)}main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
.brand{font:700 14px/1 system-ui;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);text-decoration:none}
h1{font-size:1.75rem;line-height:1.2;margin:.6rem 0 .3rem}h2{font-size:1.05rem;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:2rem 0 .6rem}
.meta{color:var(--dim);font-size:.92rem}.pick{background:var(--raised);border:1px solid var(--line);padding:16px;margin:1.2rem 0}
.pick strong{font-size:1.25rem}.bar{display:flex;height:10px;margin:.7rem 0 .3rem}.bar span:first-child{background:var(--red)}.bar span:last-child{background:var(--blue)}
.split{display:flex;justify-content:space-between;font-size:.9rem;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:.93rem}td,th{padding:.45rem .3rem;border-bottom:1px solid var(--line);text-align:center}
th{color:var(--dim);font-weight:600;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase}td.a{color:var(--ink)}td.l{color:var(--dim);font-size:.78rem;text-transform:uppercase;letter-spacing:.05em}
.result{border-left:4px solid var(--gold);padding:.5rem .8rem;background:var(--raised);margin:1rem 0}
.cta{display:inline-block;margin-top:1rem;padding:.6rem 1rem;border:1px solid var(--gold);text-decoration:none}
ul.fights{list-style:none;padding:0}ul.fights li{border-bottom:1px solid var(--line);padding:.7rem 0}
.note{color:var(--dim);font-size:.82rem}
"""


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def esc(s):
    return html.escape(str(s), quote=True)


def fighters_by_id(payload):
    f = payload["fighters"]
    return {r[0]: dict(zip(f["fields"], r)) for r in f["rows"]}


def ufc_record(fid, history):
    h = history.get(fid) or []
    w = sum(1 for x in h if x[1] == "W")
    return f"{w}-{len(h) - w}" if h else None


def style_text(f):
    strike = {"Minimal": "Minimal Striking"}.get(f.get("strike_style"), f"{f.get('strike_style')} Striker")
    grapple = {"Submission": "Submission Grappler", "Takedown Defense": "Takedown Defender", "Balanced": "Balanced Grappler",
               "Minimal": "Minimal Grappling"}.get(f.get("grapple_style"), f.get("grapple_style"))
    if f.get("strike_style") and f.get("grapple_style"):
        return f"{strike} · {grapple}"
    return f.get("style")


def age(f):
    d = f.get("dob_epoch_days")
    return int((date.today() - date(1970, 1, 1)).days - d) // 365 if d is not None else None


def height(f):
    h = f.get("height_in")
    return f"{int(h // 12)}'{int(round(h % 12))}\"" if h else None


def reach(f):
    r = f.get("reach_in")
    return f'{r:g}"' if r else None


def pct(x):
    return f"{round(x * 100)}%"


def tape_rows(a, b, history, prefight):
    def rec(f):
        r = ufc_record(f["fighter_id"], history)
        if r:
            return r
        p = prefight.get(f["fighter_id"])
        return f"Debut ({p['wins']}-{p['losses']} pro)" if p else "UFC debut"
    rows = [("UFC record", rec(a), rec(b)), ("Age", age(a), age(b)), ("Height", height(a), height(b)),
            ("Reach", reach(a), reach(b)),
            ("Stance", a.get("stance"), b.get("stance")), ("Style", style_text(a), style_text(b))]
    stats = [("Sig. strikes landed / min", "career_slpm", lambda x: f"{x:.2f}"), ("Striking accuracy", "career_str_acc", pct),
             ("Sig. strikes absorbed / min", "career_sapm", lambda x: f"{x:.2f}"), ("Takedowns / 15 min", "career_td_avg", lambda x: f"{x:.2f}"),
             ("Takedown defense", "career_td_def", pct), ("Submission attempts / 15 min", "career_sub_avg", lambda x: f"{x:.2f}")]
    for label, k, fmt in stats:
        if a.get(k) is not None or b.get(k) is not None:
            rows.append((label, fmt(a[k]) if a.get(k) is not None else None, fmt(b[k]) if b.get(k) is not None else None))
    body = "".join(f'<tr><td class="a">{esc(x if x is not None else "—")}</td><td class="l">{esc(lbl)}</td>'
                   f'<td class="a">{esc(y if y is not None else "—")}</td></tr>' for lbl, x, y in rows)
    return (f'<table><tr><th>{esc(a["name"])}</th><th></th><th>{esc(b["name"])}</th></tr>{body}</table>'
            f'<p class="note">Career stats count official UFC fights only.</p>')


def track_record_html(metrics):
    if not metrics:
        return ""
    return (f'<p class="note">Track record: {pct(metrics["accuracy"])} correct on {metrics["n_fights"]:,} UFC fights since '
            f'{metrics["since"][:4]} that the model never trained on, and {pct(metrics["accuracy_confident"])} when it gives '
            f'a fighter 60% or better.</p>')


def page(title, description, canonical, body, og_image=None, jsonld=None):
    og = f'<meta property="og:image" content="{og_image}"><meta name="twitter:image" content="{og_image}">' if og_image else ""
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Call the Card">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}"><meta name="twitter:card" content="summary_large_image">{og}{ld}
<style>{CSS}</style></head><body><main>
<a class="brand" href="/">Call the Card</a>
{body}
<p><a class="cta" href="/">See this week's full card on Call the Card &rarr;</a></p>
</main></body></html>"""


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


def build_event(card, payload, metrics, preds=None, graded=None):
    """preds: {(idA, idB): predict_full result} for an upcoming card; graded:
    the last_results payload bouts for a card that has happened."""
    fb = fighters_by_id(payload)
    hist, pre = payload["fighter_history"], payload.get("prefight_records", {})
    ev_name, ev_date = card["eventName"], card["eventDate"]
    ev_slug = slug(ev_name)
    ev_dir = DOCS / "events" / ev_slug
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_url = f"{SITE}/events/{ev_slug}/"
    short_ev = ev_name.split(" - ")[0]
    location = card.get("eventLocation")
    items = []
    for b in card["bouts"]:
        a, c = fb.get(b["idA"]), fb.get(b["idB"])
        if not a or not c:
            continue
        f_slug = f"{slug(a['name'])}-vs-{slug(c['name'])}"
        f_dir = ev_dir / f_slug
        f_dir.mkdir(exist_ok=True)
        f_url = f"{ev_url}{f_slug}/"
        rounds = 5 if b.get("isFiveRounds") or b.get("tier") == "main_event" or b.get("isTitleFight") else 3
        title_tag = " (title fight)" if b.get("isTitleFight") else ""
        pick_html, p_a, pick_line, desc, li_extra = "", None, "", "", ""
        if preds is not None:
            r = preds.get((b["idA"], b["idB"]))
            if not r:
                continue
            p_a = r["prob_a_wins"]
            win, lose, p = (a, c, p_a) if p_a >= 0.5 else (c, a, 1 - p_a)
            m = r["method"]
            top_m = max(m, key=m.get)
            rnd = ""
            if top_m != "dec" and r.get("round_given_finish"):
                top_r = max(r["round_given_finish"], key=r["round_given_finish"].get)
                rnd = f" in round {top_r}"
            pick_line = f"Pick: {win['name']} ({round(p * 100)}%)"
            pick_html = (f'<div class="pick"><div class="meta">Model pick</div><strong>{esc(win["name"])} &mdash; {round(p * 100)}%</strong>'
                         f'<div class="bar"><span style="width:{p_a * 100:.1f}%"></span><span style="width:{(1 - p_a) * 100:.1f}%"></span></div>'
                         f'<div class="split"><span>{esc(a["name"])} {round(p_a * 100)}%</span><span>{round((1 - p_a) * 100)}% {esc(c["name"])}</span></div>'
                         f'<p>Most likely result: <b>{METHOD_NAMES[top_m]}</b>{rnd}. Method odds: Decision {pct(m["dec"])}, '
                         f'KO/TKO {pct(m["ko"])}, Submission {pct(m["sub"])}.</p></div>')
            desc = (f"{a['name']} vs {c['name']} prediction for {short_ev} ({ev_date}): our model picks {win['name']} "
                    f"({round(p * 100)}%) over {lose['name']}, most likely by {METHOD_NAMES[top_m]}. Odds, stats and the tale of the tape.")
            li_extra = f" &mdash; pick: <b>{esc(win['name'])}</b> ({round(p * 100)}%, {METHOD_NAMES[top_m]})"
        elif graded is not None:
            g = next((x for x in graded if x["idA"] == b["idA"] and x["idB"] == b["idB"]), None)
            if not g:
                continue
            mp = g.get("modelPick") or {}
            winner = a if g["outcome"] == "a" else c if g["outcome"] == "b" else None
            picked = a if mp.get("side") == "a" else c if mp.get("side") == "b" else None
            res = (f"{winner['name']} won by {g['method']} in round {g['round']} ({g['time']})" if winner
                   else f"{g.get('method') or 'Draw / no contest'}")
            verdict = ("&#10003; Model was right" if picked and winner and picked["fighter_id"] == winner["fighter_id"]
                       else "&#10007; Model missed" if picked and winner else "")
            pick_html = (f'<div class="result"><b>Result:</b> {esc(res)}.<br>Model pick: {esc(picked["name"]) if picked else "—"}'
                         f' ({METHOD_NAMES.get(mp.get("method"), "")}). {verdict}</div>')
            pick_line = f"Result: {winner['name']} won" if winner else "Result"
            desc = (f"{a['name']} vs {c['name']} at {short_ev} ({ev_date}): result, our model's pick and the full stat comparison.")
            li_extra = f" &mdash; {esc(res)} {verdict}"
        h1 = f"{a['name']} vs {c['name']} Prediction"
        body = (f'<h1>{esc(h1)}</h1><p class="meta">{esc(b["weightClass"] or "")}{title_tag} &middot; {rounds} rounds &middot; '
                f'<a href="{ev_url}">{esc(ev_name)}</a> &middot; {esc(ev_date)}{" &middot; " + esc(location) if location else ""}</p>'
                f'{pick_html}<h2>Tale of the tape</h2>{tape_rows(a, c, hist, pre)}{track_record_html(metrics)}'
                f'<h2>More from this card</h2><p><a href="{ev_url}">Every pick for {esc(ev_name)}</a></p>')
        jsonld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{a['name']} vs {c['name']}",
                  "startDate": ev_date, "sport": "Mixed martial arts", "superEvent": {"@type": "SportsEvent", "name": ev_name},
                  "competitor": [{"@type": "Person", "name": a["name"]}, {"@type": "Person", "name": c["name"]}]}
        if location:
            jsonld["location"] = {"@type": "Place", "name": location}
        og_png(f_dir / "og.png", ev_name, a["name"], c["name"], pick_line, p_a)
        (f_dir / "index.html").write_text(
            page(f"{h1}: {short_ev} | Call the Card", desc, f_url, body, f"{f_url}og.png", jsonld), encoding="utf-8")
        items.append(f'<li><a href="{f_url}">{esc(a["name"])} vs {esc(c["name"])}</a> <span class="meta">{esc(b["weightClass"] or "")}</span>{li_extra}</li>')
    kind = "Predictions & Picks" if preds is not None else "Results & Model Picks"
    ev_desc = (f"Every fight on {short_ev} ({ev_date}) with our model's pick, win odds and method: "
               if preds is not None else f"Results for every fight on {short_ev} ({ev_date}) and how our model's picks did: ")
    ev_desc += ", ".join(f"{b['nameA']} vs {b['nameB']}" for b in card["bouts"][:3]) + " and more."
    body = (f'<h1>{esc(ev_name)}: {kind}</h1><p class="meta">{esc(ev_date)}{" &middot; " + esc(location) if location else ""}</p>'
            f'<ul class="fights">{"".join(items)}</ul>{track_record_html(metrics)}')
    (ev_dir / "index.html").write_text(page(f"{short_ev} {kind}: Every Fight | Call the Card", ev_desc, ev_url, body), encoding="utf-8")
    (ev_dir / "event.json").write_text(json.dumps({"name": ev_name, "date": ev_date, "updated": date.today().isoformat(),
                                                   "fights": len(items), "graded": graded is not None}), encoding="utf-8")
    return len(items)


def build_index_and_sitemap():
    events = []
    for meta in (DOCS / "events").glob("*/event.json"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        m["slug"] = meta.parent.name
        events.append(m)
    events.sort(key=lambda m: m["date"], reverse=True)
    items = "".join(f'<li><a href="{SITE}/events/{m["slug"]}/">{esc(m["name"])}</a> <span class="meta">{m["date"]}'
                    f'{" &middot; results" if m["graded"] else " &middot; predictions"}</span></li>' for m in events)
    (DOCS / "events" / "index.html").write_text(page(
        "UFC Predictions & Picks by Event | Call the Card",
        "Every UFC card we've called: fight-by-fight predictions, win odds and how the model did.",
        f"{SITE}/events/", f'<h1>UFC predictions by event</h1><ul class="fights">{items}</ul>'), encoding="utf-8")
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

    payload = json.loads((ROOT / "web" / "model_data.json").read_text(encoding="utf-8"))
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
