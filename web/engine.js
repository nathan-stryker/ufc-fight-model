// Client-side port of src/models/predict.py -- must match it exactly.
// Requires MODEL_DATA to be defined (embedded model_data.json payload).

const BASE_RATING = 1500.0;
const METHODS = ["ko", "sub", "dec"];
const METHOD_DIST_FIELDS = [];
for (const tier of ["last5", "career"]) {
  for (const outcome of ["win", "loss"]) {
    for (const m of METHODS) METHOD_DIST_FIELDS.push(`${tier}_${outcome}_${m}`);
  }
}
const WIN_SNAPSHOT_FIELDS = [
  "elo", "fights_entering", "win_pct_entering", "finish_rate_entering", "current_streak_entering",
  "sig_str_landed_per_min", "sig_str_absorbed_per_min", "sig_str_acc",
  "td_avg_per15", "td_acc", "td_def", "sub_att_per15", "ctrl_pct",
];
const DEBUT_DEFAULTS = {
  elo: BASE_RATING, fights_entering: 0, win_pct_entering: NaN, finish_rate_entering: NaN,
  current_streak_entering: 0, sig_str_landed_per_min: NaN, sig_str_absorbed_per_min: NaN,
  sig_str_acc: NaN, td_avg_per15: NaN, td_acc: NaN, td_def: NaN, sub_att_per15: NaN, ctrl_pct: NaN,
};

// ---------------------------------------------------------------------------
// Fighter data indexing
// ---------------------------------------------------------------------------

function buildFighterIndex(fightersPayload) {
  const fields = fightersPayload.fields;
  const byId = new Map();
  const searchList = [];
  for (const row of fightersPayload.rows) {
    const o = {};
    fields.forEach((f, i) => { o[f] = row[i]; });
    byId.set(o.fighter_id, o);
    searchList.push({ id: o.fighter_id, name: o.name, nickname: o.nickname, dob: o.dob_epoch_days });
  }
  return { byId, searchList };
}

// ---------------------------------------------------------------------------
// Tree-ensemble inference (mirrors XGBoost's own prediction logic exactly)
// ---------------------------------------------------------------------------

function walkTree(tree, x) {
  const [left, right, splitIdx, splitCond, defaultLeft, leafVal] = tree;
  let node = 0;
  while (left[node] !== -1) {
    const fi = splitIdx[node];
    const val = x[fi];
    let goLeft;
    if (val === null || val === undefined || Number.isNaN(val)) {
      goLeft = defaultLeft[node] === 1;
    } else {
      // XGBoost casts features to float32 internally before comparing against
      // a split threshold. Comparing in full float64 (as JS numbers naturally
      // are) occasionally flips a branch when a value sits within float32's
      // rounding distance of the threshold -- confirmed as the exact cause of
      // a real ~0.7-point win-probability discrepancy against Python during
      // development (one tree out of 106, one borderline age_years_diff).
      goLeft = Math.fround(val) < Math.fround(splitCond[node]);
    }
    node = goLeft ? left[node] : right[node];
  }
  return leafVal[node];
}

function sigmoid(x) {
  return 1 / (1 + Math.exp(-x));
}

function predictBinary(model, x) {
  let margin = model.base_logit;
  for (const tree of model.trees) margin += walkTree(tree, x);
  return sigmoid(margin);
}

function predictMulticlass(model, x) {
  const margins = model.base_score.slice();
  model.trees.forEach((tree, i) => {
    margins[model.tree_info[i]] += walkTree(tree, x);
  });
  const maxM = Math.max(...margins);
  const exps = margins.map((m) => Math.exp(m - maxM));
  const sum = exps.reduce((a, b) => a + b, 0);
  return exps.map((e) => e / sum);
}

function toVector(featureNames, featDict) {
  return featureNames.map((name) => {
    const v = featDict[name];
    return v === null || v === undefined ? NaN : v;
  });
}

// ---------------------------------------------------------------------------
// Feature construction (mirrors predict.py's build_feature_row / build_method_dist)
// ---------------------------------------------------------------------------

