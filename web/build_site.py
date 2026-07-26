"""Assemble the final self-contained website from the template + engine + model data + UI JS."""
import re
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent

template = (WEB_DIR / "site_template.html").read_text(encoding="utf-8")
engine_js = (WEB_DIR / "engine.js").read_text(encoding="utf-8")
model_data_json = (WEB_DIR / "model_data.json").read_text(encoding="utf-8")
ui_js = (WEB_DIR / "ui.js").read_text(encoding="utf-8")
paper_trade_js = (WEB_DIR / "paper_trade.js").read_text(encoding="utf-8")
predictions_js = (WEB_DIR / "predictions.js").read_text(encoding="utf-8")
news_render_js = (WEB_DIR / "news_render.js").read_text(encoding="utf-8")
results_render_js = (WEB_DIR / "results_render.js").read_text(encoding="utf-8")
predict_ui_js = (WEB_DIR / "predict_ui.js").read_text(encoding="utf-8")

# Home page no longer embeds paper_trade.js/predictions.js's ADD flows (those
# moved to predict.html, see below) -- it only needs predictions.js, and only
# for the compact sidebar teaser (mountHistory), not paper_trade.js at all.
out = template.replace("__ENGINE_JS__", engine_js)
out = out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
out = out.replace("__PREDICTIONS_JS__", predictions_js)
out = out.replace("__NEWS_RENDER_JS__", news_render_js)
out = out.replace("__RESULTS_RENDER_JS__", results_render_js)
out = out.replace("__UI_JS__", ui_js)

out_path = WEB_DIR / "site.html"
out_path.write_text(out, encoding="utf-8")
print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")

docs_dir = WEB_DIR.parent / "docs"
docs_dir.mkdir(exist_ok=True)
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
news_out = news_out.replace("__NEWS_RENDER_JS__", news_render_js)

news_site_path = WEB_DIR / "news.html"
news_site_path.write_text(news_out, encoding="utf-8")
print(f"wrote {news_site_path} ({news_site_path.stat().st_size / 1e6:.2f} MB)")

news_docs_path = docs_dir / "news.html"
news_docs_path.write_text(news_out, encoding="utf-8")
print(f"wrote {news_docs_path} (GitHub Pages copy)")

# Standalone results.html page -- same pattern as news.html: shares the
# main template's CSS, embeds only the small last_results_data.json.
results_template = (WEB_DIR / "results_template.html").read_text(encoding="utf-8")
results_data_path = WEB_DIR / "last_results_data.json"
results_data_json = results_data_path.read_text(encoding="utf-8") if results_data_path.exists() else "null"

results_out = results_template.replace("__SHARED_STYLE__", shared_style)
results_out = results_out.replace("__LAST_RESULTS_DATA__", f"const LAST_RESULTS_DATA = {results_data_json};")
results_out = results_out.replace("__RESULTS_RENDER_JS__", results_render_js)

results_site_path = WEB_DIR / "results.html"
results_site_path.write_text(results_out, encoding="utf-8")
print(f"wrote {results_site_path} ({results_site_path.stat().st_size / 1e6:.2f} MB)")

results_docs_path = docs_dir / "results.html"
results_docs_path.write_text(results_out, encoding="utf-8")
print(f"wrote {results_docs_path} (GitHub Pages copy)")

# Standalone predictions.html page -- same shared-CSS pattern as news.html/
# results.html, but embeds NO model data at all (not even a small JSON
# payload): predictions.js's history/settle/report UI is pure localStorage,
# it never needs engine.js or MODEL_DATA. Only the "log a new prediction"
# form does (it needs a live matchup result), which is why that form lives
# on predict.html instead (see below), not offered on this page.
predictions_template = (WEB_DIR / "predictions_template.html").read_text(encoding="utf-8")

predictions_out = predictions_template.replace("__SHARED_STYLE__", shared_style)
predictions_out = predictions_out.replace("__PREDICTIONS_JS__", predictions_js)

predictions_site_path = WEB_DIR / "predictions.html"
predictions_site_path.write_text(predictions_out, encoding="utf-8")
print(f"wrote {predictions_site_path} ({predictions_site_path.stat().st_size / 1e6:.2f} MB)")

predictions_docs_path = docs_dir / "predictions.html"
predictions_docs_path.write_text(predictions_out, encoding="utf-8")
print(f"wrote {predictions_docs_path} (GitHub Pages copy)")

# Standalone edge-calculator.html page -- both the "log a new edge calc" form
# and the history/settle/report UI live here. The add-form needs a live
# matchup result, which only predict.html ever computes (it's the only page
# with engine.js + MODEL_DATA) -- predict_ui.js's runPrediction() persists
# each result to localStorage via paper_trade.js's setMatchup(), and this
# page's mountAdd() reads back whatever was most recently called.
edge_calculator_template = (WEB_DIR / "edge_calculator_template.html").read_text(encoding="utf-8")

edge_calculator_out = edge_calculator_template.replace("__SHARED_STYLE__", shared_style)
edge_calculator_out = edge_calculator_out.replace("__PAPER_TRADE_JS__", paper_trade_js)

edge_calculator_site_path = WEB_DIR / "edge-calculator.html"
edge_calculator_site_path.write_text(edge_calculator_out, encoding="utf-8")
print(f"wrote {edge_calculator_site_path} ({edge_calculator_site_path.stat().st_size / 1e6:.2f} MB)")

edge_calculator_docs_path = docs_dir / "edge-calculator.html"
edge_calculator_docs_path.write_text(edge_calculator_out, encoding="utf-8")
print(f"wrote {edge_calculator_docs_path} (GitHub Pages copy)")

# Standalone predict.html page -- branded "Fantasy Matchup" in the nav, a
# fun side toy (manual "pick any two fighters" picker + results panel) now
# that the real fight card has its own inline "Make Your Pick" panel per
# bout (see ui.js). Unlike news/results/predictions/edge-calculator, this
# one DOES need the full engine.js + MODEL_DATA (it runs live inference),
# so it's a heavy page like the home page -- that's unavoidable, prediction
# requires the model. No My Predictions log-a-pick form here (removed --
# pointless friction on a page that's just for fun, not meant to build a
# track record); predictions.js isn't even loaded on this page anymore.
# paper_trade.js IS still embedded, but never mounted here -- it just needs
# to be loaded so setMatchup() can persist each result to localStorage for
# edge-calculator.html to read (see the comment there). Reads ?a=&b=&
# rounds= query params on load so a shared/bookmarked link still works.
predict_template = (WEB_DIR / "predict_template.html").read_text(encoding="utf-8")

predict_out = predict_template.replace("__SHARED_STYLE__", shared_style)
predict_out = predict_out.replace("__ENGINE_JS__", engine_js)
predict_out = predict_out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
predict_out = predict_out.replace("__PAPER_TRADE_JS__", paper_trade_js)
predict_out = predict_out.replace("__PREDICT_UI_JS__", predict_ui_js)

predict_site_path = WEB_DIR / "predict.html"
predict_site_path.write_text(predict_out, encoding="utf-8")
print(f"wrote {predict_site_path} ({predict_site_path.stat().st_size / 1e6:.2f} MB)")

predict_docs_path = docs_dir / "predict.html"
predict_docs_path.write_text(predict_out, encoding="utf-8")
print(f"wrote {predict_docs_path} (GitHub Pages copy)")
