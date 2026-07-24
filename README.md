# UFC Fight Model

Predicts the winner, method of victory, and round of a UFC fight with
gradient-boosted (XGBoost) models trained on historical fighter stats, Elo
ratings, and a favorite/underdog method-matchup heuristic.

**Data source**: UFCStats.com now blocks scrapers with a bot-detection
challenge, so this project uses the actively-maintained public mirror at
[github.com/Greco1899/scrape_ufc_stats](https://github.com/Greco1899/scrape_ufc_stats)
(GPL-3.0) instead of scraping directly. Its raw CSVs live in `data/raw/` --
re-download them periodically to pick up new events.

## Setup

```
pip install -r requirements.txt
```

## Website ("Call the Card")

`web/` contains a fully client-side matchup predictor -- it re-implements the
XGBoost tree-ensemble inference, the Elo-logreg blend, and the method/round
marginalization logic directly in JavaScript (`web/engine.js`), so predictions
run entirely in the browser with no server and no data leaving the page.

To rebuild it after retraining:
```
python -m src.export_web_model   # strips models + fighter data to web/model_data.json
python web/build_site.py         # assembles web/site.html AND docs/index.html (template + engine.js + model data + ui.js)
```
`web/site.html` / `docs/index.html` are identical, self-contained files (~1.7MB)
-- everything (model, fighter data, fonts, flags, JS) is inlined, so either
one can be opened directly or hosted anywhere with zero build step. They were
verified against `predict.py` for several matchups (exact match to the
decimal) before publishing -- see the "best_iteration truncation" note below,
which was a real bug caught during that verification.

### Deployment

The site is published two ways, both driven by the same `build_site.py` output:

- **Claude Artifact** -- `web/site.html` republished via the `Artifact` tool to
  a stable URL (`https://claude.ai/code/artifact/37135e89-...`), private by
  default until shared.
- **GitHub Pages** -- `docs/index.html` served publicly at
  **https://nathan-stryker.github.io/ufc-fight-model/** from the
  [nathan-stryker/ufc-fight-model](https://github.com/nathan-stryker/ufc-fight-model)
  repo (public), Pages configured to build from `docs/` on `master`. Pushing to
  `master` *usually* auto-rebuilds Pages in ~1-2 minutes -- no separate deploy
  step needed in the common case.
  `data/raw/`, `data/processed/`, and `models/artifacts/` stay gitignored (large,
  regenerable); only source, `web/`, and `docs/index.html` are committed. The
  weekly scheduled refresh (`ufc-fight-model-refresh`) pushes to this repo
  automatically after a successful retrain, keeping both copies in sync.

  **Gotcha, caught for real**: a push does NOT reliably auto-trigger a Pages
  rebuild -- one push landed cleanly (`git status` clean, commit visible on
  GitHub) with no new Pages build at all, so the live site kept serving the
  previous version. Always verify after pushing: check
  `gh api repos/nathan-stryker/ufc-fight-model/pages/builds/latest` for a
  build matching the pushed commit SHA; if it's still pinned to an older
  commit after ~60-90s, manually kick one with
  `gh api -X POST repos/nathan-stryker/ufc-fight-model/pages/builds`. The
  scheduled weekly refresh does this verification automatically now -- see
  its task prompt (`ufc-fight-model-refresh`) for the exact steps.

### This week's card (home page)

The home page shows the next upcoming UFC event's full fight card, each bout
with a **Call This Fight** button that auto-fills both corners and runs the
prediction in one click. Data comes from `src/data/scrape_upcoming_card.py`
(same Sherdog.com source as fighter nationality, checked again for this
feature: unrestricted robots.txt), which finds the soonest event on Sherdog's
UFC organization page and scrapes its bout list (fighter names + weight
class) at build time -- not fetched live in-browser, since this is a static
site with no server and Artifact's CSP blocks cross-origin fetches anyway.

Rebuild/refresh with:
```
python -m src.data.scrape_upcoming_card   # writes data/processed/upcoming_card.csv
python -m src.export_web_model            # embeds it into web/model_data.json
python web/build_site.py
```

Each scraped fighter is matched to our own `fighters.csv` by **exact
normalized name only** -- deliberately no fuzzy fallback, unlike the
one-time manual nationality backlog: this runs unattended every week with no
one to sanity-check individual guesses, so a wrong-but-plausible match is a
worse outcome than just showing "No prediction available" for that bout. A
genuine UFC debutant is expected to miss too (no fight history in our data
at all, so there'd be nothing to predict from regardless). A small
hand-verified `NAME_ALIASES` dict in the script exists for the rare case of a
real, confirmed spelling mismatch between Sherdog and our data (same trust
model as `manual_nationality_overrides.py` -- a human decided the pairing is
correct, not an algorithm guessing).

**Real gap found and fixed while building this**: the site's fighter picker
is active-roster-only (fought in the last 24 months -- see "Fighter
portraits" below), which is normally reasonable, but a fighter returning from
a genuine multi-year injury/contract layoff can be booked on a real card
while failing that window. On the first real card scraped (UFC Fight Night
282), 6 of 13 bouts had a fighter matched by name but silently missing from
the exported roster for exactly this reason -- their "Call This Fight"
button would have crashed on click. Fixed in `export_web_model.py`'s
`export_fighters()`: the active-window filter now has an explicit exception
that always keeps any fighter appearing in `upcoming_card.csv`, regardless of
how long ago their *previous* fight was -- being booked on the next card is
unambiguously current. Verified after the fix: 12 of 13 bouts on that card
became fully clickable (the 13th was a genuine name mismatch, not this bug).

**How to apply**: if this ever regresses (a "Call This Fight" button crashes,
or a bout that should be predictable shows "No prediction available"), check
this exception first -- don't just widen `ACTIVE_WINDOW_MONTHS` globally,
since that constant intentionally keeps the general search box from bloating
with fighters nobody would currently book.

**"Model Predicts" line, added 2026-07-23**: every predictable bout on the
card also shows the model's own top-line call (e.g. "Model predicts Magomed
Ankalaev by Decision") without needing to click "Call This Fight" first --
`ui.js` runs `predictFull()` for each bout up front at render time and
derives the headline via `verdictText()`, the same helper the full results
panel's verdict line uses (extracted specifically so the two can never
disagree -- see `renderResult()`). No scheduled-rounds data comes from
Sherdog's card listing, so this assumes 5 rounds for the main event and 3
for everything else (standard UFC convention); "Call This Fight" still opens
the full predictor where the round toggle can be corrected by hand for a
5-round co-main or similar exception.

**Tiered poster layout, added 2026-07-23**: user feedback -- the original
flat list of 13 identical rows didn't read like a real fight card. Redesigned
into main event (standalone, gold-outlined) -> rest of main card (co-main
called out in silver) -> prelims (featured prelim called out in bronze),
matching how a real UFC poster is laid out. First shipped with tier assigned
**positionally** (`assign_tiers()`, a fixed `MAIN_CARD_SIZE = 5` constant
marking where "main card" ends and "prelims" begins), per the user's own
initial preference for the simpler approach over scraping ufc.com's explicit
segment labels.

**Real segment data + title fights, added 2026-07-23 (same day, follow-up)**:
the user flagged the positional guess themselves as a known gap ("it is not
always 5 fights on a main card") and asked for a belt icon on title fights,
with the co-main staying **gold** instead of silver when it's *also* a title
fight (a real scenario -- some cards run two title fights). Confirmed live
while building this: the very next UFC card at the time had **6** main-card
bouts, not 5 -- the fixed constant really was silently wrong for a real card,
not just a hypothetical edge case.

Fixed by switching to ufc.com as the primary source for bout list + tiering
(Sherdog remains the source for event discovery/name/date/location, already
vetted and unchanged). `scrape_card_ufc_com()` in `scrape_upcoming_card.py`
reads the real `id="main-card"`/`id="prelims-card"`/`id="early-prelims"`
segment containers (each holding `.c-listing-fight` blocks with
`.c-listing-fight__corner-name--red`/`--blue` names and a
`.c-listing-fight__class-text` weight-class string) and derives tier from
actual segment membership + position within it (index 0 of main-card = main
event, index 1 = co-main, index 0 of prelims = featured prelim -- same
prominence-descending-order logic as before, just applied to the real
segment instead of one long guessed list). `is_title_fight` comes from the
weight-class text containing "Title" (e.g. "Welterweight Title Bout" vs a
plain "Light Heavyweight Bout") -- confirmed against a real two-title card
(UFC 330: Makhachev's welterweight title defense plus a women's strawweight
title co-main) before shipping.

ufc.com's segment containers are only reliably populated once an event is
close to fight week -- a distant future PPV can go months with only a flat
"how to watch" bout list and no main-card/prelims split yet. Handled with a
graceful fallback chain: if ufc.com's event page doesn't parse, its parsed
date doesn't match the Sherdog event being looked up (guards against
silently mixing two different events' data), or its main-card segment comes
back empty, `scrape_upcoming_card.py` falls back to the original
Sherdog-only scrape + positional `assign_tiers()` heuristic so the card still
ships, just without real segment/title data for that one week -- same
degrade-gracefully philosophy as the flag scraper.

Frontend: `ui.js`'s `renderUpcomingCard()` renders a small inline SVG belt
icon (colored via `--gold`, not an emoji) next to the weight-class label for
any `isTitleFight` bout, and a co-main row gets a second CSS class
(`fc-row--co-main-title`) that overrides the usual silver border/wash with
gold when `isTitleFight` is also true (`site_template.html`, source-order
override, same specificity as the base `.fc-row--co-main` rule).

**How to apply**: `MAIN_CARD_SIZE` in `scrape_upcoming_card.py` still exists
but is fallback-only now -- don't "fix" a wrong tier by adjusting it unless
the fallback path is actually the one that fired that week (check the
printed `source:` line from `python -m src.data.scrape_upcoming_card`). If
ufc.com's HTML structure changes (class names, container ids), that's the
first thing to check for a future "wrong tiers again" report -- it was
verified against real live pages while building this but is inherently more
fragile than Sherdog's cleaner itemprop microdata.

**Recent-form W/L badges, added 2026-07-23 (same day, follow-up)**: user
asked for a fun addition -- up to the last 5 UFC results per fighter on the
card, as a hoverable badge showing who they beat/lost to. Entirely derived
from `fights.csv`, already sitting in our processed data -- no new scraping.
`export_web_model.py`'s `_recent_results_payload()` looks up every fighter
appearing on the upcoming card (both corners), sorts their fights by date
descending, and takes the top 5, tagging each as `W`/`L`/`D`/`NC` (draws and
no-contests checked via their own boolean columns first, since `winner_id`
is NaN for both and would otherwise silently fall through to "loss").
Scoped to just the upcoming-card fighters for now, not the full active
roster, matching the user's explicit "start with the week's card" choice
over the full predictor -- extend the scope here if this later gets added
to the main predictor's fighter cards too, per the user's stated ideal.

Frontend (`ui.js`'s `formBadgesHtml()`): small colored square badges (green
`W` / red `L` / gray `D`/`NC`, reusing the existing `--green`/`--red` tokens
rather than adding new ones -- the letter already disambiguates) rendered as
`<button>` elements, not plain hover targets, because hover has no mobile
equivalent -- tap toggles a `.open` class that reveals a small tooltip
(`.fc-form-tip`, "lost to Alex Pereira · KO/TKO · R1") showing opponent +
method + round, with a `document`-level click listener closing any open
tooltip on an outside tap. `:hover`/`:focus` in the CSS cover desktop for
free on top of the same toggle mechanism. Fighters with no UFC fight record
show a "UFC Debut" label instead (see below) rather than no badges at all.

**Real duplicate-name data bug found and fixed, added 2026-07-24**: user
noticed Mike Davis (a real, active UFC lightweight) showed zero fight
history on the card, followed by a general "make sure we're getting all
our data correct" ask. Root cause was in `load_data.py`'s `load_fights()`,
not the card scraper: `name_to_id = fighters...drop_duplicates(subset="name",
keep=False)...` dropped BOTH rows for any duplicated fighter name --
`keep=False` means "drop every occurrence of a duplicated value," not "drop
the extras." Our data has 8 real, distinct people who happen to share a
name (e.g. two different "Bruno Silva"s at different weights) -- every one
of their fights, ~50 total across `fights.csv`, silently got `fighter_id =
NaN`, making genuinely active fighters like Mike Davis look winless/
historyless and excluding all those fights from Elo/feature computation
entirely.

Fixed by disambiguating per-fight instead of dropping the name outright:
`_weight_to_division()` buckets a fighter's own listed fight weight (which
clusters tightly on the real division numbers, confirmed by checking the
distribution) against the bout's own weight class -- resolves only when
EXACTLY ONE candidate's division matches, stays `NaN` (same safe fallback
as before) if zero or multiple match, so a genuinely ambiguous fight is
never guessed at. Result: Mike Davis 7/7 fights recovered; the other 7
duplicate names mostly recovered too (e.g. Bruno Silva 22/23 -- the one
remaining unresolved bout has a weight class that doesn't match EITHER
candidate, correctly left alone rather than guessed). Full pipeline
re-run (`load_data` -> `build_features` -> `method_features` -> `train` ->
`train_method` -> `train_round` -> `evaluate`) to pick up the ~50 newly-
recovered fights into Elo/features -- win-model holdout accuracy moved
0.658 -> 0.640 (AUC 0.691 -> 0.685), a real but small shift, well under
this project's own "flag if >5 points" guard, and expected: correcting a
fighter's ID mid-career reshuffles their whole Elo trajectory, not just
that one fight.

The SAME bug existed independently in `scrape_upcoming_card.py`'s
`match_fighter_ids()` (`by_norm_name.setdefault(...)` silently kept
whichever duplicate-named fighter came first, rather than dropping them --
a different failure mode, wrong-but-plausible instead of missing, same
root cause) -- fixed with the identical weight-class disambiguation
(imports `_weight_to_division` from `load_data.py` rather than
duplicating the logic).

**"UFC Debut" label, same session**: user's original ask, but building it
before the fix above would have inherited the same bug (Mike Davis would
have shown "UFC Debut" instead of a real record -- wrong, not just
missing). `_recent_results_payload()` now always sets a key for every
fighter it looks up, even to an empty list, so the frontend can tell a
genuine zero-fight debut apart from a fighter it never looked up at all
(no id resolved) -- `formBadgesHtml()` renders `.fc-debut-label` ("UFC
Debut", muted italic) for the former, nothing for the latter.

**Divisional rankings, added 2026-07-23 (same day, follow-up)**: since the
card scraper already reads `.c-listing-fight` blocks off ufc.com, the same
blocks also carry each fighter's official UFC divisional rank in a
`.c-listing-fight__ranks-row` container -- always exactly two
`.c-listing-fight__corner-rank` divs in `[red, blue]` order, each holding
either `"C"` (reigning champion, confirmed against a real title fight),
`"#N"`, or nothing for unranked. `_extract_ranks()` in
`scrape_upcoming_card.py` pulls this alongside the existing name/weight-
class/title-fight extraction; `rank_a`/`rank_b` are `None` when the Sherdog
fallback path runs instead (no ranking data available there). Rendered in
`ui.js` as a small chip next to each fighter's name (`rankChipHtml()`) --
gold for `"C"`, muted for a plain number, nothing for unranked (no
placeholder chip).

**News tab, added 2026-07-24**: `src/data/scrape_news.py` pulls ~15-20
recent headlines from ufc.com/news (robots.txt allows it; paginated via
`?page=N`, no JS needed). Each card exposes a clean headline/teaser/
category-tag/thumbnail/link structure -- only that preview data is scraped,
never the article body, and the site always links out to the real article
rather than reproducing its text. Thumbnails are hotlinked to ufc.com's own
hosting (same as any news aggregator), not downloaded/re-hosted. The
source's own timestamps ("10 hours ago") are relative and would read as
wrong on a site that only refreshes weekly, so they're discarded entirely
in favor of a single "As of `<export date>`" line. Wired through
`export_web_model.py`'s `_news_payload()` into `ui.js`'s `renderNews()`,
styled with a new `--teal` accent token (same 4-theme-block pattern as
`--green`/`--violet`) since it's a new nav section distinct from the
existing gold/green/violet ones.

**Gotcha if you ever hand-roll XGBoost inference from its native JSON dump**:
early stopping (`early_stopping_rounds=30`) keeps training past the best
round before it actually stops, so the saved model has MORE trees than
`predict_proba()` actually uses -- sklearn silently truncates to
`best_iteration + 1` rounds, but that cutoff isn't obvious from the tree
data itself, it's stored separately under `learner.attributes.best_iteration`
in the raw JSON. Missing this produced a ~3.5 point error in win probability
during development. `export_web_model.py`'s `_best_iteration()` handles it.

**Second gotcha, more insidious -- XGBoost compares splits in float32, not
float64**: it casts every feature value to float32 internally before
evaluating a split threshold, both during training and prediction. A pure
double-precision (float64) reimplementation -- which is what JS numbers and
naive Python both are -- will get the SAME answer as XGBoost for the
overwhelming majority of splits, but if a feature value happens to land
within float32's rounding distance of a threshold (float32 has ~7 significant
digits of precision), the float64 comparison can go the opposite direction.
This caused a real, reproducible ~2.8-point win-probability error for one
specific matchup during development -- traced to exactly one flipped branch
in one tree (out of 106), on an `age_years_diff` value 4.4e-7 away from its
split threshold. Confirmed with `np.float32(val) < np.float32(cond)` flipping
relative to the plain float64 comparison for that exact pair of numbers.
Fixed in `engine.js`'s `walkTree` by comparing with `Math.fround(val) <
Math.fround(splitCond)` instead of a plain `<`. If you ever touch the tree
traversal logic in engine.js (or reimplement XGBoost inference in any other
language), this precision detail is not optional -- re-verify against
`predict.py` across several matchups afterward, the same way this was caught.

### Prop Bet Tracker (in-browser paper trading)

Below the matchup predictor, the site also has a paper-trading log for prop
bets (method of victory, round totals) -- the client-side counterpart to
`src/backtest/{log_bet,settle_bet,paper_trade_report}.py`, since running
Python isn't realistic for logging a bet at the sportsbook in the moment.
`web/paper_trade.js` ports the same odds math and market pricing exactly
(reusing `predictFull()`'s already-computed `methodGivenA`/`methodGivenB`,
`pFinish`, and `roundGivenFinish`), and uses the exact same CSV schema as the
Python tools, so a downloaded log opens in either.

No backend exists, so persistence is a hybrid: bets auto-save to the
browser's `localStorage` (best-effort -- wrapped in try/catch in case a
sandboxed context disables it) plus an explicit "Download backup" / "Restore
from file" pair that doesn't depend on browser storage surviving at all.
Export uses the Claude Artifact `downloads` capability when available
(`window.claude.downloads.save`), falling back to a plain `<a download>`
click otherwise -- both paths were exercised during testing. Import is a
plain `<input type="file">` + `FileReader`, needing no special capability.

### My Predictions (not betting-affiliated), added 2026-07-23

A second, separate log below the Prop Bet Tracker, for users who just want
to record what THEY personally think will happen -- winner, optionally a
method, optionally a round, plus a free-text note -- with zero odds, edge,
or stake-sizing math anywhere in it. Deliberately kept as its own module
(`web/predictions.js`) and its own `localStorage` key
(`ufc_my_predictions_v1`) rather than folded into the prop tracker as another
"market" type, since the user explicitly wants this framed as unrelated to
betting. Mirrors the same mount/CSV-backup/restore pattern as
`paper_trade.js` (see above) for consistency, including its own
`my_predictions.csv` schema.

Each logged prediction also captures what the model itself predicted for
that matchup at the time (via the same `verdictText()` helper used
elsewhere), shown alongside your pick for comparison, and the settled-results
report includes a "picked the same winner as the model" rate -- a
descriptive stat only (winner comparison, not full method+round agreement;
the report text says so explicitly to avoid the wrong impression).

**Real bug caught during testing, not just anecdote**: a CSV
export/re-import round-trip test (log a prediction, settle it, hand-build a
CSV row mimicking one exported from a different session, import it) showed
the settled-results report silently under-counting genuinely correct picks.
Root cause: `settlePrediction()` stored `correct_winner`/`correct_method`/
`correct_round` as real JS booleans, which JSON round-trips (auto-save)
fine, but a **CSV round-trip turns a boolean into the string `"true"`**, and
the report's original `filter(p => p.correct_winner === true)` used strict
equality -- a re-imported row's string `"true"` fails `=== true`, so it
silently stopped counting as a hit. Fixed by having the report recompute
correctness fresh from the raw `picked_*`/`actual_*` fields every time
(`isCorrectWinner`/`isCorrectMethod`/`isCorrectRound` in `predictions.js`)
instead of trusting the stored flags -- the stored `correct_*` columns are
now purely for readability if someone opens the CSV directly, never read
back by the app's own logic. Verified with a hand-built two-row CSV
(one correct, one incorrect pick) imported via `replace` mode, confirming
the report's accuracy percentages matched hand-computed expectations exactly.

### Page structure and section navigation, added 2026-07-23

The page grew four distinct sections over the course of this project (This
Week's Card, Predict, Prop Bet Tracker, My Predictions) that had started to
blur together visually -- flagged directly by the user ("it is easy to get
lost on it, there being no clear differentiation between the predictions and
the betting log"). Fixed two ways, deliberately choosing the lighter option
over a full tab-based UI (which would hide sections from each other and lose
the "scroll the whole card" feel) -- explicitly agreed as a first pass, with
tabs as the fallback if this doesn't read as different enough:

- **A sticky section nav** (`#site-nav` in `site_template.html`) pinned to
  the top of the viewport with jump-links to all four sections. Uses plain
  `<a href="#id">` anchors + `scroll-behavior: smooth` on `html` (native
  browser behavior, no custom scroll JS to maintain), with `scroll-margin-top`
  on each target section so the sticky bar never covers a section's own
  header when jumped to. A small `IntersectionObserver`-based scrollspy in
  `ui.js` (`setupScrollspy()`) highlights whichever section is actually in
  view as you scroll, not just on click.
- **A distinct accent color per section**, extending the existing red/blue/
  gold token system with two new CSS custom properties (`--green` for the
  Prop Bet Tracker -- money/wagering association, `--violet` for My
  Predictions -- deliberately a different hue from anything money-related,
  reinforcing "not betting"), each with dark/light theme variants following
  the same pattern as the existing tokens. Each tracker section gets a
  colored top border + a very subtle background wash in its own color;
  Prop Tracker and My Predictions also got a proper bolded section header
  (eyebrow + title, matching the visual weight of "This Week's Card"'s own
  header) in place of the plain `.tape-title` both used before, which is
  part of why they read as near-identical at a glance previously.

**Known gap**: the Browser pane did not composite frames in the session this
was built (screenshot, programmatic scroll, and viewport resize all silently
no-op'd against the live tab -- confirmed by testing `window.scrollTo()`
directly and finding `scrollY` never changed). Verified everything checkable
without real rendering instead: computed CSS values for the new accent
colors/sticky positioning, the full predict -> prop-tracker -> my-predictions
functional flow after the DOM was restructured (`.matchup` is now wrapped in
a `#predict-section` div alongside a new header, rather than carrying the
nav-anchor id directly), and zero console errors throughout. The anchor-jump
and scrollspy mechanics themselves rely on standard, well-established browser
behavior (not novel custom logic), so this is a real but bounded gap -- if
the user reports the nav not scrolling correctly or the active-link
highlighting not working, that's the first place to check with a real
render.

**Compacting pass, same feedback round**: the user also asked for the page
to feel less spread out. Trimmed vertical rhythm across the board rather
than one big rewrite -- `.page` top/bottom padding, the masthead's bottom
margin, the sticky nav's own margin, each section's top margin (2.5-3.5rem
down to 1.75-2.5rem depending on section), and the fight-card row list's
internal padding/gaps. Kept every individual change small and additive to
existing values (no rule deleted or restructured) specifically so this pass
carries near-zero regression risk -- nothing about component structure or
behavior changed, only spacing numbers.

### Visual design

Deliberately built around the sport's own materials rather than a generic
dashboard look: a near-black ring-canvas ground, the red/blue corner
convention as the actual color system (not a decorative accent), and brass
standing in for gold (an engraved belt plate, not a bright flat "gold"
token). Colors live as CSS custom properties in `site_template.html`,
redefined per theme (`prefers-color-scheme` + a `data-theme` override for
the viewer's own toggle) -- same variable names as before a July 2026
redesign pass, just richer values, so no JS had to change.

Typography: **Oswald Bold**, a real condensed sports-broadcast face (the
kind used on scoreboards and fight posters), inlined as a subsetted WOFF2
data URI (`@font-face` in `site_template.html`, ~11KB) rather than a system
font standing in for one. Used with restraint -- only the masthead title,
"VS" mark, fighter names, and the predicted-verdict headline, not the whole
page (body copy stays on the system font stack to keep the rest of the
payload down). Regenerate it if it's ever lost:
```
python -m fontTools.varLib.instancer "Oswald[wght].ttf" wght=700 -o oswald-700.ttf
python -m fontTools.subset oswald-700.ttf --output-file=oswald-700.woff2 --flavor=woff2 \
  --unicodes="U+0020-007E,U+00A0-024F,U+2018-201F,U+2026,U+2013-2014" --no-hinting --desubroutinize
```
(source: `google/fonts` GitHub repo, `ofl/oswald/Oswald[wght].ttf`, SIL Open
Font License -- redistribution/embedding is explicitly permitted.)

**Fighter portraits: real country flags, not a generated badge.** Two
earlier versions of this (a procedurally-generated fighter-bust silhouette,
then a boxing glove medallion -- see git history / memory for the false
starts) were replaced entirely per explicit user request for real flags.
No existing data source had fighter nationality at all -- not UFCStats, not
the odds datasets used elsewhere in this project -- so this required a new,
narrowly-scoped scrape:

- **Active-roster filter first** (`src/data/scrape_nationality.py`'s
  `ACTIVE_WINDOW_MONTHS`, also reused by `export_web_model.py`): "active" =
  fought within the last 24 months, using data already in
  `fighter_snapshot.csv` -- no new source needed for this half. This
  matters architecturally: the underlying training/Elo/rolling-form
  pipeline keeps EVERY historical fighter regardless of activity (an active
  fighter's own features depend on fights against opponents who've since
  retired, so nothing gets deleted there) -- only the website's exported,
  selectable fighter list is filtered down to ~780 active fighters. This
  was a real constraint the user raised proactively before I'd even
  mentioned it, and it's the right one.
- **Nationality scraped from Sherdog.com** for just that active subset (not
  the full multi-thousand historical roster, which would have made a
  scrape like this impractical) -- checked robots.txt first (Sherdog:
  unrestricted; `ufc.com`'s own roster pages specify a 15s crawl-delay,
  which would've taken 3+ hours for ~800 fighters and was ruled out for
  that reason). Sherdog fighter URLs aren't guessable from a name (found
  out the hard way mid-session -- a manually-guessed URL silently landed on
  a *different* fighter's profile with a totally wrong nationality), so
  every fighter is looked up via Sherdog's own search first and matched by
  exact normalized name, skipped rather than guessed if nothing matches.
  87.9% match rate (687/782) on the first automated run. Politely
  rate-limited (~1 req/sec, ~1500 requests total, resumable if interrupted
  -- a real mid-run network outage killed the first attempt after only 148
  fighters, so resume support isn't hypothetical).
- **The remaining ~95 fighters were resolved by hand, not further
  automation.** Tried extending the matcher first (camelCase-splitting for
  concatenated Korean given names like "SeungWoo" -> "Seung Woo", word-order
  reversal for surname-first Chinese names like "Zhang Weili" -> "Weili
  Zhang" -- both verified working on real examples) and investigated deeper
  pagination for common-surname misses (Sherdog's search has zero relevance
  ranking, just alphabetical-by-first-name pages of 20 -- "Jon Jones" is
  page 22). The user stopped this line of work directly ("seems easier than
  your messing up the Chinese Korean and Asian names") and asked to just be
  given the unmatched list instead. Right call: automated fuzzy matching on
  exactly this category of name (short, common, transliterated many
  different ways) is where a wrong-but-plausible match is easiest to ship
  silently. The full list went back and forth in conversation and the
  answers are now `src/data/manual_nationality_overrides.py` -- a real,
  rerunnable, idempotent script (not a one-off shell command) specifically
  so this data survives even if `fighter_nationality.csv` is ever
  regenerated from scratch. Run it right after `scrape_nationality.py` in
  that case. Current match rate: 782/782 (100%).
- **Flags themselves** are MIT-licensed SVGs from
  [lipis/flag-icons](https://github.com/lipis/flag-icons)
  (`src/fetch_flags.py`), cached locally in `web/flags/` (like `web/fonts/`)
  and embedded into `model_data.json` only for the country codes the active
  roster actually uses (82 currently), keyed by ISO code. Sherdog shows UK
  constituent-country flags (England/Wales/Scotland/N. Ireland) rather than
  a single "GB" flag -- these aren't standard ISO 3166-1 codes, so
  `fetch_flags.py`'s `CODE_REMAP` maps Sherdog's codes to flag-icons'
  equivalent non-ISO filenames (`gb-eng`, `gb-wls`, `gb-sct`, etc.) at fetch
  time, built from codes actually observed rather than guessed upfront.
- Badge shape changed from a circular medallion to a small rectangular
  plate (`.fighter-badge`, ~3.4rem x 2.4rem) to match flags' natural 4:3
  aspect ratio rather than force-cropping them into a circle.

Net effect on payload: dropped from ~2MB to ~1.7MB overall, since the
active-only fighter list (782 fighters) is far smaller than the full
historical roster it replaced, more than offsetting the 82 small flag SVGs
added.

A subtle canvas-grain texture (an inline SVG `feTurbulence` filter, no image
payload) sits behind everything instead of a flat solid color, and the
masthead gets a one-time restrained load-in animation (respects
`prefers-reduced-motion`).

**Screenshot tooling came back mid-session** after being unavailable
earlier -- worth retrying rather than assuming it's still broken.
Actually seeing the rendered page caught three real bugs that computed-style
and DOM checks alone had completely missed:
1. The fighter-bust emblem described above -- unreadable at actual size,
   despite passing every structural check (no overlap, correct hash
   variation).
2. The "Predicted" chip and the tape-row progress bar were both solid
   `var(--gold)` fill sitting directly adjacent, so the Decision row
   visually read as ~90% filled when the real value was 43.5% -- the
   percentage math was already confirmed correct via
   `getBoundingClientRect`, this was a pure rendering-clarity bug invisible
   to any non-visual check. Fixed by making the chip an outlined ghost
   badge instead of solid-filled.
3. A real CSS specificity bug: `.pt-row { display: flex }` and the browser's
   built-in `[hidden] { display: none }` have equal specificity, and the
   author rule wins by cascade order -- so `paper_trade.js` setting
   `methodRow.hidden = true` etc. to hide fields that don't apply to the
   selected market did nothing, every field showed regardless of market.
   Fixed with `.pt-row[hidden] { display: none; }` (raises specificity via
   the attribute selector). Worth checking for this pattern anywhere else
   `.hidden` gets toggled on an element whose class also sets `display`.

**Takeaway for future work here**: DOM/computed-style verification is
necessary but not sufficient for this codebase -- all three bugs above
passed every functional test that existed before a screenshot was taken.
Use screenshot tooling for any future visual change if it's available; if
it's not, say so explicitly rather than presenting non-visual checks as
equivalent confirmation.

**Follow-up, same session: the body copy was still the giveaway.** The user
pointed out that Oswald alone hadn't actually fixed the "looks like every
other Claude-made site" complaint -- because only display text (masthead,
"VS", fighter names, verdict) used it. Every paragraph, label, button, and
form field was still on the plain system-UI stack
(`-apple-system, "Segoe UI", Roboto, ...`), which is arguably as much a
tell as Inter/Space Grotesk, since it's the literal no-custom-font default.
Added **Barlow** (Regular 400 + Bold 700, same subsetting/embedding
approach as Oswald, ~13KB each) as the body face -- picked specifically
because it comes from the same grotesque-sans lineage as Oswald (civic/
signage-inspired), so the pairing reads as one considered system rather
than two unrelated fonts glued together. Same license/rebuild-command
documentation pattern as Oswald; font files + OFL license saved to
`web/fonts/`.

**Second real bug caught applying this**: `<button>`, `<input>`, `<select>`,
and `<textarea>` don't inherit `font-family` from the body by default in
ANY browser -- a well-known but easy-to-forget CSS gotcha (form controls use
the OS's native control font unless explicitly told to inherit). Only
`.predict-btn` had `font-family: inherit` set; every other button on the
page (Change Fighter, the 3RD/5RD toggle, all the prop-tracker action
buttons) was silently rendering in the system default regardless of the new
Barlow embed -- confirmed via `getComputedStyle` returning `"Arial"` for
`.clear-btn` instead of the expected stack. Fixed properly with a single
global rule (`button, input, select, textarea { font-family: inherit; }`)
rather than patching each button class individually -- the standard fix for
this exact gotcha. Verified afterward that every form control across both
the main predictor and the prop tracker correctly resolves to Barlow.

## Pipeline

1. **Clean the raw CSVs** into tidy tables:
   ```
   python -m src.data.load_data
   ```
   Writes `data/processed/fighters.csv`, `fights.csv`, `round_stats.csv`.

2. **Build features**:
   ```
   python -m src.features.build_features
   python -m src.features.method_features
   ```
   Writes `data/processed/model_features.csv` (one row per fighter per fight,
   augmented with both corner orders), `fighter_snapshot.csv` (each fighter's
   current Elo/record/form, used by `predict.py`), `elo_ratings.csv` and
   `division_elo_ratings.csv` for inspection, and `method_features.py`'s
   `method_long.csv` / `method_snapshot.csv` (win/loss-by-method
   distributions per fighter, last-5 and career tiers).

3. **(Optional) Tune hyperparameters**:
   ```
   python -m src.models.tune
   ```
   Only needs re-running after adding/removing features (see "Hyperparameter
   tuning" below) -- writes `models/artifacts/best_params.json`, which
   `train.py` picks up automatically. Not part of the regular weekly refresh;
   the existing tuned params are reused as-is when just refreshing data.

4. **Train + evaluate**:
   ```
   python -m src.models.train
   python -m src.models.train_method
   python -m src.models.train_round
   python -m src.models.evaluate
   ```
   Trains the baseline (Elo-only logistic regression) and main XGBoost win
   model, with a chronological train / validation / holdout-test split.
   `train_method.py` predicts Decision/KO-TKO/Submission from the WINNER's
   perspective of each fight (also trains an ablation model without the
   alignment features to confirm they're adding real signal -- see Design
   notes). `train_round.py` predicts which round a finish happens in,
   conditional on the fight ending in a finish. `evaluate.py` reports
   accuracy / log-loss / Brier score / AUC for the win model on the untouched
   holdout, saves a calibration plot to `models/artifacts/calibration_plot.png`,
   and runs a corner-order symmetry check.

5. **Predict a matchup**:
   ```
   python -m src.models.predict "Fighter A Name" "Fighter B Name" [--rounds 3|5]
   ```
   Looks up each fighter's current snapshot and returns a symmetrized win
   probability (averages the (A,B) and (B,A) model scores, which cancels
   XGBoost's boosting-order noise -- see `evaluate.py` docstring), plus a
   method-of-victory breakdown and a round breakdown (conditional on a
   finish). `--rounds 5` for title/main-event (5-round) fights. Also prints
   each fighter's current weight class and their all-time rank within it by
   division Elo (see "Weight-class-aware Elo" below).

## Weight-class-aware Elo (informational only, not a training feature)

`src/features/elo.py`'s `compute_division_elo` maintains a separate Elo
rating per (fighter, weight class) instead of one global rating -- a
fighter's lightweight skill and heavyweight skill aren't the same thing.
When a fighter enters a division for the first time, their rating is seeded
from 75% of their most recent rating in whatever division they last fought
in (shrunk toward the base rating), not reset from scratch, since skill
mostly transfers across a weight change even if not perfectly. Validated
against real career moves -- e.g. Jon Jones shows up rated separately at
Light Heavyweight (his long-reigning division) and Heavyweight (where he
moved up later), both matching his actual record; same for Georges
St-Pierre at Welterweight and his one Middleweight superfight.

**It was tested as a training feature and empirically didn't help**: three
controlled variants (same random seed) -- global Elo only, global + division
Elo, division Elo replacing global -- all landed within noise of each other
(64.1-64.4% accuracy, 0.686-0.690 AUC). Division Elo is 95% correlated with
the existing global Elo and has less data per division to stabilize on, so
it mostly adds redundant noise rather than new signal. It's kept in the
codebase purely as **informational context** -- `predict.py` and the website
show each fighter's division + all-time rank within it, which is genuinely
interesting on its own, but it does not feed into any of the three models.

This also required fixing a real data-quality bug along the way: the raw
`WEIGHTCLASS` field had 120 near-duplicate categories ("Welterweight",
"UFC Welterweight", "UFC Interim Welterweight", "Ultimate Fighter 33
Welterweight Tournament", ...) because the original cleaning only stripped
"Bout"/"Title Bout" suffixes. `load_data.py`'s `_normalize_weightclass` now
canonicalizes these down to the real 14 divisions.

## Notebooks

- `01_explore_data.ipynb` -- sanity-checks the cleaned tables.
- `02_feature_engineering.ipynb` -- validates Elo trajectories against known
  fighters' careers and inspects the model feature table.
- `03_model_training_eval.ipynb` -- runs training + evaluation inline, shows
  the calibration plot and feature importances.

## Design notes

- Every feature is a **fighter_A - fighter_B differential**, and training
  data is augmented with both corner orders, so the model can't pick up a
  red/blue-corner bias. Verified in `evaluate.py`'s symmetry check.
- All career/rolling features are computed strictly from fights **before**
  the fight they're attached to (`shift(1)` per fighter after sorting
  chronologically) -- no leakage from a fight's own outcome into its features.
- Splits are **chronological**, never random k-fold -- fight outcomes aren't
  independent over time (fighters and styles evolve), so random splits would
  overstate accuracy.
- A handful of UFC fighters share the exact same name (e.g. two different
  people named "Bruno Silva"). `load_data.py` leaves these unmatched rather
  than risk mixing two people's records together; affects well under 1% of
  fighter-fight slots.
- Small-sample rate stats (win %, finish rate, striking/takedown accuracy,
  per-minute rates) are shrunk toward sport-wide population priors, weighted
  by how much data the fighter actually has (`K_FIGHTS`, `K_STRIKE_ATTEMPTS`,
  `K_TD_ATTEMPTS`, `K_MINUTES` in `build_features.py`). Without this, a
  fighter's single UFC fight could produce a 100% takedown rate or 0 strikes
  absorbed/min purely by chance, and the model would trust it as much as a
  24-fight veteran's track record. This is applied identically to training
  features and to `predict.py`'s live snapshot -- verified to improve holdout
  accuracy by ~1.5 points, not just fix anecdotes.
- XGBoost's final prediction is a 90/10 blend with the Elo-only logistic
  regression baseline (`XGB_BLEND_WEIGHT` in `evaluate.py`). Tree ensembles
  cannot extrapolate past the range of a feature seen in training -- since
  real UFC matchmaking rarely books lopsided fights, `elo_diff` tops out
  around +/-203 in the training data, and XGBoost's response to it literally
  flattens beyond that. The logistic baseline extrapolates smoothly (a
  sigmoid has no ceiling), so blending in 10% of it fixes that specific
  failure mode for very lopsided hypothetical matchups, with no measurable
  cost to accuracy on realistic (competitively-matched) fights.

## Method and round models

`train_method.py` predicts method of victory using a specific heuristic
(supplied by the project's user, who reports success hand-predicting fights
this way): compare the FAVORITE's typical winning method against the
UNDERDOG's typical losing method (does the favorite's style match how the
underdog usually loses?), and the reverse upset path (does the underdog's
typical winning method match how the favorite usually loses?) -- at two
tiers, last-5 fights and full UFC career. Favorite/underdog is decided by
pre-fight Elo. These are the `align_fav_*` / `align_upset_*` features in
`src/features/method_features.py`.

**This heuristic is doing essentially all of the real work**: an ablation
model trained on the same fight-outcome diff features but WITHOUT the
alignment features ties the naive "always guess Decision" baseline exactly
(51.5% vs. 51.4%). With the alignment features, holdout accuracy is 54.0%
and log-loss improves from 1.015 (naive) to 0.968.

The round model is only trained on fights that end in a finish (decisions
trivially go the distance) and is queried twice at prediction time -- once
per possible finish method -- then mixed using the method model's own
KO/Submission probabilities as weights. Its top-pick accuracy roughly ties
"always guess round 1" (round 1 is genuinely the most common single outcome,
53% of all finishes), but its probabilities are real: log-loss 1.052 vs.
1.097 for the naive marginal distribution, and 0.589 AUC discriminating
actual round-1 finishes. Both models under-call Submission (it's the
rarest of the 3 methods, ~20% base rate) -- tried class-weighting to fix
this, but it made both accuracy and log-loss worse, so it was reverted.
`P(sub)` is still meaningfully informative even when it's not the top pick
(0.65 AUC discriminating actual submissions) -- `predict.py` shows the full
probability breakdown rather than forcing a single guess, so this isn't a
practical problem.

## Known limitation: outlier fighters in lopsided hypothetical matchups

`predict.py` can still give a misleading answer for matchups that would never
actually be booked -- e.g. a legendary former champion at advanced age and a
long layoff, against a fighter debuting off a single win. Age and layoff
length are genuine, in-distribution statistical patterns in the data (older
fighters with long layoffs tend to lose more, on average, across 30 years of
UFC history), so the model isn't wrong to weigh them -- it just has no way to
know a specific fighter is a historical outlier whose talent overrides that
trend, because no stats-based feature encodes "this particular person is one
of the greatest of all time." Real matchmakers never book fights extreme
enough to give the model examples to learn this distinction from. Treat
predictions for wildly mismatched hypothetical pairings with much lower
confidence than predictions for realistic, plausible UFC matchups.

## Hyperparameter tuning and interaction features

`src/models/tune.py` searches XGBoost hyperparameters (max_depth,
learning_rate, subsample, colsample_bytree, min_child_weight, reg_lambda) via
expanding-window chronological cross-validation (folds validating on 2020,
2021, 2022, 2023 in turn, each trained on everything before that year) --
more robust than comparing configs on a single validation split, which is all
`train.py` ever did before. The 2024+ holdout stays completely untouched
throughout the search. This found a real, holdout-validated improvement:
64.4% -> 65.8% accuracy (0.690 -> 0.691 AUC) just from better hyperparameters,
none of which had ever actually been tuned before (the original values were
reasonable defaults, not a search result). `train.py` automatically uses
`models/artifacts/best_params.json` when present, falling back to defaults
otherwise. Re-run `tune.py` after adding/removing features, since the best
config can shift (confirmed below).

Also tried: style-matchup interaction features (`wrestling_edge_diff` = A's
takedown rate against B's specific takedown defense minus the reverse,
`striking_edge_diff` similarly for striking volume vs. absorption) --
the same "does X's strength align with Y's weakness" pattern that
measurably helped the method model. Re-running the CV search WITH these
features present did shift the best hyperparameters, but across every fair,
controlled comparison tried (same seed, same holdout), results flip-flopped
by metric and stayed within noise of the no-interaction baseline -- never a
clear win. Reverted, same as division Elo: a reasonable, well-motivated idea
that didn't hold up under rigorous testing. The code (`_compute_interactions`,
`INTERACTION_COLS` in `build_features.py`) is still there, computed into
`model_features.csv`, just excluded from `FEATURE_COLS`/training -- don't
add it back without redoing this kind of controlled test.

## Current holdout performance (fights on/after 2024-01-01)

| Model                                    | Accuracy | Log-loss | Brier | AUC   |
|-------------------------------------------|---------:|---------:|------:|------:|
| Baseline (Elo-only logistic reg)           |    0.557 |    0.680 | 0.243 | 0.589 |
| XGBoost, untuned hyperparameters           |    0.644 |    0.643 | 0.226 | 0.690 |
| XGBoost, CV-tuned hyperparameters          |    0.658 |    0.642 | 0.225 | 0.691 |

UFC fights are high-variance by nature (a single mistake can end a fight), so
accuracy in the low-to-mid 60s on a class-balanced holdout is in line with
other public UFC prediction models -- this is the sport's ceiling, not a bug.

## Real-odds backtest: does this beat the sportsbooks? (No.)

Raw accuracy and "can this profitably beat the market" are different
questions -- sportsbook odds already price in information (style matchups,
injury/camp news, insider sentiment) a stats-only model can't see. To test
profitability directly rather than assume it, `src/backtest/` joins
[jansen88/ufc-data](https://github.com/jansen88/ufc-data)'s historical
moneyline odds (Nov 2014-Dec 2023, no stated license, used for personal
research only) onto our own fight history and compares:

1. `match_odds.py` -- joins the odds' favourite/underdog names onto our
   fights.csv by normalized name + date (84.3% match rate, 3699 fights).
2. `walk_forward.py` -- **critical**: the production model is trained on
   everything before 2024, so scoring it on 2015-2023 fights would be
   in-sample. This retrains yearly expanding-window folds (train strictly
   before each test year, same tuned hyperparameters/blend/symmetrization as
   production) to get a genuinely out-of-sample probability for every
   odds-covered fight.
3. `run_backtest.py` -- de-vigs the market's decimal odds into a true
   implied probability, compares calibration/AUC, and simulates flat + 1/4-
   Kelly betting across several edge thresholds.

**Result** (3546 fights, 2015-2023): the vig-free market beats the model on
every metric -- Brier 0.214 vs 0.235, log-loss 0.617 vs 0.661, AUC 0.640 vs
0.576. AUC is calibration-independent (pure rank-ordering), so this isn't
just an over-conservative-probability problem: the market genuinely ranks
fighters better. The model was also systematically underconfident at every
quantile bin of predicted probability. Betting simulation confirms it: flat
ROI was negative at every edge threshold tried; fractional-Kelly ROI was only
marginally positive (+0.5-0.9%), on samples too small to call real. This
matches expectations going in -- UFC moneyline markets are sharp (measured
vig here: 0.69%, a tight line) -- and confirms the ~65.8% holdout accuracy
above should NOT be read as any kind of signal that this model can beat
sportsbooks on the moneyline.

## Paper-trading prop bets (method of victory, round totals)

No free historical dataset of MMA prop odds (method of victory, round
totals) was found -- bestfightodds.com's per-fight prop tables sit behind
what looks like an internal/gated route, and paid odds APIs only cover props
from ~2020 on. Rather than backtest props historically, `src/backtest/`
includes a live, forward-looking paper-trading workflow: log real prop odds
as they appear for upcoming cards, let them settle after the event, and
accumulate a real sample over time.

- `log_bet.py` -- interactive: enter the matchup + market (winner / method
  of victory / round total over-under) + the odds you're seeing, and it
  computes the model's own probability for that exact market (reusing
  `predict.py`'s `predict_full()`, which already computes per-fighter method
  probabilities and the round-of-finish distribution -- just exposed here as
  `method_given_a`/`method_given_b`), the edge vs. the (optionally de-vigged)
  market, and a suggested 1/4-Kelly stake. Appends to `data/processed/paper_trades.csv`.
  A method bet can also optionally pin an exact round (e.g. "Fighter A by
  KO/TKO, Round 2") -- this multiplies in `round_given_win_method[side][method]`,
  the model's round distribution *conditioned on that specific fighter winning
  by that specific method*, rather than pricing it off the method-only
  probability alone. This matters: a real sportsbook prop like "Ngannou by
  KO/TKO in Round 1" is a strictly narrower (and lower-probability) bet than
  "Ngannou by KO/TKO, any round" -- comparing the latter's probability against
  the former's odds understates the vig you're actually facing and overstates
  your edge. Leave the round blank for the original any-round method bet.
- `settle_bet.py <bet_id> won|lost|push` -- mark a bet's real outcome once
  the fight has happened, computing realized profit at both flat and
  Kelly stakes.
- `paper_trade_report.py` -- running ROI, win rate, and model-vs-actual
  calibration by market, once enough bets have settled to mean anything
  (a few dozen at minimum -- small samples here are pure noise, same as any
  backtest).
