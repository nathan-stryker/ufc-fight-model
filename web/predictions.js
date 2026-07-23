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
  function csvEscape(v) {
    const s = v === null || v === undefined ? "" : String(v);
    if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  }
  function toCsv(rows) {
    const lines = [FIELDS.join(",")];
    rows.forEach((r) => lines.push(FIELDS.map((f) => csvEscape(r[f])).join(",")));
    return lines.join("\r\n");
  }
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

  function addPrediction(form) {
    const r = matchup.result;
    const mv = modelVerdict(r);
    const pickedWinnerName = form.side === "a" ? r.nameA : r.nameB;
    const pred = {
      pred_id: nextId(),
      logged_at: new Date().toISOString(),
      event: form.event, fighter_a: r.nameA, fighter_b: r.nameB,
      scheduled_rounds: matchup.scheduledRounds,
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
    const agreedWithModel = settled.filter((p) => p.picked_winner === p.model_winner).length;
    return {
      n,
      winnerAcc: n ? winnerHits / n : null,
      methodAcc: methodCalled.length ? methodHits / methodCalled.length : null,
      methodN: methodCalled.length,
      roundAcc: roundCalled.length ? roundHits / roundCalled.length : null,
      roundN: roundCalled.length,
      agreedWithModelRate: n ? agreedWithModel / n : null,
    };
  }

  // ---------------------------------------------------------------------------
  let root = null;

  function el(tag, className, html) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function renderAddForm() {
    const wrap = el("div", "pt-add");
    if (!matchup) {
      wrap.appendChild(el("div", "pt-empty-hint", "Call a matchup above to log your own prediction on it."));
      return wrap;
    }
    const r = matchup.result;
    wrap.appendChild(el("div", "pt-matchup-label mono", `Predicting: ${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}`));

    const winnerRow = el("div", "pt-row", `<label>Winner</label>
      <select id="mp-side">
        <option value="a">${escapeHtml(r.nameA)}</option>
        <option value="b">${escapeHtml(r.nameB)}</option>
      </select>`);
    wrap.appendChild(winnerRow);

    const methodRow = el("div", "pt-row", `<label>Method</label>
      <select id="mp-method">
        <option value="">No pick (winner only)</option>
        <option value="dec">Decision</option>
        <option value="ko">KO/TKO</option>
        <option value="sub">Submission</option>
      </select>`);
    wrap.appendChild(methodRow);

    const roundOptions = Array.from({ length: matchup.scheduledRounds }, (_, i) => i + 1)
      .map((n) => `<option value="${n}">Round ${n}</option>`).join("");
    const roundRow = el("div", "pt-row", `<label>Round</label>
      <select id="mp-round">
        <option value="">No pick (any round)</option>
        ${roundOptions}
      </select>`);
    roundRow.hidden = true;
    wrap.appendChild(roundRow);

    wrap.appendChild(el("div", "pt-row", `<label>Event</label><input type="text" id="mp-event" placeholder="e.g. UFC 300" value="${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}">`));
    wrap.appendChild(el("div", "pt-row", `<label>Note</label><input type="text" id="mp-note" placeholder="optional -- why you think that"></div>`));

    const addBtn = el("button", "predict-btn pt-add-btn", "Log My Prediction");
    addBtn.type = "button";
    wrap.appendChild(addBtn);

    const methodSel = methodRow.querySelector("#mp-method");
    methodSel.addEventListener("change", () => {
      roundRow.hidden = methodSel.value === "" || methodSel.value === "dec";
    });

    addBtn.addEventListener("click", () => {
      addPrediction({
        side: wrap.querySelector("#mp-side").value,
        method: methodSel.value,
        round: roundRow.hidden ? "" : wrap.querySelector("#mp-round").value,
        event: wrap.querySelector("#mp-event").value.trim(),
        note: wrap.querySelector("#mp-note").value.trim(),
      });
      render();
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

  function modelSummary(p) {
    let s = `${p.model_winner} by ${METHOD_NAMES[p.model_method]}`;
    if (p.model_method !== "dec" && p.model_round) s += `, Round ${p.model_round}`;
    return s;
  }

  function renderPending() {
    const pending = preds.filter((p) => p.status === "pending");
    const box = el("div", "pt-log");
    box.appendChild(el("div", "tape-title", "<span>Pending predictions</span>"));
    if (pending.length === 0) {
      box.appendChild(el("div", "pt-empty-hint", "No pending predictions logged yet."));
      return box;
    }
    const table = el("div", "pt-table");
    pending.forEach((p) => {
      const row = el("div", "pt-table-row");
      row.innerHTML = `
        <div class="pt-cell pt-cell-main">
          <div class="pt-selection">${escapeHtml(pickSummary(p))}</div>
          <div class="pt-sub mono">${escapeHtml(p.event)} &middot; model said ${escapeHtml(modelSummary(p))}</div>
        </div>
        <div class="pt-cell pt-actions-cell"></div>`;
      const actions = row.querySelector(".pt-actions-cell");

      const settleBtn = el("button", "clear-btn pt-settle-btn", "Enter Result");
      settleBtn.type = "button";
      const form = el("div", "pt-row");
      form.hidden = true;
      form.innerHTML = `
        <select class="mp-actual-side"><option value="${escapeHtml(p.fighter_a)}">${escapeHtml(p.fighter_a)}</option><option value="${escapeHtml(p.fighter_b)}">${escapeHtml(p.fighter_b)}</option></select>
        <select class="mp-actual-method"><option value="dec">Decision</option><option value="ko">KO/TKO</option><option value="sub">Submission</option></select>
        <select class="mp-actual-round">${Array.from({ length: p.scheduled_rounds }, (_, i) => i + 1).map((n) => `<option value="${n}">Round ${n}</option>`).join("")}</select>
        <button class="clear-btn mp-save-btn" type="button">Save</button>`;
      const methodSel = form.querySelector(".mp-actual-method");
      const roundSel = form.querySelector(".mp-actual-round");
      methodSel.addEventListener("change", () => { roundSel.style.display = methodSel.value === "dec" ? "none" : ""; });

      settleBtn.addEventListener("click", () => { form.hidden = !form.hidden; });
      form.querySelector(".mp-save-btn").addEventListener("click", () => {
        settlePrediction(p.pred_id, {
          winner: form.querySelector(".mp-actual-side").value,
          method: methodSel.value,
          round: roundSel.value,
        });
        render();
      });

      const del = el("button", "clear-btn pt-delete-btn", "&times;");
      del.type = "button";
      del.title = "Remove";
      del.addEventListener("click", () => { deletePrediction(p.pred_id); render(); });

      actions.appendChild(settleBtn);
      actions.appendChild(del);
      table.appendChild(row);
      table.appendChild(form);
    });
    box.appendChild(table);
    return box;
  }

  function renderReport() {
    const rep = computeReport();
    const box = el("div", "pt-report");
    box.appendChild(el("div", "tape-title", "<span>Your track record</span>"));
    if (rep.n === 0) {
      box.appendChild(el("div", "pt-empty-hint", "No settled predictions yet -- results show up here once fights happen and you enter what actually happened."));
      return box;
    }
    const summary = el("div", "pt-summary mono");
    summary.innerHTML = `
      n=${rep.n} settled &middot; winner accuracy ${pct(rep.winnerAcc)}<br>
      method accuracy ${pct(rep.methodAcc)} (${rep.methodN} called)<br>
      round accuracy ${pct(rep.roundAcc)} (${rep.roundN} called)<br>
      picked the same WINNER as the model ${pct(rep.agreedWithModelRate)} of the time
      (this compares winner only, not method/round -- see each row's "model said" note for the full comparison)`;
    box.appendChild(summary);
    if (rep.n < 20) {
      box.appendChild(el("div", "pt-note", "Fewer than 20 settled predictions -- treat this as noise for now."));
    }
    return box;
  }

  function renderActions() {
    const box = el("div", "pt-actions-row");
    const exportBtn = el("button", "clear-btn", "Download backup (CSV)");
    exportBtn.type = "button";
    exportBtn.addEventListener("click", async () => {
      const csv = toCsv(preds);
      if (window.claude && window.claude.downloads) {
        try {
          await window.claude.downloads.save({ filename: "my_predictions.csv", data: csv });
          return;
        } catch (e) { /* fall through to manual download */ }
      }
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "my_predictions.csv";
      a.click();
      URL.revokeObjectURL(url);
    });

    const importBtn = el("button", "clear-btn", "Restore from file");
    importBtn.type = "button";
    const fileInput = el("input");
    fileInput.type = "file"; fileInput.accept = ".csv"; fileInput.hidden = true;
    importBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      const file = fileInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const count = window.MyPredictions.importCsvText(reader.result, "merge");
        render();
        alert(`Restored ${count} prediction(s) from ${file.name}.`);
      };
      reader.readAsText(file);
    });

    box.appendChild(exportBtn);
    box.appendChild(importBtn);
    box.appendChild(fileInput);
    if (!storageOk) {
      box.appendChild(el("div", "pt-note", "Browser storage isn't available here, so nothing auto-saves between visits -- use the backup/restore buttons every session."));
    }
    return box;
  }

  function render() {
    if (!root) return;
    root.innerHTML = "";
    root.appendChild(el("div", "tape-title", "<span>My Predictions</span>"));
    root.appendChild(el("p", "tracker-note", "Not betting-affiliated -- just log what YOU think will happen (winner, method, round) and see your own track record build up over time, including how often you agree with the model."));
    root.appendChild(renderAddForm());
    root.appendChild(renderPending());
    root.appendChild(renderReport());
    root.appendChild(renderActions());
  }

  window.MyPredictions = {
    mount(rootId) {
      root = document.getElementById(rootId);
      load();
      render();
    },
    setMatchup(scheduledRounds, result) {
      matchup = { scheduledRounds, result };
      render();
    },
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