const MS_PER_DAY = 86400000;
function todayEpochDays() {
  const now = new Date();
  return Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / MS_PER_DAY);
}

function buildWinFeats(f, todayDays) {
  const hasSnapshot = f.elo !== null && f.elo !== undefined;
  const feats = {};
  if (!hasSnapshot) {
    Object.assign(feats, DEBUT_DEFAULTS);
    feats.layoff_days_entering = NaN;
  } else {
    for (const k of WIN_SNAPSHOT_FIELDS) feats[k] = f[k] === null ? NaN : f[k];
    feats.layoff_days_entering = f.last_fight_epoch_days != null ? todayDays - f.last_fight_epoch_days : NaN;
  }
  feats.height_in = f.height_in === null || f.height_in === undefined ? NaN : f.height_in;
  feats.reach_in = f.reach_in === null || f.reach_in === undefined ? NaN : f.reach_in;
  feats.age_years = f.dob_epoch_days != null ? (todayDays - f.dob_epoch_days) / 365.25 : NaN;
  for (const cat of ["orthodox", "southpaw", "switch"]) {
    feats[`stance_${cat}`] = f.stance && f.stance.toLowerCase() === cat ? 1.0 : 0.0;
  }
  feats._isDebut = !hasSnapshot;
  return feats;
}

function buildMethodDist(f, priors) {
  const hasHistory = f.career_win_ko !== null && f.career_win_ko !== undefined;
  if (!hasHistory) {
    const d = {};
    for (const field of METHOD_DIST_FIELDS) {
      const m = field.split("_").pop();
      d[field] = priors[m];
    }
    return d;
  }
  const d = {};
  for (const field of METHOD_DIST_FIELDS) d[field] = f[field] === null ? NaN : f[field];
  return d;
}

function computeAlignment(distA, distB, aIsFavorite) {
  const [favDist, dogDist] = aIsFavorite ? [distA, distB] : [distB, distA];
  const align = {};
  for (const tier of ["last5", "career"]) {
    for (const m of METHODS) {
      align[`align_fav_${m}_${tier}`] = favDist[`${tier}_win_${m}`] * dogDist[`${tier}_loss_${m}`];
      align[`align_upset_${m}_${tier}`] = dogDist[`${tier}_win_${m}`] * favDist[`${tier}_loss_${m}`];
    }
  }
  return align;
}

function buildDiffDict(featsA, featsB, baseCols) {
  const d = {};
  for (const c of baseCols) d[`${c}_diff`] = featsA[c] - featsB[c];
  return d;
}

// ---------------------------------------------------------------------------
// Full prediction (mirrors predict.py's predict_full)
// ---------------------------------------------------------------------------

function blendWithEloBaseline(xgbProb, eloProb, w) {
  return w * xgbProb + (1 - w) * eloProb;
}

function eloLogregProb(eloDiff, logreg) {
  const d = Number.isNaN(eloDiff) ? 0.0 : eloDiff;
  return sigmoid(logreg.intercept + logreg.coef * d);
}

