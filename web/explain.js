// "Why this pick?" -- per-feature explanation of the win-probability model.
//
// Method: single-path cover-weighted decomposition (the "Saabas value" /
// treeinterpreter approach), not full Shapley-value TreeSHAP. A from-scratch
// port of the exact TreeSHAP EXTEND/UNWIND recursion was tried first and
// failed its own completeness self-check (contributions didn't sum back to
// the model's real margin, off by several percent on every real matchup
// tested) -- rather than ship a subtly-wrong "exact" algorithm, this uses a
// simpler method with a much smaller bug surface that is EXACTLY additive
// by construction (a telescoping sum, not a combinatorial identity that's
// easy to get subtly wrong), and is itself a real, established technique
// -- not an invented heuristic. It answers "which features, along the
// actual decision path this fighter's stats took through each tree, moved
// the prediction the most" rather than exact game-theoretic Shapley
// values -- a fair, still-rigorous answer to "why", just not a claim of
// Shapley-value uniqueness.
//
// Global scope (no IIFE), matching engine.js's convention, since this reuses
// engine.js's buildWinFeats/buildDiffDict/toVector directly -- an
// explanation must be built from the EXACT SAME feature vectors predictFull()
// itself used, never a re-derived copy, or it could explain a different
// prediction than the one on screen.
//
// Requires engine.js to already be loaded (BASE_RATING, buildWinFeats,
// buildDiffDict, toVector, walkTree's float32 comparison convention).

// ---------------------------------------------------------------------------
// Core per-tree decomposition
// ---------------------------------------------------------------------------

// Cover-weighted average leaf value of the subtree rooted at each node,
// computed bottom-up (post-order, via explicit recursion rather than
// assuming any particular node-array ordering). nodeValue[0] (the root) is
// this whole tree's cover-weighted average output -- i.e. its contribution
// to the model's baseline/expected margin, the same quantity real SHAP
// calls the "expected value" -- and nodeValue[leaf] === leafVal[leaf] by
// definition, so walking any root-to-leaf path and summing
// nodeValue[child]-nodeValue[parent] at each step telescopes EXACTLY to
// leafVal(x) - nodeValue[root]. That telescoping identity is what makes
// this method safe to hand-roll: the completeness property isn't something
// that can silently drift, it falls out of the arithmetic by construction.
function computeNodeValues(tree) {
  const [left, right, , , , leafVal] = tree;
  const cover = tree[6];
  const nodeValue = new Array(left.length);
  function compute(node) {
    if (nodeValue[node] !== undefined) return nodeValue[node];
    if (left[node] === -1) {
      nodeValue[node] = leafVal[node];
    } else {
      const l = compute(left[node]), r = compute(right[node]);
      nodeValue[node] = (cover[left[node]] * l + cover[right[node]] * r) / cover[node];
    }
    return nodeValue[node];
  }
  compute(0);
  return nodeValue;
}

// Walks the tree along x's actual decision path (same routing rule as
// engine.js's walkTree(), including the same Math.fround comparison, so
// this visits the exact same leaf predictBinary() would), accumulating
// each split's (nodeValue[child] - nodeValue[node]) delta into `phi` under
// that split's feature index. `phi` is shared/accumulated across all trees
// by the caller, not reset here.
function treeSaabasContribs(tree, x, phi) {
  const [left, right, splitIdx, splitCond, defaultLeft] = tree;
  const nodeValue = computeNodeValues(tree);
  let node = 0;
  while (left[node] !== -1) {
    const fi = splitIdx[node];
    const val = x[fi];
    let next;
    if (val === null || val === undefined || Number.isNaN(val)) {
      next = defaultLeft[node] === 1 ? left[node] : right[node];
    } else {
      next = Math.fround(val) < Math.fround(splitCond[node]) ? left[node] : right[node];
    }
    phi[fi] += nodeValue[next] - nodeValue[node];
    node = next;
  }
}

// This tree's contribution to the model's baseline/expected margin (see
// computeNodeValues' comment) -- confirmed by direct comparison against
// xgboost's own pred_contribs bias column during development (see
// src/export_web_model.py's strip_tree comment).
function treeExpectedValue(tree) {
  return computeNodeValues(tree)[0];
}

// ---------------------------------------------------------------------------
// Whole-model explanation (one orientation)
// ---------------------------------------------------------------------------

function explainMargin(model, x) {
  const phi = new Array(model.features.length).fill(0);
  let base = model.base_logit;
  for (const tree of model.trees) {
    treeSaabasContribs(tree, x, phi);
    base += treeExpectedValue(tree);
  }
  return { phi, base };
}

