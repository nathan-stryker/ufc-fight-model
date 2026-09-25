"""
Audit every fighter on this week's card: compares everything the site shows
(web/model_data.json -- the exact payload the page renders) against two
outside sources, and reports every mismatch and every field that couldn't be
checked. Nothing is marked OK unless an outside source agrees.

Sources:
  - UFC.com athlete pages (slugs taken from the event page's own links):
    pro record, career stat block, height/reach/age bio, 3 most recent fights,
    and the country UFC lists next to each fighter on the event page.
  - Sherdog fighter pages: nationality, DOB, height, full pro fight history
    (UFC fights = events named UFC... / The Ultimate Fighter...).
  UFCStats itself now serves a bot-check page to scripts, so it isn't used.

Run: python -m src.audit_card   (~7 min: UFC.com's crawl-delay is 15s)
Writes: data/processed/card_audit.csv (one row per check)
"""
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.data.scrape_prefight_history import MANUAL_SHERDOG_URLS, parse_fight_history

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal MMA-stats research script)"}
UFC_DELAY, SHERDOG_DELAY = 15.0, 1.0
FINISH_METHODS = {"KO/TKO", "Submission", "TKO - Doctor's Stoppage"}
COUNTRY_TO_ISO = None  # filled from fighter_nationality.csv's own name->iso pairs


CACHE_DIR = PROCESSED_DIR / ".audit_cache"


def get(session, url, delay):
    """Same-day disk cache, so a rerun doesn't re-crawl at UFC.com's 15s pace."""
    import hashlib
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{date.today()}_{hashlib.md5(url.encode()).hexdigest()}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    time.sleep(delay)
    r = session.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")
    return r.text


# ---------------------------------------------------------------- UFC.com
def ufc_event(session):
    html = get(session, "https://www.ufc.com/events", UFC_DELAY)
    m = re.search(r'href="(/event/[^"]+)"', html)
    html = get(session, "https://www.ufc.com" + m.group(1), UFC_DELAY)
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for f in soup.select(".c-listing-fight"):
        slugs = []
        for a in f.select("a[href*='/athlete/']"):
            s = a["href"].rstrip("/").split("/athlete/")[-1]
            if s not in slugs:
                slugs.append(s)
        countries = [c.get_text(" ", strip=True) for c in f.select(".c-listing-fight__country-text")]
        names = [n.get_text(" ", strip=True) for n in f.select(".c-listing-fight__corner-name")]
        out.append({"slugs": slugs, "countries": countries, "names": names})
    return out


def _num(s):
    m = re.search(r"-?\d+(\.\d+)?", s or "")
    return float(m.group(0)) if m else None


def ufc_athlete(session, slug):
    soup = BeautifulSoup(get(session, f"https://www.ufc.com/athlete/{slug}", UFC_DELAY), "html.parser")
    d = {}
    rec = soup.select_one(".hero-profile__division-body")
    m = re.search(r"(\d+)-(\d+)-(\d+)", rec.get_text() if rec else "")
    d["pro_record"] = tuple(int(x) for x in m.groups()) if m else None
    for g in soup.select(".c-stat-compare__group"):
        t = g.get_text(" ", strip=True).lower()
        v = _num(t)
        for key, pat in [("slpm", "sig. str. landed"), ("sapm", "sig. str. absorbed"), ("td_avg", "takedown avg"),
                         ("sub_avg", "submission avg"), ("str_def", "sig. str. defense"), ("td_def", "takedown defense")]:
            if pat in t:
                d[key] = v / 100 if key in ("str_def", "td_def") and v is not None else v
    for g in soup.select(".e-chart-circle__wrapper"):
        t = g.get_text(" ", strip=True).lower()
        if "striking accuracy" in t:
            d["str_acc"] = _num(t) / 100
        if "takedown accuracy" in t:
            d["td_acc"] = _num(t) / 100
    for g in soup.select(".c-overlap__stats"):
        t = g.get_text(" ", strip=True).lower()
        for key, pat in [("sig_landed", "sig. strikes landed"), ("sig_att", "sig. strikes attempted"),
                         ("td_landed", "takedowns landed"), ("td_att", "takedowns attempted")]:
            if pat in t:
                d[key] = _num(t.split(pat)[-1])
    for f in soup.select("div.c-bio__field"):
        lab, txt = f.select_one(".c-bio__label"), f.select_one(".c-bio__text")
        if lab and txt:
            d["bio_" + lab.get_text(strip=True).lower()] = txt.get_text(strip=True)
    fights = []
    for c in soup.select(".c-card-event--athlete-results"):
        t = c.get_text(" | ", strip=True)
        dm = re.search(r"([A-Z][a-z]{2})\.? (\d{1,2}), (\d{4})", t)
        fights.append({"text": t, "date": datetime.strptime(" ".join(dm.groups()), "%b %d %Y").date() if dm else None})
    d["recent"] = fights
    return d