function predictFull(fighterA, fighterB, scheduledRounds, model) {
  const todayDays = todayEpochDays();
  const featsA = buildWinFeats(fighterA, todayDays);
  const featsB = buildWinFeats(fighterB, todayDays);

  const baseCols = model.win_model.features.map((n) => n.slice(0, -"_diff".length));
  const rowAB = buildDiffDict(featsA, featsB, baseCols);
  const rowBA = buildDiffDict(featsB, featsA, baseCols);

  const xgbAB = predictBinary(model.win_model, toVector(model.win_model.features, rowAB));
  const xgbBA = predictBinary(model.win_model, toVector(model.win_model.features, rowBA));
  const blendedAB = blendWithEloBaseline(xgbAB, eloLogregProb(rowAB.elo_diff, model.elo_logreg), model.blend_weight);
  const blendedBA = blendWithEloBaseline(xgbBA, eloLogregProb(rowBA.elo_diff, model.elo_logreg), model.blend_weight);
  const probAWins = 0.5 * (blendedAB + (1 - blendedBA));
  const probBWins = 1.0 - probAWins;

  const distA = buildMethodDist(fighterA, model.method_priors);
  const distB = buildMethodDist(fighterB, model.method_priors);
  const aIsFavorite = featsA.elo >= featsB.elo;
  const align = computeAlignment(distA, distB, aIsFavorite);

  const rowMethodA = Object.assign({}, rowAB, align);
  const rowMethodB = Object.assign({}, rowBA, align);
  const methodProbsA = predictMulticlass(model.method_model, toVector(model.method_model.features, rowMethodA));
  const methodProbsB = predictMulticlass(model.method_model, toVector(model.method_model.features, rowMethodB));
  const methodClasses = model.method_model.classes;
  const pMethodGivenA = {}, pMethodGivenB = {};
  methodClasses.forEach((c, i) => { pMethodGivenA[c] = methodProbsA[i]; pMethodGivenB[c] = methodProbsB[i]; });
  const methodOverall = {};
  methodClasses.forEach((c) => { methodOverall[c] = probAWins * pMethodGivenA[c] + probBWins * pMethodGivenB[c]; });

  const roundRows = [], roundWeights = [], rowMeta = [];
  for (const [side, pWins, rowDiff, pMethodGiven] of [["a", probAWins, rowAB, pMethodGivenA], ["b", probBWins, rowBA, pMethodGivenB]]) {
    for (const m of ["ko", "sub"]) {
      roundRows.push(Object.assign({}, rowDiff, align, {
        scheduled_rounds: scheduledRounds, is_ko: m === "ko" ? 1.0 : 0.0, is_sub: m === "sub" ? 1.0 : 0.0,
      }));
      roundWeights.push(pWins * pMethodGiven[m]);
      rowMeta.push([side, m]);
    }
  }
  const numRoundClasses = model.round_model.num_class;
  const roundDistFull = new Array(numRoundClasses).fill(0);
  let pFinish = 0;
  // Per (fighter, method) conditional round distribution -- P(round=r | that
  // fighter wins by that specific method), not yet marginalized away. Needed
  // for prop markets like "Fighter A by KO/TKO, Round 2", which the combined
  // roundGivenFinish below can't answer since it's already summed across both
  // fighters and both finish methods.
  const condRoundByWinMethod = { a: {}, b: {} };
  roundRows.forEach((row, idx) => {
    const probs = predictMulticlass(model.round_model, toVector(model.round_model.features, row));
    const w = roundWeights[idx];
    pFinish += w;
    probs.forEach((p, i) => { roundDistFull[i] += p * w; });
    const [side, m] = rowMeta[idx];
    condRoundByWinMethod[side][m] = probs.slice(0, scheduledRounds);
  });
  const roundGivenFinish = {};
  if (pFinish > 1e-9) {
    for (let i = 0; i < scheduledRounds && i < numRoundClasses; i++) roundGivenFinish[i + 1] = roundDistFull[i] / pFinish;
  }

  // Per-fighter method breakdown (P(A wins AND method=m), not just P(method=m)
  // overall) -- needed for prop markets like "Fighter A by Submission", which
  // methodOverall alone can't answer since it's already marginalized over who
  // wins. Mirrors the same addition in src/models/predict.py.
  const methodGivenA = {}, methodGivenB = {};
  methodClasses.forEach((c) => {
    methodGivenA[c] = probAWins * pMethodGivenA[c];
    methodGivenB[c] = probBWins * pMethodGivenB[c];
  });

  return {
    nameA: fighterA.name, nameB: fighterB.name,
    probAWins, probBWins,
    method: methodOverall,
    methodGivenA, methodGivenB,
    condRoundByWinMethod,
    pFinish,
    roundGivenFinish,
    scheduledRounds,
    debutA: featsA._isDebut, debutB: featsB._isDebut,
  };
}