// ---------------------------------------------------------------------------
// Human-readable presentation
// ---------------------------------------------------------------------------

// Readable name + category for each model feature, used for the "Model
// leaned most on" line. Categories still drive explainWin()'s grouping and
// its intangibles noise filter.
const FACTOR_LABELS = {
  elo_diff: { label: "Recent form (Elo)", category: "intangibles" },
  height_in_diff: { label: "Height", category: "intangibles" },
  reach_in_diff: { label: "Reach", category: "intangibles" },
  age_years_diff: { label: "Age", category: "intangibles" },
  fights_entering_diff: { label: "UFC experience", category: "intangibles" },
  win_pct_entering_diff: { label: "Win rate", category: "intangibles" },
  finish_rate_entering_diff: { label: "Finish rate", category: "intangibles" },
  current_streak_entering_diff: { label: "Current streak", category: "intangibles" },
  layoff_days_entering_diff: { label: "Time since last fight", category: "intangibles" },
  // Named to match the stat rows above them (CAREER_STAT_ROWS) -- e.g. the
  // absorbed-per-minute feature was "Striking defense", which read as the
  // separate "Sig. strike defense" row and could point at the other fighter.
  sig_str_landed_per_min_diff: { label: "Strikes landed / min", category: "striking" },
  sig_str_absorbed_per_min_diff: { label: "Strikes absorbed / min", category: "striking" },
  sig_str_acc_diff: { label: "Strike accuracy", category: "striking" },
  td_avg_per15_diff: { label: "Takedowns / 15 min", category: "grappling" },
  td_acc_diff: { label: "Takedown accuracy", category: "grappling" },
  td_def_diff: { label: "Takedown defense", category: "grappling" },
  sub_att_per15_diff: { label: "Submission attempts / 15 min", category: "grappling" },
  ctrl_pct_diff: { label: "Control time", category: "grappling" },
};

// Shared by the fight card and Fantasy Matchup Breakdown panels.
const BREAKDOWN_CAPTION =
  "Striking, grappling and record numbers cover each fighter's whole UFC career (official UFC fights only -- " +
  "UFC.com also counts Contender Series fights for some fighters, so a few can differ slightly from theirs). " +
  "Recent form is this site's own Elo rating. The model weighs recent fights most, so what it leaned on can " +
  "favor the fighter with the lower career number.";

// ---------------------------------------------------------------------------
// UFC.com-style side-by-side stat comparison for the Breakdown panel
// ---------------------------------------------------------------------------
// The same factors the model uses (and the old diverging-bar rows showed),
// laid out like UFC.com's fight pages: fighter A's number | stat | fighter
// B's number, the better number in that fighter's corner color (user,
// 2026-09-24: keep our data, lay it out like UFC.com; the bars were
// confusing). What the model weighed most is one line underneath.
//
// Every number is a real, checkable one, never a model-internal value: the
// model's own inputs are last-5-fight averages and win/finish rates shrunk
// toward the league average, which never match a fighter's actual record
// (see feedback_displayed_stats_must_match_ufc_com). Striking/grappling are
// UFC career numbers computed from our own fight-by-fight data -- identical
// to UFC.com except that UFC.com also counts Contender Series fights for
// some fighters. Win rate, finish rate and fight count come straight from
// the fighter's UFC fight history.

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const fmtPct = (x) => `${Math.round(x * 100)}%`;
const CAREER_STAT_ROWS = {
  striking: [
    { label: "Strikes landed / min", field: "career_slpm", fmt: (x) => x.toFixed(2), better: "high" },
    { label: "Strike accuracy", field: "career_str_acc", fmt: fmtPct, better: "high" },
    { label: "Strikes absorbed / min", field: "career_sapm", fmt: (x) => x.toFixed(2), better: "low" },
  ],
  grappling: [
    { label: "Takedowns / 15 min", field: "career_td_avg", fmt: (x) => x.toFixed(2), better: "high" },
    { label: "Takedown accuracy", field: "career_td_acc", fmt: fmtPct, better: "high" },
    { label: "Takedown defense", field: "career_td_def", fmt: fmtPct, better: "high" },
    { label: "Submission attempts / 15 min", field: "career_sub_avg", fmt: (x) => x.toFixed(2), better: "high" },
    { label: "Control time", field: "career_ctrl_pct", fmt: fmtPct, better: "high" },
  ],
};

