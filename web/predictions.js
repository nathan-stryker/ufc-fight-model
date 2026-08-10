// Client-side "My Predictions" log -- deliberately NOT betting-affiliated:
// no odds, no edge, no stake sizing, just "what do you personally think will
// happen." Reuses the same mounting/localStorage/CSV-backup pattern as
// paper_trade.js (see that file for the reasoning), but its own separate
// storage key and CSV schema so the two logs never mix.
(function () {
  const STORAGE_KEY = "ufc_my_predictions_v1";
  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };

  const FIELDS = [
    "pred_id", "logged_at", "event", "fighter_a", "fighter_b", "scheduled_rounds",
    "picked_winner", "picked_method", "picked_round",
    "model_winner", "model_method", "model_round",
    "note", "status", "settled_at",
    "actual_winner", "actual_method", "actual_round",
    "correct_winner", "correct_method", "correct_round",
  ];

  // --- CSV (identical implementation to paper_trade.js -- kept duplicated
  // rather than shared, it's ~30 lines and the two logs are meant to be
  // fully independent files a user could hand off separately) ---
  function parseCsv(text) {
    const rows = [];
    let i = 0, field = "", row = [], inQuotes = false;
    const pushField = () => { row.push(field); field = ""; };
    const pushRow = () => { pushField(); rows.push(row); row = []; };
    while (i < text.length) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          inQuotes = false; i++; continue;
        }
        field += c; i++; continue;
      }
      if (c === '"') { inQuotes = true; i++; continue; }
      if (c === ",") { pushField(); i++; continue; }
      if (c === "\r") { i++; continue; }
      if (c === "\n") { pushRow(); i++; continue; }
      field += c; i++;
    }
    if (field.length || row.length) pushRow();
    if (rows.length === 0) return [];
    const header = rows[0];
    return rows.slice(1).filter((r) => r.length === header.length && r.some((v) => v !== "")).map((r) => {
      const obj = {};
      header.forEach((h, idx) => { obj[h] = r[idx]; });
      return obj;
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function pct(x) {
    return x == null ? "n/a" : (x * 100).toFixed(0) + "%";
  }

  // --- state ---
  let preds = [];
  let matchup = null; // { scheduledRounds, result }
  let storageOk = true;

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      preds = raw ? JSON.parse(raw) : [];
    } catch (e) {
      storageOk = false;
      preds = [];
    }
  }
  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preds));
    } catch (e) {
      storageOk = false;
    }
  }
  function nextId() {
    return `mp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  }

  // Same top-pick derivation as ui.js's renderResult() verdict line -- kept
  // as an independent copy here (not cross-module coupled) since it's just
  // reading fields already on the result object, not re-deriving probabilities.
  function modelVerdict(r) {
    const aWinner = r.probAWins >= 0.5;
    const winner = aWinner ? r.nameA : r.nameB;
    const methodRanked = Object.entries(r.method).sort((x, y) => y[1] - x[1]);
    const method = methodRanked[0][0];
    let round = "";
    if (method !== "dec") {
      const roundRanked = Object.entries(r.roundGivenFinish).sort((x, y) => y[1] - x[1]);
      if (roundRanked.length) round = roundRanked[0][0];
    }
    return { winner, method, round };
  }

  // Only matches a PENDING prediction, not a settled one -- a settled pick
  // means that exact fight already happened and got graded, so a future
  // rematch between the same two fighters (rare but real in MMA) must still
  // be pickable, not silently blocked by an old, already-resolved pick for
  // the same name pair. One active (pending) pick per fight is the actual
  // rule being enforced, not "ever predicted this pair once."
  function findPendingPredictionByFighters(nameA, nameB) {
    return preds.find((p) => p.status === "pending" && (
      (p.fighter_a === nameA && p.fighter_b === nameB) ||
      (p.fighter_a === nameB && p.fighter_b === nameA)
    ));
  }

  // Defense in depth: the UI (buildPickSection below) already refuses to
  // show a submittable form once a pending pick exists for this matchup, so
  // this branch should be unreachable in normal use -- but guarding here too
  // means a duplicate can never get created even via a stale/cached form
  // that didn't get the memo (e.g. two tabs open at once).
  function addPrediction(matchupObj, form) {
    const r = matchupObj.result;
    const existing = findPendingPredictionByFighters(r.nameA, r.nameB);
    if (existing) return existing;
    const mv = modelVerdict(r);
    const pickedWinnerName = form.side === "a" ? r.nameA : r.nameB;
    const pred = {
      pred_id: nextId(),
      logged_at: new Date().toISOString(),
      event: form.event, fighter_a: r.nameA, fighter_b: r.nameB,
      scheduled_rounds: matchupObj.scheduledRounds,
      picked_winner: pickedWinnerName,
      picked_method: form.method || "",
      picked_round: form.round || "",
      model_winner: mv.winner, model_method: mv.method, model_round: mv.round,
      note: form.note || "",
      status: "pending", settled_at: "",
      actual_winner: "", actual_method: "", actual_round: "",
      correct_winner: "", correct_method: "", correct_round: "",
    };
    preds.push(pred);
    save();
    return pred;
  }

  // Recomputed fresh from the raw picked_*/actual_* fields every time,
  // rather than trusted from stored correct_* flags -- a real bug found via
  // testing: JSON round-trips a JS boolean fine, but a CSV round-trip turns
  // it into the STRING "true"/"false", and a naive `=== true` check on a
  // re-imported row silently stops counting a genuinely correct pick as
  // correct. Returns null for "not applicable" (no pick made, or a decision
  // has no round to grade).
  function isCorrectWinner(p) {
    return p.picked_winner === p.actual_winner;
  }
  function isCorrectMethod(p) {
    if (!p.picked_method) return null;
    return p.picked_method === p.actual_method;
  }
  function isCorrectRound(p) {
    if (!p.picked_method || !p.picked_round || p.actual_method === "dec") return null;
    return String(p.picked_round) === String(p.actual_round);
  }
  // Same idea as isCorrectRound but grades the MODEL's round-of-finish call
  // (model_round) instead of your own pick. model_round is only ever set
  // when the model's top method pick was itself a finish (see
  // modelVerdict() -- round is left "" when method === "dec"), so the
  // model_method check below is really just belt-and-suspenders; the
  // actual_method === "dec" check is the one that matters (nothing to grade
  // a round against when the real fight went the distance).
  function isCorrectModelRound(p) {
    if (p.model_method === "dec" || !p.model_round || p.actual_method === "dec") return null;
    return String(p.model_round) === String(p.actual_round);
  }

  function settlePrediction(predId, actual) {
    const p = preds.find((x) => String(x.pred_id) === String(predId));
    if (!p) return;
    p.actual_winner = actual.winner;
    p.actual_method = actual.method;
    p.actual_round = actual.method === "dec" ? "" : actual.round;
    p.status = "settled";
    p.settled_at = new Date().toISOString();
    // Stored for readability if the CSV is opened directly -- report math
    // below never trusts these back, it recomputes from picked_*/actual_*.
    p.correct_winner = isCorrectWinner(p);
    p.correct_method = isCorrectMethod(p);
    p.correct_round = isCorrectRound(p);
    save();
  }

  // Same raw-string -> bucket mapping as src/features/method_features.py's
  // METHOD_BUCKET, duplicated here (not imported -- this is a JS file with
  // no build step tying it to the Python source) so a bout's real `method`
  // string (as shipped in last_results_data.json) can be compared against
  // a prediction's picked_method ("ko"/"sub"/"dec"). An unrecognized raw
  // string (a method text this list doesn't cover) intentionally does NOT
  // fall back to a guess -- see autoSettleFromResults below.
  const METHOD_BUCKET = {
    "KO/TKO": "ko",
    "TKO - Doctor's Stoppage": "ko",
    "Submission": "sub",
    "Decision - Unanimous": "dec",
    "Decision - Split": "dec",
    "Decision - Majority": "dec",
    // fights.csv always stores a qualified "Decision - X" form, but at least
    // one currently-cached last_results snapshot has the bare "Decision"
    // string instead (found by testing against real cached data, not
    // guessed) -- unambiguous either way (any kind of decision is the "dec"
    // bucket), so mapping it directly is safe, not a guess.
    "Decision": "dec",
  };

  // Auto-settles any PENDING prediction whose fighter pair matches a bout in
  // `bouts` (a Last Week's Results payload) that already has a real,
  // determinate outcome -- lets a logged prediction mark itself correct/
  // incorrect the moment its fight's real result is already known to the
  // site, instead of leaving it "pending" forever until the user manually
  // re-enters a result they can already see on Last Week's Results. Skips
  // (does NOT guess) a bout that's a draw/no-contest, or whose method string
  // isn't one of the recognized buckets above -- same "omit, don't guess"
  // rule as the rest of this project's data handling. Idempotent: already-
  // settled predictions are filtered out up front, so calling this again on
  // a later page load (nothing new to settle) is a harmless no-op. Called
  // from ui.js (home page) and results_template.html (results.html) --
  // wherever Last Week's Results data is available.
  function autoSettleFromResults(bouts) {
    if (!bouts || !bouts.length) return 0;
    load();
    let settledCount = 0;
    preds.filter((p) => p.status === "pending").forEach((p) => {
      const bout = bouts.find((b) =>
        (b.nameA === p.fighter_a && b.nameB === p.fighter_b) ||
        (b.nameA === p.fighter_b && b.nameB === p.fighter_a)
      );
      if (!bout) return;
      if (bout.outcome !== "a" && bout.outcome !== "b") return;
      const bucket = METHOD_BUCKET[bout.method];
      if (!bucket) return;
      const winnerName = bout.outcome === "a" ? bout.nameA : bout.nameB;
      settlePrediction(p.pred_id, { winner: winnerName, method: bucket, round: bout.round });
      settledCount++;
    });
    return settledCount;
  }

  function deletePrediction(predId) {
    preds = preds.filter((p) => String(p.pred_id) !== String(predId));
    save();
  }

  function computeReport() {
    const settled = preds.filter((p) => p.status === "settled");
    const n = settled.length;
    const winnerHits = settled.filter((p) => isCorrectWinner(p)).length;
    const methodCalled = settled.filter((p) => isCorrectMethod(p) !== null);
    const methodHits = methodCalled.filter((p) => isCorrectMethod(p) === true).length;
    const roundCalled = settled.filter((p) => isCorrectRound(p) !== null);
    const roundHits = roundCalled.filter((p) => isCorrectRound(p) === true).length;
    const modelRoundCalled = settled.filter((p) => isCorrectModelRound(p) !== null);
    const modelRoundHits = modelRoundCalled.filter((p) => isCorrectModelRound(p) === true).length;
    const agreedWithModel = settled.filter((p) => p.picked_winner === p.model_winner).length;
    return {
      n,
      winnerAcc: n ? winnerHits / n : null,
      methodAcc: methodCalled.length ? methodHits / methodCalled.length : null,
      methodN: methodCalled.length,
      roundAcc: roundCalled.length ? roundHits / roundCalled.length : null,
      roundN: roundCalled.length,
      modelRoundAcc: modelRoundCalled.length ? modelRoundHits / modelRoundCalled.length : null,
      modelRoundN: modelRoundCalled.length,
      agreedWithModelRate: n ? agreedWithModel / n : null,
    };
  }

  // ---------------------------------------------------------------------------
  // Three mount points, not one. Viewing/settling EXISTING predictions and
  // the track-record report are pure localStorage reads, no model needed at
  // all, so that half lives on its own lightweight predictions.html page (or
  // as a compact teaser in the home page's sidebar) -- mountHistory(),
  // unchanged by this comment. "Add a prediction" always needs a LIVE
  // matchup result, but now has two independent call sites for that: the
  // singleton Fantasy Matchup page (predict.html, a manual "pick any two
  // fighters" toy -- mountAdd()/setMatchup(), module-global `matchup`), and
  // the real fight card's own per-bout "Make Your Pick" panel, which already
  // has its own live result computed on page load for every predictable
  // bout (see ui.js's predictFull() call in boutRowHtml()) -- no picker
  // needed there at all. mountCardPick() takes that result directly, no
  // module-global involved, so any number of fight-card rows can have their
  // own independent pick form open at once.
  let addRoot = null;
  let historyRoot = null;
  let historyOpts = {};

  function el(tag, className, html) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  // Builds the actual pick form (winner/method/round/event/note + submit
  // button) for a given {scheduledRounds, result} matchup -- used both by
  // the singleton Fantasy Matchup page (matchup fed via setMatchup()) and
  // by the fight card's per-bout "Make Your Pick" panels (one independent
  // instance per expanded row, matchup fixed at mount time). Classnames,
  // not ids, on the inputs -- multiple instances can be mounted on the same
  // page at once (several expanded fight-card rows), and querySelector
  // scoped to `wrap` finds the right descendant either way, but duplicate
  // ids across simultaneous instances would still be invalid HTML.
  function buildPickFormBase(matchupObj) {
    const wrap = el("div", "pt-add");
    const r = matchupObj.result;
    wrap.appendChild(el("div", "pt-matchup-label mono", `Predicting: ${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}`));

    const winnerRow = el("div", "pt-row", `<label>Winner</label>
      <select class="mp-side">
        <option value="a">${escapeHtml(r.nameA)}</option>
        <option value="b">${escapeHtml(r.nameB)}</option>
      </select>`);
    wrap.appendChild(winnerRow);

    const methodRow = el("div", "pt-row", `<label>Method</label>
      <select class="mp-method">
        <option value="">No pick (winner only)</option>
        <option value="dec">Decision</option>
        <option value="ko">KO/TKO</option>
        <option value="sub">Submission</option>
      </select>`);
    wrap.appendChild(methodRow);

    const roundOptions = Array.from({ length: matchupObj.scheduledRounds }, (_, i) => i + 1)
      .map((n) => `<option value="${n}">Round ${n}</option>`).join("");
    const roundRow = el("div", "pt-row", `<label>Round</label>
      <select class="mp-round">
        <option value="">No pick (any round)</option>
        ${roundOptions}
      </select>`);
    roundRow.hidden = true;
    wrap.appendChild(roundRow);

    wrap.appendChild(el("div", "pt-row", `<label>Event</label><input type="text" class="mp-event" placeholder="e.g. UFC 300" value="${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}">`));
    wrap.appendChild(el("div", "pt-row", `<label>Note</label><input type="text" class="mp-note" placeholder="optional -- why you think that"></div>`));

    const addBtn = el("button", "predict-btn pt-add-btn", "Log My Prediction");
    addBtn.type = "button";
    wrap.appendChild(addBtn);

    const methodSel = methodRow.querySelector(".mp-method");
    methodSel.addEventListener("change", () => {
      roundRow.hidden = methodSel.value === "" || methodSel.value === "dec";
    });

    function readForm() {
      return {
        side: wrap.querySelector(".mp-side").value,
        method: methodSel.value,
        round: roundRow.hidden ? "" : wrap.querySelector(".mp-round").value,
        event: wrap.querySelector(".mp-event").value.trim(),
        note: wrap.querySelector(".mp-note").value.trim(),
      };
    }

    return { wrap, addBtn, readForm };
  }

  // Shown INSTEAD of the pick form whenever a pending prediction already
  // exists for this matchup -- one active pick per fight, enforced by never
  // even offering a second form, not just by rejecting a second submit.
  // "Remove pick" is the escape hatch for a genuine correction (fat-
  // fingered the wrong round, changed your mind) -- deletes the pick and
  // hands back to `opts.onChange` to decide what to re-render in its place.
  function buildLockedPickView(pred, opts) {
    const wrap = el("div", "pt-add pt-locked");
    wrap.appendChild(el("div", "pt-matchup-label mono", `${escapeHtml(pred.fighter_a)} vs ${escapeHtml(pred.fighter_b)}`));
    wrap.appendChild(el("div", "pt-logged-confirm", `Your pick: ${escapeHtml(pickSummary(pred))}`));
    const removeBtn = el("button", "clear-btn pt-remove-pick-btn", "Remove pick");
    removeBtn.type = "button";
    removeBtn.addEventListener("click", () => {
      deletePrediction(pred.pred_id);
      if (opts && opts.onChange) opts.onChange();
    });
    wrap.appendChild(removeBtn);
    return wrap;
  }

  // Fantasy Matchup page (singleton, module-global `matchup`) -- shows the
  // locked view (not a blank form) once a pending pick exists for the
  // current matchup, same one-pick-per-fight rule as the fight-card panels
  // below. Removing the pick falls back to a fresh form via renderAll().
  function renderAddForm() {
    if (!matchup) {
      const empty = el("div", "pt-add");
      empty.appendChild(el("div", "pt-empty-hint", "Call a matchup above to log your own prediction on it."));
      return empty;
    }
    const existing = findPendingPredictionByFighters(matchup.result.nameA, matchup.result.nameB);
    if (existing) {
      return buildLockedPickView(existing, { onChange: renderAll });
    }
    const { wrap, addBtn, readForm } = buildPickFormBase(matchup);
    addBtn.addEventListener("click", () => {
      addPrediction(matchup, readForm());
      renderAll();
    });
    return wrap;
  }

  // Fight-card row (one independent instance per expanded bout, matchup
  // fixed at mount time, no module-global involved). Re-checks for an
  // existing pending pick every time this is called -- including on a
  // fresh page load, not just right after submitting in the same session --
  // so a prediction made last week still shows as "Your pick: ..." instead
  // of a blank form the next time this row is expanded. opts.onChange lets
  // the caller (ui.js) refresh the row's own always-visible pick summary
  // line and toggle-button label after a pick is added or removed here.
  function buildCardPickSection(matchupObj, opts) {
    const existing = findPendingPredictionByFighters(matchupObj.result.nameA, matchupObj.result.nameB);
    if (existing) {
      return buildLockedPickView(existing, {
        onChange: () => {
          if (opts && opts.rootEl) mountCardPick(opts.rootEl, matchupObj, opts);
          renderAll(); // refreshes the sidebar teaser's pending count elsewhere on this same page, if mounted
          if (opts && opts.onChange) opts.onChange();
        },
      });
    }
    const { wrap, addBtn, readForm } = buildPickFormBase(matchupObj);
    addBtn.addEventListener("click", () => {
      addPrediction(matchupObj, readForm());
      if (opts && opts.rootEl) mountCardPick(opts.rootEl, matchupObj, opts);
      renderAll();
      if (opts && opts.onChange) opts.onChange();
    });
    return wrap;
  }

  function pickSummary(p) {
    let s = p.picked_winner;
    if (p.picked_method) {
      s += ` by ${METHOD_NAMES[p.picked_method]}`;
      if (p.picked_round) s += `, Round ${p.picked_round}`;
    }
    return s;
  }

  // Home page's Predict section -- just the log-a-pick form, nothing else,
  // so a fresh matchup result always has somewhere to log a pick against.
  function renderAdd() {
    if (!addRoot) return;
    addRoot.innerHTML = "";
    addRoot.appendChild(el("div", "section-header", '<h2 class="section-title display">My Predictions</h2>'));
    addRoot.appendChild(renderAddForm());
  }

  // Home page sidebar only now -- the standalone predictions.html page
  // (pending list, settle/delete, full report, CSV export/import) was
  // removed as redundant once Last Week's Results started showing the
  // model's own accuracy (see accuracyGroupHtml in results_render.js).
  // Individual picks still live on their fight-card row (mountCardPick,
  // "Remove pick") and still auto-settle against real results, so this
  // teaser is just a running scoreboard, not the only way to see a pick.
  function renderHistoryTeaser() {
    const rep = computeReport();
    const pendingCount = preds.filter((p) => p.status === "pending").length;
    const box = el("div");
    box.appendChild(el("div", "lr-header", '<h2 class="lr-title display">My Predictions</h2>'));
    if (preds.length === 0) {
      box.appendChild(el("div", "pt-empty-hint", "Call a matchup and log your own pick to start building a track record."));
    } else {
      const summary = el("div", "mp-teaser-summary mono");
      summary.innerHTML = rep.n
        ? `${pendingCount} pending &middot; ${pct(rep.winnerAcc)} winner accuracy (${rep.n} settled)`
        : `${pendingCount} pending &middot; no settled predictions yet`;
      box.appendChild(summary);
    }
    return box;
  }

  function renderHistory() {
    if (!historyRoot) return;
    historyRoot.innerHTML = "";
    historyRoot.appendChild(renderHistoryTeaser());
  }

  function renderAll() {
    renderAdd();
    renderHistory();
  }

  // Standalone (not an inline method) so buildCardPickSection can call it
  // recursively -- re-mounting the same rootEl in place is how a "Remove
  // pick" or a fresh submit swaps between the locked view and the form
  // without needing the caller to re-render the whole fight card.
  function mountCardPick(rootEl, matchupObj, opts) {
    if (!rootEl) return;
    load();
    rootEl.innerHTML = "";
    rootEl.appendChild(buildCardPickSection(matchupObj, { ...(opts || {}), rootEl }));
  }

  window.MyPredictions = {
    mountAdd(rootId) {
      addRoot = document.getElementById(rootId);
      load();
      renderAll();
    },
    mountHistory(rootId, opts) {
      historyRoot = document.getElementById(rootId);
      historyOpts = opts || {};
      load();
      renderAll();
    },
    setMatchup(scheduledRounds, result) {
      matchup = { scheduledRounds, result };
      renderAll();
    },
    mountCardPick,
    // Read-only lookup for ui.js's always-visible "Your pick: ..." line on
    // each fight-card row -- reloads from storage every call so it reflects
    // whatever's actually saved, not a stale in-memory snapshot. Pending
    // only (see findPendingPredictionByFighters) so an old settled pick from
    // a past meeting between the same two fighters doesn't wrongly show up
    // under a future rematch.
    getPickSummaryFor(nameA, nameB) {
      load();
      const p = findPendingPredictionByFighters(nameA, nameB);
      return p ? pickSummary(p) : null;
    },
    autoSettleFromResults,
    importCsvText(text, mode = "merge") {
      const rows = parseCsv(text);
      if (mode === "replace") {
        preds = rows;
      } else {
        const byId = new Map(preds.map((p) => [String(p.pred_id), p]));
        rows.forEach((r) => byId.set(String(r.pred_id), r));
        preds = Array.from(byId.values());
      }
      save();
      return rows.length;
    },
  };
})();
