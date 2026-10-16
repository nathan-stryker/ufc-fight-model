"""Assemble the final self-contained website from the template + engine + model data + UI JS."""
import re
import shutil
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR.parent))
from src.build_seo_pages import ICON_LINKS, main as build_seo_pages  # noqa: E402


def with_icons(html):
    """Add the favicon links (web/make_icons.py) right after the charset tag."""
    return html.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + ICON_LINKS, 1)


template = (WEB_DIR / "site_template.html").read_text(encoding="utf-8")
engine_js = (WEB_DIR / "engine.js").read_text(encoding="utf-8")
explain_js = (WEB_DIR / "explain.js").read_text(encoding="utf-8")
model_data_json = (WEB_DIR / "model_data.json").read_text(encoding="utf-8")
ui_js = (WEB_DIR / "ui.js").read_text(encoding="utf-8")
predictions_js = (WEB_DIR / "predictions.js").read_text(encoding="utf-8")
news_render_js = (WEB_DIR / "news_render.js").read_text(encoding="utf-8")
results_render_js = (WEB_DIR / "results_render.js").read_text(encoding="utf-8")
predict_ui_js = (WEB_DIR / "predict_ui.js").read_text(encoding="utf-8")

# Home page never embeds paper_trade.js -- it only needs predictions.js, and
# only for the compact sidebar teaser (mountHistory). paper_trade.js isn't
# embedded on ANY built page as of 2026-07-27 (Edge Calculator, its only
# consumer, was pulled from the site -- see edge_calculator_template.html's
# own comment) but the file stays in web/ as dormant source, not deleted.
out = template.replace("__ENGINE_JS__", engine_js)
out = out.replace("__EXPLAIN_JS__", explain_js)
out = out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
out = out.replace("__PREDICTIONS_JS__", predictions_js)
out = out.replace("__NEWS_RENDER_JS__", news_render_js)
out = out.replace("__RESULTS_RENDER_JS__", results_render_js)
out = out.replace("__UI_JS__", ui_js)
out = with_icons(out)

out_path = WEB_DIR / "site.html"
out_path.write_text(out, encoding="utf-8")
print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")

docs_dir = WEB_DIR.parent / "docs"
docs_dir.mkdir(exist_ok=True)
# This is a hand-built static site, not a Jekyll site -- GitHub Pages runs
# docs/ through Jekyll by default unless this marker is present, and Jekyll
# processing a large, non-Jekyll HTML payload occasionally caused mysterious
# "Page build failed" errors with no useful detail (hit this directly,
# 2026-08-06). Recreated on every build so it can never be silently lost.
(docs_dir / ".nojekyll").touch()
for icon in (WEB_DIR / "icons").iterdir():
    shutil.copyfile(icon, docs_dir / icon.name)
docs_path = docs_dir / "index.html"
docs_path.write_text(out, encoding="utf-8")
print(f"wrote {docs_path} (GitHub Pages copy)")

# Standalone news.html page -- shares the main template's CSS wholesale (kept
# in lockstep automatically, no separate stylesheet to drift out of sync)
# but embeds only the small news_data.json, not the multi-MB model payload.
news_template = (WEB_DIR / "news_template.html").read_text(encoding="utf-8")
news_data_path = WEB_DIR / "news_data.json"
news_data_json = news_data_path.read_text(encoding="utf-8") if news_data_path.exists() else "null"

style_match = re.search(r"<style>.*?</style>", template, re.S)
shared_style = style_match.group(0) if style_match else "<style></style>"

news_out = news_template.replace("__SHARED_STYLE__", shared_style)
news_out = news_out.replace("__NEWS_DATA__", f"const NEWS_DATA = {news_data_json};")
news_out = with_icons(news_out.replace("__NEWS_RENDER_JS__", news_render_js))

news_site_path = WEB_DIR / "news.html"
news_site_path.write_text(news_out, encoding="utf-8")
print(f"wrote {news_site_path} ({news_site_path.stat().st_size / 1e6:.2f} MB)")

news_docs_path = docs_dir / "news.html"
news_docs_path.write_text(news_out, encoding="utf-8")
print(f"wrote {news_docs_path} (GitHub Pages copy)")

# Standalone results.html page -- same pattern as news.html: shares the
# main template's CSS, embeds only the small last_results_data.json. Also
# embeds predictions.js (unlike news.html) so the accuracy sidebar's
# auto-settle call can actually write to the My Predictions localStorage
# log, not just read it -- see results_template.html's own script block.
results_template = (WEB_DIR / "results_template.html").read_text(encoding="utf-8")
results_data_path = WEB_DIR / "last_results_data.json"
results_data_json = results_data_path.read_text(encoding="utf-8") if results_data_path.exists() else "null"

results_out = results_template.replace("__SHARED_STYLE__", shared_style)
results_out = results_out.replace("__LAST_RESULTS_DATA__", f"const LAST_RESULTS_DATA = {results_data_json};")
results_out = results_out.replace("__RESULTS_RENDER_JS__", results_render_js)
results_out = with_icons(results_out.replace("__PREDICTIONS_JS__", predictions_js))

results_site_path = WEB_DIR / "results.html"
results_site_path.write_text(results_out, encoding="utf-8")
print(f"wrote {results_site_path} ({results_site_path.stat().st_size / 1e6:.2f} MB)")

results_docs_path = docs_dir / "results.html"
results_docs_path.write_text(results_out, encoding="utf-8")
print(f"wrote {results_docs_path} (GitHub Pages copy)")

# Standalone predict.html page -- branded "Fantasy Matchup" in the nav, a
# fun side toy (manual "pick any two fighters" picker + results panel) now
# that the real fight card has its own inline "Make Your Pick" panel per
# bout (see ui.js). Unlike news/results/predictions/edge-calculator, this
# one DOES need the full engine.js + MODEL_DATA (it runs live inference),
# so it's a heavy page like the home page -- that's unavoidable, prediction
# requires the model. No My Predictions log-a-pick form here (removed --
# pointless friction on a page that's just for fun, not meant to build a
# track record); predictions.js isn't even loaded on this page anymore.
# Reads ?a=&b=&rounds= query params on load so a shared/bookmarked link
# still works. (Edge Calculator, which this page used to hand results off
# to via paper_trade.js's setMatchup(), was pulled from the site -- see
# edge_calculator_template.html's own comment for why.)
predict_template = (WEB_DIR / "predict_template.html").read_text(encoding="utf-8")

predict_out = predict_template.replace("__SHARED_STYLE__", shared_style)
predict_out = predict_out.replace("__ENGINE_JS__", engine_js)
predict_out = predict_out.replace("__EXPLAIN_JS__", explain_js)
predict_out = predict_out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
predict_out = with_icons(predict_out.replace("__PREDICT_UI_JS__", predict_ui_js))

predict_site_path = WEB_DIR / "predict.html"
predict_site_path.write_text(predict_out, encoding="utf-8")
print(f"wrote {predict_site_path} ({predict_site_path.stat().st_size / 1e6:.2f} MB)")

predict_docs_path = docs_dir / "predict.html"
predict_docs_path.write_text(predict_out, encoding="utf-8")
print(f"wrote {predict_docs_path} (GitHub Pages copy)")

# Static, search-indexable fight/event pages + sitemap (src/build_seo_pages.py),
# rebuilt every time the site is -- including the weekly scheduled refresh.
build_seo_pages()