const FINISH_METHODS = new Set(["KO/TKO", "Submission", "TKO - Doctor's Stoppage"]); // = build_features.FINISH_METHODS

// UFC wins/losses/finishes from fighter_history (draws and no-contests
// aren't in it). null for a UFC debut.
function ufcRecord(f, fighterHistory) {
  const hist = fighterHistory && fighterHistory[f.fighter_id];
  if (!hist || !hist.length) return null;
  const wins = hist.filter((h) => h[1] === "W");
  return { wins: wins.length, losses: hist.length - wins.length, finishes: wins.filter((h) => FINISH_METHODS.has(h[2])).length };
}

function formatLayoff(days) {
  if (days == null) return null;
  const months = Math.round(days / 30.44);
  if (months < 1) return `${days} days`;
  return months < 24 ? `${months} mo` : `${(days / 365.25).toFixed(1)} yrs`;
}

function formatHeight(inches) {
  if (inches == null) return null;
  const ft = Math.floor(inches / 12);
  return `${ft}'${Math.round(inches - ft * 12)}"`;
}

function formatStreak(n) {
  if (n == null || n === 0) return null;
  return n > 0 ? `W${n}` : `L${-n}`;
}

function statRowHtml(label, aText, bText, betterSide) {
  const cls = (side) => (betterSide === side ? ` tott-better-${side}` : "");
  return `<div class="tott-row"><div class="tott-val tott-a${cls("a")}">${escHtml(aText == null ? "—" : aText)}</div>` +
    `<div class="tott-label">${escHtml(label)}</div>` +
    `<div class="tott-val tott-b${cls("b")}">${escHtml(bText == null ? "—" : bText)}</div></div>`;
}

function statSectionHtml(title, subtitle, rowsHtml) {
  const sub = subtitle ? `<span class="mono">${escHtml(subtitle)}</span>` : "";
  return `<div class="tape"><div class="tape-title"><span>${escHtml(title)}</span>${sub}</div>${rowsHtml}</div>`;
}

// Top model factors (by |contribution|) as one readable line, from
// explainWin()'s already-computed, already-filtered categories.
function keyFactorsHtml(explanation) {
  const all = CATEGORY_ORDER.flatMap((c) => explanation[c] || []);
  const top = all.filter((f) => f.relativeMagnitude >= 0.25)
    .sort((x, y) => y.relativeMagnitude - x.relativeMagnitude).slice(0, 4);
  if (!top.length) return "";
  const items = top.map((f) => {
    const who = shortFighterName(f.favors === "a" ? explanation.nameA : explanation.nameB);
    return `<span class="key-factor key-factor-${f.favors}">${escHtml(f.label)} <span class="key-factor-who">(${escHtml(who)})</span></span>`;
  }).join("");
  return `<div class="key-factors"><div class="key-factors-label">Model leaned most on</div><div class="key-factors-list">${items}</div></div>`;
}

