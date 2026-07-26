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

out = template.replace("__ENGINE_JS__", engine_js)
out = out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
out = out.replace("__PAPER_TRADE_JS__", paper_trade_js)
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
# form does (it needs a live matchup result), which is why that form stays
# on the home page next to Predict and isn't offered on this page.
predictions_template = (WEB_DIR / "predictions_template.html").read_text(encoding="utf-8")

predictions_out = predictions_template.replace("__SHARED_STYLE__", shared_style)
predictions_out = predictions_out.replace("__PREDICTIONS_JS__", predictions_js)

predictions_site_path = WEB_DIR / "predictions.html"
predictions_site_path.write_text(predictions_out, encoding="utf-8")
print(f"wrote {predictions_site_path} ({predictions_site_path.stat().st_size / 1e6:.2f} MB)")

predictions_docs_path = docs_dir / "predictions.html"
predictions_docs_path.write_text(predictions_out, encoding="utf-8")
print(f"wrote {predictions_docs_path} (GitHub Pages copy)")