# ---------------------------------------------------------------- Sherdog
def sherdog(session, url):
    html = get(session, url, SHERDOG_DELAY)
    soup = BeautifulSoup(html, "html.parser")
    d = {"url": url}
    nat = soup.select_one('strong[itemprop="nationality"]')
    d["nationality"] = nat.get_text(strip=True) if nat else None
    text = soup.get_text(" ", strip=True)
    m = re.search(r"AGE\s+\d+\s*/\s*([A-Z][a-z]{2} \d{1,2}, \d{4})", text)
    d["dob"] = datetime.strptime(m.group(1), "%b %d, %Y").date() if m else None
    m = re.search(r"HEIGHT\s+\d+'\s*\d+\"\s*/\s*([\d.]+)\s*cm", text)
    d["height_in"] = round(float(m.group(1)) / 2.54, 1) if m and float(m.group(1)) > 0 else None
    fights = parse_fight_history(html)
    for f in fights:
        ev = f["event"] or ""
        f["is_ufc"] = bool(re.match(r"(UFC|The Ultimate Fighter)", ev)) and "Contender" not in ev and "Road to UFC" not in ev
        f["event_date"] = f["event_date"].date()
    d["fights"] = sorted(fights, key=lambda f: f["event_date"], reverse=True)
    return d


# ---------------------------------------------------------------- compare
def last_name(s):
    parts = [p for p in re.sub(r"[^A-Za-z\s-]", "", s or "").lower().split() if p not in ("jr", "sr", "ii", "iii", "iv")]
    return parts[-1] if parts else ""


def method_cat(m):
    m = (m or "").lower()
    if "draw" in m:  # Sherdog "Draw (Majority)" == UFCStats "Decision - Majority" on a drawn fight
        return "DEC"
    if "no contest" in m or "overturned" in m or "could not continue" in m:
        return "NC"
    if "submission" in m:
        return "SUB"
    if "ko" in m or "doctor" in m:
        return "KO"
    if "decision" in m:
        return "DEC"
    if "dq" in m or "disqualification" in m:
        return "DQ"
    return m or None