// The full stat comparison, as an HTML string both pages drop into their
// Breakdown panel. fighterA/fighterB are payload fighter objects; the
// explanation is explainWin()'s output for the same pair.
function statComparisonHtml(fighterA, fighterB, explanation, model) {
  const today = todayEpochDays();
  const names = `<div class="tott-row tott-names"><div class="tott-val tott-a">${escHtml(shortFighterName(fighterA.name))}</div>` +
    `<div class="tott-label"></div><div class="tott-val tott-b">${escHtml(shortFighterName(fighterB.name))}</div></div>`;

  // One row from a per-fighter getter. `better` is "high"/"low" to color
  // the better number, or omitted where more isn't simply better (height,
  // age, layoff...).
  const row = (label, get, fmt, better) => {
    const a = get(fighterA), b = get(fighterB);
    let side = null;
    if (better && a != null && b != null && a !== b) side = (better === "high") === (a > b) ? "a" : "b";
    return statRowHtml(label, a != null ? fmt(a) : null, b != null ? fmt(b) : null, side);
  };
  const careerRows = (rows) => rows.map((r) => row(r.label, (f) => f[r.field], r.fmt, r.better)).join("");

  const recA = ufcRecord(fighterA, model.fighter_history), recB = ufcRecord(fighterB, model.fighter_history);
  const rec = (f) => (f === fighterA ? recA : recB);
  const intangibles = [
    row("Recent form (Elo)", (f) => (f.elo != null ? Math.round(f.elo) : null), String, "high"),
    row("Height", (f) => f.height_in, formatHeight),
    row("Reach", (f) => f.reach_in, (x) => `${x}"`),
    row("Age", (f) => (f.dob_epoch_days != null ? Math.floor((today - f.dob_epoch_days) / 365.25) : null), String),
    row("UFC experience", (f) => (rec(f) ? rec(f).wins + rec(f).losses : 0), (n) => (n ? `${n} fights` : "Debut")),
    row("Win rate", (f) => (rec(f) ? rec(f).wins / (rec(f).wins + rec(f).losses) : null), fmtPct, "high"),
    row("Finish rate", (f) => (rec(f) && rec(f).wins ? rec(f).finishes / rec(f).wins : null), fmtPct, "high"),
    row("Current streak", (f) => (rec(f) ? f.current_streak_entering : null), (n) => formatStreak(n) || "—", "high"),
    row("Time since last fight", (f) => (f.last_fight_epoch_days != null && rec(f) ? today - f.last_fight_epoch_days : null), formatLayoff),
    row("Stance", (f) => f.stance, String),
  ].join("");
  // A UFC debut shows their pre-UFC pro record when the card scraper found one.
  const recordText = (f, r) => {
    if (r) return `${r.wins}-${r.losses}`;
    const pre = model.prefight_records && model.prefight_records[f.fighter_id];
    return pre && pre.fights && pre.fights.length ? `Debut (${pre.wins}-${pre.losses} pro)` : "Debut";
  };
  const recordRow = statRowHtml("UFC record", recordText(fighterA, recA), recordText(fighterB, recB));

  return `<div class="tape">${names}</div>` +
    statSectionHtml("Striking", "UFC career", careerRows(CAREER_STAT_ROWS.striking)) +
    statSectionHtml("Grappling", "UFC career", careerRows(CAREER_STAT_ROWS.grappling)) +
    statSectionHtml("Intangibles", null, recordRow + intangibles) +
    dataGapHtml(fighterA, fighterB, model) +
    keyFactorsHtml(explanation);
}

// A blank on a UFC debut is expected. A blank on a fighter who HAS UFC fights
// means this project's data is missing something it should have, which also
// quietly weakens that prediction -- called out in words so every visitor
// sees it (user request, 2026-09-08). Takedown accuracy/defense are left out:
// those are legitimately blank when nobody attempted a takedown.
const DATA_GAP_FIELDS = [
  ["height_in", "height"], ["reach_in", "reach"], ["dob_epoch_days", "date of birth"],
  ["career_slpm", "striking stats"],
];
function dataGapHtml(fighterA, fighterB, model) {
  const notes = [fighterA, fighterB].map((f) => {
    const hist = model.fighter_history && model.fighter_history[f.fighter_id];
    if (!hist || !hist.length) return null;
    const missing = DATA_GAP_FIELDS.filter(([field]) => f[field] == null).map(([, label]) => label);
    return missing.length ? `${f.name} has UFC fights but no ${missing.join(", ")} on file -- the model used its learned default.` : null;
  }).filter(Boolean);
  return notes.length ? `<div class="data-gap-note">Data gap: ${notes.map(escHtml).join(" ")}</div>` : "";
}

// "Raul Rosas Jr." -> "Rosas Jr.", "Raoni Barcelos" -> "Barcelos", mononyms
// unchanged -- for compact "A vs B" section labels.
const NAME_SUFFIXES = new Set(["Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV"]);
function shortFighterName(name) {
  const parts = String(name).trim().split(/\s+/);
  if (parts.length === 1) return parts[0];
  const last = parts[parts.length - 1];
  return NAME_SUFFIXES.has(last) && parts.length > 2 ? `${parts[parts.length - 2]} ${last}` : last;
}
const STANCE_FEATURES = ["stance_orthodox_diff", "stance_southpaw_diff", "stance_switch_diff"];
const CATEGORY_ORDER = ["striking", "grappling", "intangibles"];

function stanceLabel(f) {
  for (const cat of ["orthodox", "southpaw", "switch"]) {
    if (f[`stance_${cat}`] === 1.0) return cat[0].toUpperCase() + cat.slice(1);
  }
  return null;
}

// One row per model feature with its symmetrized contribution; the three
// stance one-hots are summed into a single "Stance matchup" row.
function factorRows(phiFinal, featureNames, featsA, featsB) {
  const rows = [];
  let stanceShap = 0;
  featureNames.forEach((f, i) => {
    if (STANCE_FEATURES.includes(f)) { stanceShap += phiFinal[i]; return; }
    const meta = FACTOR_LABELS[f];
    if (!meta) return; // shouldn't happen, but never show an unlabeled raw feature name
    rows.push({ shap: phiFinal[i], label: meta.label, category: meta.category });
  });
  if (stanceLabel(featsA) && stanceLabel(featsB)) {
    rows.push({ shap: stanceShap, label: "Stance matchup", category: "intangibles" });
  }
  return rows;
}

