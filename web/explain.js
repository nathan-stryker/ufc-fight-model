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

// label + category + how to phrase the raw differential; NaN handling is
// separate (see factorRows below) since it depends on which SIDE is
// missing, not just the feature. Category buckets (striking/grappling/
// intangibles) match the Breakdown panel's own section headings -- height/
// reach/stance aren't literally "intangible" but there's no 4th bucket in
// the requested layout, and physical attributes sit more naturally next to
// experience/form than next to a strike-volume stat.
const FACTOR_LABELS = {
  elo_diff: { label: "Recent form (Elo rating)", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v)} pts` },
  height_in_diff: { label: "Height", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} in` },
  reach_in_diff: { label: "Reach", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} in` },
  age_years_diff: { label: "Age", category: "intangibles", fmt: (v) => `${Math.abs(v).toFixed(1)} yrs ${v < 0 ? "younger" : "older"}` },
  fights_entering_diff: { label: "UFC experience", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v)} fights` },
  win_pct_entering_diff: { label: "Win rate", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
  finish_rate_entering_diff: { label: "Finish rate", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
  current_streak_entering_diff: { label: "Current streak", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v)} fights` },
  layoff_days_entering_diff: { label: "Time since last fight", category: "intangibles", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v)} days` },
  sig_str_landed_per_min_diff: { label: "Striking output", category: "striking", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} landed/min` },
  sig_str_absorbed_per_min_diff: { label: "Striking defense", category: "striking", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} absorbed/min` },
  sig_str_acc_diff: { label: "Striking accuracy", category: "striking", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
  td_avg_per15_diff: { label: "Takedown rate", category: "grappling", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} per 15 min` },
  td_acc_diff: { label: "Takedown accuracy", category: "grappling", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
  td_def_diff: { label: "Takedown defense", category: "grappling", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
  sub_att_per15_diff: { label: "Submission attempts", category: "grappling", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} per 15 min` },
  ctrl_pct_diff: { label: "Grappling control time", category: "grappling", fmt: (v) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)} pts` },
};
const STANCE_FEATURES = ["stance_orthodox_diff", "stance_southpaw_diff", "stance_switch_diff"];
const CATEGORY_ORDER = ["striking", "grappling", "intangibles"];

function stanceLabel(f) {
  for (const cat of ["orthodox", "southpaw", "switch"]) {
    if (f[`stance_${cat}`] === 1.0) return cat[0].toUpperCase() + cat.slice(1);
  }
  return null;
}

// featsA/featsB are the SAME per-fighter feature dicts predictFull() built
// via buildWinFeats() -- passed in rather than recomputed, so a NaN here is
// guaranteed to be the exact same NaN the model actually saw, not a second
// independent (and possibly different) derivation. A NaN on a genuine UFC
// debut fighter (featsX._isDebut) is expected -- there's simply no UFC
// record yet. A NaN on a fighter who HAS UFC fights on file is different:
// it means this project's own data is missing something it should have
// (an untracked physical measurement, a round_stats.csv gap, etc.), which
// quietly weakens that one prediction -- phrased distinctly on purpose
// (flagged directly by user request, 2026-09-08) so it's visible to every
// visitor, not just caught if someone happens to notice.
function factorRows(phiFinal, featureNames, featsA, featsB, nameA, nameB) {
  const rows = [];
  let stanceShap = 0;
  featureNames.forEach((f, i) => {
    if (STANCE_FEATURES.includes(f)) { stanceShap += phiFinal[i]; return; }
    const meta = FACTOR_LABELS[f];
    if (!meta) return; // shouldn't happen, but never show an unlabeled raw feature name
    const base = f.slice(0, -"_diff".length);
    const rawA = featsA[base], rawB = featsB[base];
    let valueText;
    if (Number.isNaN(rawA) || Number.isNaN(rawB)) {
      const missingIsA = Number.isNaN(rawA);
      const missingName = missingIsA ? nameA : nameB;
      const missingIsDebut = missingIsA ? featsA._isDebut : featsB._isDebut;
      valueText = missingIsDebut
        ? `no data yet for ${missingName} (debut) -- model used its learned default`
        : `data gap for ${missingName} on this stat (has UFC fights, but it's not on file) -- model used its learned default`;
    } else {
      valueText = meta.fmt(rawA - rawB);
    }
    rows.push({ shap: phiFinal[i], label: meta.label, valueText, category: meta.category });
  });
  const stanceA = stanceLabel(featsA), stanceB = stanceLabel(featsB);
  if (stanceA && stanceB) {
    rows.push({
      shap: stanceShap, label: "Stance matchup", category: "intangibles",
      valueText: stanceA === stanceB ? `both ${stanceA}` : `${stanceA} vs. ${stanceB}`,
    });
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

  const rows = factorRows(phiFinal, model.win_model.features, featsA, featsB, fighterA.name, fighterB.name);
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
    valueText: r.valueText,
    favors: r.shap >= 0 ? "a" : "b",
    relativeMagnitude: Math.abs(r.shap) / maxAbs,
  });
  const categories = {};
  for (const cat of CATEGORY_ORDER) {
    categories[cat] = rows.filter((r) => r.category === cat).sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap)).map(toFactor);
  }
  return {
    nameA: fighterA.name, nameB: fighterB.name,
    styleA: fighterA.style || null, styleB: fighterB.style || null,
    ...categories,
  };
}