def main():
    global COUNTRY_TO_ISO
    payload = json.loads((ROOT / "web" / "model_data.json").read_text(encoding="utf-8"))
    fields = payload["fighters"]["fields"]
    fighters = {r[0]: dict(zip(fields, r)) for r in payload["fighters"]["rows"]}
    hist, recent, pre = payload["fighter_history"], payload["recent_results"], payload["prefight_records"]
    nat = pd.read_csv(PROCESSED_DIR / "fighter_nationality.csv")
    COUNTRY_TO_ISO = {n.lower(): i for n, i in zip(nat["nationality"], nat["iso_code"]) if isinstance(n, str)}
    sherdog_by_id = dict(zip(nat["fighter_id"], nat["sherdog_url"]))

    session = requests.Session()
    ufc_bouts = ufc_event(session)
    card = payload["upcoming_card"]["bouts"]
    today = date.today()

    checks = []

    def check(name, field, ours, theirs, source, status, note=""):
        checks.append({"fighter": name, "field": field, "ours": ours, "theirs": theirs,
                       "source": source, "status": status, "note": note})
        print(f"  [{status:9}] {field}: ours={ours} | {source}={theirs} {note}", flush=True)

    for bi, bout in enumerate(card):
        ub = ufc_bouts[bi] if bi < len(ufc_bouts) else {"slugs": [], "countries": [], "names": []}
        for side in ("A", "B"):
            fid, card_name = bout[f"id{side}"], bout[f"name{side}"]
            f = fighters.get(fid)
            print(f"\n=== {card_name} ({fid})", flush=True)
            if f is None:
                check(card_name, "fighter row", None, None, "-", "MISSING", "not in site payload")
                continue
            name = f["name"]
            k = 0 if side == "A" else 1
            slug = ub["slugs"][k] if len(ub["slugs"]) > k else None
            h = hist.get(fid, [])

            # ---- sources
            try:
                u = ufc_athlete(session, slug) if slug else None
            except Exception as e:
                u = None
                check(name, "UFC.com page", slug, str(e), "ufc.com", "UNCHECKED")
            surl = sherdog_by_id.get(fid)
            if not (isinstance(surl, str) and surl.startswith("http")):
                surl = MANUAL_SHERDOG_URLS.get(card_name.lower()) or MANUAL_SHERDOG_URLS.get(name.lower())
            if not surl:  # Sherdog's own name search; the DOB check below catches a wrong-person match
                from src.data.scrape_nationality import find_sherdog_url
                for q in dict.fromkeys([name, card_name, " ".join(reversed(name.split())),
                                        " ".join(reversed(ub["slugs"][k].split("-"))) if len(ub["slugs"]) > k else name]):
                    try:
                        surl = find_sherdog_url(session, q)
                    except Exception:
                        surl = None
                    if surl:
                        break
            try:
                s = sherdog(session, surl) if surl else None
            except Exception as e:
                s = None
                check(name, "Sherdog page", surl, str(e), "sherdog", "UNCHECKED")
            if s is None and not surl:
                check(name, "Sherdog page", None, None, "sherdog", "UNCHECKED", "no Sherdog URL on file")

            # ---- identity: Sherdog DOB vs ours (guards against wrong-person matches)
            our_dob = date.fromordinal(date(1970, 1, 1).toordinal() + int(f["dob_epoch_days"])) if f["dob_epoch_days"] is not None else None
            if s and s["dob"]:
                check(name, "DOB", our_dob, s["dob"], "sherdog", "OK" if our_dob == s["dob"] else ("GAP" if our_dob is None else "MISMATCH"))
            else:
                check(name, "DOB", our_dob, None, "sherdog", "UNCHECKED")
            our_age = (today - our_dob).days // 365.25 if our_dob else None
            if u and u.get("bio_age"):
                ua = int(_num(u["bio_age"]))
                check(name, "Age", our_age, ua, "ufc.com", "OK" if our_age is not None and abs(our_age - ua) <= 1 else ("GAP" if our_age is None else "MISMATCH"),
                      "(off by 1 is a birthday-timing difference)" if our_age is not None and abs(our_age - ua) == 1 else "")

            # ---- nationality
            our_iso = f.get("iso_code")
            srcs = []
            if s and s["nationality"]:
                srcs.append(("sherdog", s["nationality"]))
            if len(ub["countries"]) > k and ub["countries"][k]:
                srcs.append(("ufc.com card", ub["countries"][k]))
            for src, country in srcs:
                iso = COUNTRY_TO_ISO.get(country.lower())
                check(name, "Flag/nationality", our_iso, f"{country} ({iso})", src,
                      "OK" if iso and iso == our_iso else ("GAP" if not our_iso else "MISMATCH"))
            if not srcs:
                check(name, "Flag/nationality", our_iso, None, "-", "UNCHECKED")

            # ---- physical
            for fld, key in [("Height", "height_in"), ("Reach", "reach_in")]:
                ours = f[key]
                theirs = _num(u.get(f"bio_{fld.lower()}")) if u else None
                if theirs:
                    check(name, fld, ours, theirs, "ufc.com", "OK" if ours is not None and abs(ours - theirs) <= 0.5 else ("GAP" if ours is None else "MISMATCH"))
                elif fld == "Height" and s and s["height_in"]:
                    check(name, fld, ours, s["height_in"], "sherdog", "OK" if ours is not None and abs(ours - s["height_in"]) <= 1 else ("GAP" if ours is None else "MISMATCH"))
                else:
                    check(name, fld, ours, None, "-", "GAP" if ours is None else "UNCHECKED", "no outside source lists it")
            check(name, "Stance", f["stance"], None, "-", "GAP" if not f["stance"] else "UNCHECKED",
                  "UFC.com/Sherdog don't list stance")

            # ---- records
            if h:
                ow = sum(1 for x in h if x[1] == "W"); ol = len(h) - ow
                if s:
                    sf = [x for x in s["fights"] if x["is_ufc"]]
                    sw = sum(1 for x in sf if x["result"] == "win"); sl = sum(1 for x in sf if x["result"] == "loss")
                    sd = sum(1 for x in sf if x["result"] in ("draw", "nc"))
                    check(name, "UFC record (W-L)", f"{ow}-{ol}", f"{sw}-{sl}" + (f" (+{sd} draw/NC)" if sd else ""), "sherdog",
                          "OK" if (ow, ol) == (sw, sl) else "MISMATCH")
                    # fight-by-fight, matched by date (one UFC fight per date;
                    # opponent spellings differ, e.g. "Aoriqileng" / "Qileng Aori")
                    ours_by_date = {x[5]: x for x in h}
                    s_by_date = {str(x["event_date"]): x for x in sf}
                    for d_, x in s_by_date.items():
                        if x["result"] in ("win", "loss"):
                            o = ours_by_date.get(d_)
                            if o is None:
                                check(name, "Missing UFC fight", None, f"{d_} {x['result']} vs {x['opponent_name']} ({x['event']})", "sherdog", "MISMATCH")
                            elif o[1] != x["result"][0].upper():
                                check(name, "UFC fight result", f"{d_} {o[1]} vs {o[6]}", f"{x['result']} vs {x['opponent_name']}", "sherdog", "MISMATCH")
                    for d_, x in ours_by_date.items():
                        if d_ not in s_by_date:
                            check(name, "Extra UFC fight", f"{d_} {x[1]} vs {x[6]} ({x[4]})", None, "sherdog", "MISMATCH", "in ours, not Sherdog's UFC list")
                    # form badges (last 5 incl. draws/NC)
                    for i, (o, t) in enumerate(zip(recent.get(fid, []), sf[:5])):
                        ok = o["result"][0].upper() == {"win": "W", "loss": "L", "draw": "D", "nc": "N"}.get(t["result"], "?") and \
                            method_cat(o["method"]) == method_cat(t["method_raw"]) and str(o["round"]) == str(t["round"])
                        check(name, f"Form badge {i + 1}", f"{o['result']} {o['opponent']} {o['method']} R{o['round']}",
                              f"{t['result']} {t['opponent_name']} {t['method_raw']} R{t['round']}", "sherdog", "OK" if ok else "MISMATCH")
                    # last fight date
                    if sf:
                        our_last = date.fromordinal(date(1970, 1, 1).toordinal() + int(f["last_fight_epoch_days"]))
                        check(name, "Last UFC fight date", our_last, sf[0]["event_date"], "sherdog", "OK" if our_last == sf[0]["event_date"] else "MISMATCH")
                    # finish rate
                    ofin = sum(1 for x in h if x[1] == "W" and x[2] in FINISH_METHODS)
                    sfin = sum(1 for x in sf if x["result"] == "win" and method_cat(x["method_raw"]) in ("KO", "SUB"))
                    check(name, "UFC finishes (of wins)", f"{ofin}/{ow}", f"{sfin}/{sw}", "sherdog", "OK" if (ofin, ow) == (sfin, sw) else "MISMATCH")
                if u and u["recent"]:
                    # fighter_history holds wins/losses only; draws and no-contests live in the form badges
                    badge_opps = {last_name(o["opponent"]) for o in recent.get(fid, [])}
                    for x in u["recent"][:3]:
                        in_ours = any(y[5] == str(x["date"]) for y in h) or \
                            any(p in badge_opps for p in (last_name(t) for t in x["text"].split(" | ")[:4]))
                        check(name, "UFC.com recent fight present", None, x["text"][:90], "ufc.com", "OK" if in_ours else "MISMATCH")
            else:
                p = pre.get(fid)
                ours = f"{p['wins']}-{p['losses']}" if p else None
                if u and u["pro_record"]:
                    w, l, d_ = u["pro_record"]
                    check(name, "Pro record (debut)", ours, f"{w}-{l}-{d_}", "ufc.com",
                          "OK" if p and (p["wins"], p["losses"]) == (w, l) else ("GAP" if not p else "MISMATCH"),
                          "UFC.com counts Contender Series" if p and (p["wins"], p["losses"]) != (w, l) else "")

            # ---- career stats vs UFC.com's stat block
            # Non-UFC fights UFC.com's stat block counts but UFCStats doesn't:
            # Contender Series and Road to UFC tournament rounds.
            dwcs = [f"{'Road to UFC' if 'Road to UFC' in x['event'] else 'Contender Series'} {x['event_date']}"
                    for x in (s["fights"] if s else []) if re.search(r"Contender|Road to UFC", x["event"] or "")]
            if u:
                for fld, ours_key, ukey, tol in [
                    ("Strikes landed/min", "career_slpm", "slpm", 0.02), ("Strikes absorbed/min", "career_sapm", "sapm", 0.02),
                    ("Strike accuracy", "career_str_acc", "str_acc", 0.01), ("Strike defense", "career_str_def", "str_def", 0.01),
                    ("Takedowns/15", "career_td_avg", "td_avg", 0.02), ("Takedown accuracy", "career_td_acc", "td_acc", 0.01),
                    ("Takedown defense", "career_td_def", "td_def", 0.01), ("Sub attempts/15", "career_sub_avg", "sub_avg", 0.02)]:
                    ours, theirs = f.get(ours_key), u.get(ukey)
                    if theirs is None:
                        check(name, fld, ours, None, "ufc.com", "UNCHECKED" if ours is not None else "OK", "UFC.com shows no value")
                        continue
                    if ours is None:
                        if not h:  # UFC debut: UFC.com's numbers are from Contender Series fights
                            check(name, fld, None, theirs, "ufc.com", "NOTE", "debut -- UFC.com's number is from Contender Series, not UFC")
                        else:
                            check(name, fld, None, theirs, "ufc.com", "GAP")
                        continue
                    ok = abs(ours - theirs) <= tol + 1e-9
                    note = ""
                    if not ok and dwcs:
                        note = f"UFC.com also counts non-UFC fights ({', '.join(dwcs)})"
                    if not ok and ukey == "td_acc" and u.get("td_avg") is not None and f.get("career_td_avg") is not None \
                            and abs(u["td_avg"] - f["career_td_avg"]) <= 0.02:
                        note = ("UFC.com's own takedowns/15 matches ours, so its takedown-landed count "
                                f"({u.get('td_landed')}/{u.get('td_att')}) contradicts itself -- UFC.com widget error")
                    check(name, fld, round(ours, 3), theirs, "ufc.com", "OK" if ok else ("EXPLAINED" if note else "MISMATCH"), note)
                if u.get("td_att") and u.get("td_landed") is not None:
                    check(name, "Takedown accuracy (UFC.com raw counts)", f.get("career_td_acc"),
                          f"{int(u['td_landed'])}/{int(u['td_att'])} = {u['td_landed'] / u['td_att']:.2f}", "ufc.com", "INFO")
            check(name, "Control time", f.get("career_ctrl_pct"), None, "-", "UNCHECKED", "no outside source shows control %")
            check(name, "Recent form (Elo)", f.get("elo"), None, "-", "INFO", "our own rating; nothing external to compare")

    out = pd.DataFrame(checks)
    out.to_csv(PROCESSED_DIR / "card_audit.csv", index=False)
    print("\n\nSUMMARY")
    print(out["status"].value_counts().to_string())
    print(f"wrote {PROCESSED_DIR / 'card_audit.csv'}")


if __name__ == "__main__":
    main()