// Top-level entry point: mirrors predictFull()'s own AB/BA symmetrization
// (see engine.js) applied one layer down, in additive log-odds space where
// these contributions are natively defined and summable. Deliberately does NOT
// attempt to attribute the separate Elo-baseline blend predictFull() also
// applies (blendWithEloBaseline) to individual features -- that's a single
// scalar blend of two whole-model probabilities, not a function of these 20
// features, so decomposing it per-feature would be invented, not derived.
function explainWin(fighterA, fighterB, model) {
  const todayDays = todayEpochDays();
  const featsA = buildWinFeats(fighterA, todayDays);
  const featsB = buildWinFeats(fighterB, todayDays);
  const baseCols = model.win_model.features.map((n) => n.slice(0, -"_diff".length));
  const rowAB = buildDiffDict(featsA, featsB, baseCols);
  const rowBA = buildDiffDict(featsB, featsA, baseCols);
  const xAB = toVector(model.win_model.features, rowAB);
  const xBA = toVector(model.win_model.features, rowBA);

  const { phi: phiAB, base: baseAB } = explainMargin(model.win_model, xAB);
  const { phi: phiBA, base: baseBA } = explainMargin(model.win_model, xBA);
  const phiFinal = phiAB.map((v, i) => 0.5 * (v - phiBA[i]));
  const baseFinal = 0.5 * (baseAB - baseBA);

  // Self-check (completeness/efficiency property): contributions + base
  // must reproduce the model's own margin exactly. Cheap, catches most
  // implementation bugs without needing a Python round-trip -- logged, not
  // thrown, so a rare float-rounding edge case degrades gracefully instead
  // of breaking the page.
  const marginAB = model.win_model.base_logit + model.win_model.trees.reduce((s, t) => s + walkTree(t, xAB), 0);
  const marginBA = model.win_model.base_logit + model.win_model.trees.reduce((s, t) => s + walkTree(t, xBA), 0);
  const expectedMargin = 0.5 * (marginAB - marginBA);
  const gotMargin = baseFinal + phiFinal.reduce((a, b) => a + b, 0);
  if (Math.abs(gotMargin - expectedMargin) > 1e-4) {
    console.warn("explainWin: completeness check failed", { expectedMargin, gotMargin });
  }

  const rows = factorRows(phiFinal, model.win_model.features, featsA, featsB);
  // Relative to the single largest factor across ALL categories, not a
  // per-category scale -- so a glance across sections still shows which
  // ones actually mattered most to THIS matchup, not three independently
  // normalized bar charts that make a minor category look as loud as a
  // major one. This is a ranking aid, not a claim about percentage-points
  // of win probability (these contributions live in log-odds space;
  // converting to probability points per-feature isn't mathematically
  // valid through a sigmoid).
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.shap)), 1e-9);
  const toFactor = (r) => ({
    label: r.label,
    favors: r.shap >= 0 ? "a" : "b",
    relativeMagnitude: Math.abs(r.shap) / maxAbs,
  });
  // Intangibles (age, reach, layoff, stance, etc.) run 8-10 factors deep
  // per matchup -- unlike Striking/Grappling, which are core performance
  // stats worth showing regardless of size, most individual intangibles
  // barely move the model's pick. Below this share of the matchup's
  // single biggest factor, a factor reads as noise, not signal -- drop it
  // rather than pad the panel with near-zero rows (user feedback,
  // 2026-09-10: "we do not need unnecessary info clogging our page").
  // Striking/Grappling are never filtered.
  const MIN_INTANGIBLE_MAGNITUDE = 0.08;

  const categories = {};
  for (const cat of CATEGORY_ORDER) {
    let catRows = rows.filter((r) => r.category === cat).sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap)).map(toFactor);
    if (cat === "intangibles") {
      catRows = catRows.filter((f) => f.relativeMagnitude >= MIN_INTANGIBLE_MAGNITUDE);
    }
    categories[cat] = catRows;
  }
  return {
    nameA: fighterA.name, nameB: fighterB.name,
    styleA: fighterA.style || null, styleB: fighterB.style || null,
    ...categories,
  };
}
