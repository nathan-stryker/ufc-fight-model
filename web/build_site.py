"""Assemble the final self-contained website from the template + engine + model data + UI JS."""
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent

template = (WEB_DIR / "site_template.html").read_text(encoding="utf-8")
engine_js = (WEB_DIR / "engine.js").read_text(encoding="utf-8")
model_data_json = (WEB_DIR / "model_data.json").read_text(encoding="utf-8")
ui_js = (WEB_DIR / "ui.js").read_text(encoding="utf-8")
paper_trade_js = (WEB_DIR / "paper_trade.js").read_text(encoding="utf-8")
predictions_js = (WEB_DIR / "predictions.js").read_text(encoding="utf-8")

out = template.replace("__ENGINE_JS__", engine_js)
out = out.replace("__MODEL_DATA__", f"const MODEL_DATA = {model_data_json};")
out = out.replace("__PAPER_TRADE_JS__", paper_trade_js)
out = out.replace("__PREDICTIONS_JS__", predictions_js)
out = out.replace("__UI_JS__", ui_js)

out_path = WEB_DIR / "site.html"
out_path.write_text(out, encoding="utf-8")
print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")

docs_path = WEB_DIR.parent / "docs" / "index.html"
docs_path.parent.mkdir(exist_ok=True)
docs_path.write_text(out, encoding="utf-8")
print(f"wrote {docs_path} (GitHub Pages copy)")
