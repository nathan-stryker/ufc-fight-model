"""
Download the country flag SVGs actually needed (i.e. that appear in
data/processed/fighter_nationality.csv) from lipis/flag-icons (MIT licensed,
github.com/lipis/flag-icons) into web/flags/ as a local cache -- checked in
to the repo like web/fonts/, not re-fetched on every site build.

Run: python -m src.fetch_flags
Writes: web/flags/{iso_code}.svg (lowercase, matching flag-icons' own naming)
"""
from pathlib import Path

import pandas as pd
import requests

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
FLAGS_DIR = Path(__file__).resolve().parents[1] / "web" / "flags"
RAW_URL = "https://raw.githubusercontent.com/lipis/flag-icons/main/flags/4x3/{code}.svg"

# Sherdog shows UK constituent-country flags (England/Scotland/Wales/N.
# Ireland) rather than the single ISO "GB" flag, so its flag-image codes
# aren't standard ISO 3166-1 -- flag-icons has these too, just under
# different (non-ISO) filenames. Confirmed by checking which raw codes
# actually showed up in a real scrape (EN, WA) rather than guessing all
# four up front; SCT/NIR added defensively in case they appear later.
# Fetched under the flag-icons name but CACHED under Sherdog's own code, so
# nothing downstream needs to know this remapping exists.
CODE_REMAP = {"en": "gb-eng", "wa": "gb-wls", "sct": "gb-sct", "nir": "gb-nir"}


def main():
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    nat = pd.read_csv(PROCESSED_DIR / "fighter_nationality.csv")
    codes = sorted(nat["iso_code"].dropna().str.lower().unique())
    print(f"{len(codes)} unique country codes needed: {codes}")

    fetched, cached, missing = 0, 0, []
    for code in codes:
        out_path = FLAGS_DIR / f"{code}.svg"
        if out_path.exists():
            cached += 1
            continue
        fetch_code = CODE_REMAP.get(code, code)
        resp = requests.get(RAW_URL.format(code=fetch_code), timeout=15)
        if resp.status_code == 200 and resp.text.strip().startswith("<svg"):
            out_path.write_text(resp.text, encoding="utf-8")
            fetched += 1
        else:
            missing.append(code)

    print(f"fetched {fetched}, already cached {cached}, missing {len(missing)}")
    if missing:
        print(f"no flag-icons entry for: {missing} -- these fighters will show no flag on the site")


if __name__ == "__main__":
    main()
