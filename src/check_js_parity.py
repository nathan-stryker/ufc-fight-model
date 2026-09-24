"""JS-vs-Python parity check for the website's inference engine.

Runs web/engine.js's predictFull() in an embedded V8 (py_mini_racer) against
web/model_data.json and compares it to src.models.predict's output for the
same matchups. Exits non-zero if any win/method probability differs by more
than TOLERANCE percentage points.

Usage:
    python -m src.check_js_parity                      # default matchups
    python -m src.check_js_parity "A|B|5" "C|D|3|Women's Flyweight"
                                                       # custom; optional 4th field = bout weight class

Deliberately calls os._exit() at the end: MiniRacer's V8 teardown can hang
the interpreter on Windows, which once stalled an unattended run for the
full 5-minute tool timeout after the check itself had already passed.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 0.1  # percentage points

# Covers both weight-class paths the method model takes (bout weight class
# given vs. inferred from the fighters), a women's bout, a cross-division
# matchup, and a UFC-debut fighter (NaN strike stats, prior-based method
# history).
DEFAULT_MATCHUPS = [
    ("Islam Makhachev", "Ilia Topuria", 5, None),
    ("Raul Rosas Jr.", "Raoni Barcelos", 5, "Bantamweight"),
    ("Melissa Amaya", "Valesca Machado", 3, "Women's Strawweight"),
    ("Alex Pereira", "Tom Aspinall", 5, None),
    ("Mehemmedeli Osmanli", "Ilimbek Akylbek Uulu", 3, "Bantamweight"),
]


def python_prediction(a, b, rounds, weightclass):
    cmd = [sys.executable, "-m", "src.models.predict", a, b, "--rounds", str(rounds)]
    if weightclass:
        cmd += ["--weightclass", weightclass]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    def pct(label):
        m = re.search(rf"^\s*{re.escape(label)}: ([\d.]+)%", out, re.M)
        return float(m.group(1)) if m else None
    return {
        "probAWins": pct(a),
        "dec": pct("Decision"), "ko": pct("KO/TKO"), "sub": pct("Submission"),
    }


def main():
    from py_mini_racer import MiniRacer

    matchups = DEFAULT_MATCHUPS
    if len(sys.argv) > 1:
        matchups = [(p[0], p[1], int(p[2]), p[3] if len(p) > 3 else None) for p in (s.split("|") for s in sys.argv[1:])]

    ctx = MiniRacer()
    ctx.eval("var MODEL_DATA = " + (ROOT / "web/model_data.json").read_text(encoding="utf-8") + ";")
    ctx.eval((ROOT / "web/engine.js").read_text(encoding="utf-8"))
    ctx.eval(
        "var IDX = buildFighterIndex(MODEL_DATA.fighters);"
        "function byName(n){ const s = IDX.searchList.filter(x => x.name === n);"
        " if (s.length !== 1) throw new Error(n + ': ' + s.length + ' roster matches');"
        " return IDX.byId.get(s[0].id); }"
    )

    failed = False
    for a, b, rounds, weightclass in matchups:
        js = json.loads(ctx.eval(
            f"JSON.stringify(predictFull(byName({json.dumps(a)}), byName({json.dumps(b)}), {rounds}, MODEL_DATA, "
            f"{json.dumps(weightclass)}))"
        ))
        js_vals = {"probAWins": js["probAWins"] * 100,
                   **{k: v * 100 for k, v in js["method"].items()}}
        py_vals = python_prediction(a, b, rounds, weightclass)
        worst = max(abs(js_vals[k] - py_vals[k]) for k in py_vals if py_vals[k] is not None)
        # Python prints 1 decimal, so allow its rounding on top of the tolerance.
        ok = worst <= TOLERANCE + 0.05
        failed |= not ok
        print(f"[{'OK' if ok else 'MISMATCH'}] {a} vs {b} ({rounds} rds, {weightclass or 'inferred'}): "
              f"JS win {js_vals['probAWins']:.2f}% / Py {py_vals['probAWins']:.1f}%  "
              f"method JS dec/ko/sub {js_vals['dec']:.1f}/{js_vals['ko']:.1f}/{js_vals['sub']:.1f}  "
              f"(max diff {worst:.3f}pp)")

    print("parity: PASS" if not failed else "parity: FAIL")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
