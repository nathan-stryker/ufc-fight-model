// Client-side paper-trade log for prop bets (method of victory, round totals) --
// no historical odds dataset exists for these markets (see README), so this
// logs predictions against real sportsbook odds as they appear on upcoming
// cards, for backtesting once enough real bets have settled. Mirrors
// src/backtest/{odds_utils,log_bet,settle_bet,paper_trade_report}.py exactly,
// including the CSV schema, so a downloaded log stays compatible with those
// Python tools in either direction.
//
// Persistence: auto-saves to localStorage (best-effort -- some sandboxes
// disable storage, so every access is wrapped and falls back to in-memory
// only) plus an explicit download/restore-from-file pair as a robust backup
// that doesn't depend on browser storage surviving.
(function () {
  const STORAGE_KEY = "ufc_paper_trades_v1";
  const KELLY_FRACTION = 0.25;
  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };

  const FIELDS = [
    "bet_id", "logged_at", "event", "fighter_a", "fighter_b", "scheduled_rounds",
    "market", "selection", "sportsbook", "odds_american", "other_side_odds_american",
    "model_prob", "implied_prob", "vig_free", "edge", "kelly_fraction", "suggested_stake_units",
    "status", "settled_at", "profit_units_flat", "profit_units_kelly", "notes",
  ];

  // --- odds math (mirrors src/backtest/odds_utils.py) ---
  function americanToDecimal(a) {
    return a > 0 ? 1 + a / 100 : 1 - 100 / a;
  }
  function americanToProb(a) {
    return 1 / americanToDecimal(a);
  }
  function devigTwoWay(pA, pB) {
    const over = pA + pB;
    return [pA / over, pB / over];
  }
  function kellyStake(modelProb, american, fraction = KELLY_FRACTION) {
    const dec = americanToDecimal(american);
    const b = dec - 1;
    const full = (modelProb * (b + 1) - 1) / b;
    return Math.max(0, fraction * full);
  }
  function profitUnits(won, american, stake) {
    return won ? stake * (americanToDecimal(american) - 1) : -stake;
  }

  // --- CSV (RFC4180-ish quoting, matches what Python's csv module writes/reads) ---
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
    return (Number(x) * 100).toFixed(1) + "%";
  }
  function fmtOdds(x) {
    const n = Number(x);
    return n > 0 ? `+${n}` : `${n}`;
  }

  // --- state ---
  let bets = [];
  let matchup = null; // { scheduledRounds, result }
  let storageOk = true;

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      bets = raw ? JSON.parse(raw) : [];
    } catch (e) {
      storageOk = false;
      bets = [];
    }
  }
  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(bets));
    } catch (e) {
      storageOk = false;
    }
  }
  function nextBetId() {
    return `pt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  }

  // --- market pricing (mirrors src/backtest/log_bet.py) ---
  function roundTotalProb(result, overLine) {
    const n = Math.floor(overLine);
    let pByN = 0;
    Object.entries(result.roundGivenFinish).forEach(([r, p]) => {
      if (parseInt(r, 10) <= n) pByN += p;
    });
    pByN *= result.pFinish;
    return 1 - pByN;
  }

  function priceSelection(market, params) {
    const r = matchup.result;
    if (market === "winner") {
      const modelProb = params.side === "a" ? r.probAWins : r.probBWins;
      const name = params.side === "a" ? r.nameA : r.nameB;
      return { modelProb, selection: name };
    }
    if (market === "method") {
      const dist = params.side === "a" ? r.methodGivenA : r.methodGivenB;
      const name = params.side === "a" ? r.nameA : r.nameB;
      let modelProb = dist[params.method];
      let selection = `${name} by ${METHOD_NAMES[params.method]}`;
      // Optional exact-round pin (only meaningful for a finish -- a decision
      // goes the full scheduled distance, no single round applies). Multiplies
      // in P(round=r | this fighter wins by this method) to get the true joint
      // probability, not just the method-only marginal.
      if (params.method !== "dec" && params.round) {
        const condArr = r.condRoundByWinMethod[params.side][params.method];
        const idx = Math.round(params.round) - 1;
        const roundProb = condArr && idx >= 0 && idx < condArr.length ? condArr[idx] : 0;
        modelProb *= roundProb;
        selection += `, Round ${params.round}`;
      }
      return { modelProb, selection };
    }
    if (market === "round_total") {
      const pOver = roundTotalProb(r, params.line);
      const modelProb = params.direction === "over" ? pOver : 1 - pOver;
      return { modelProb, selection: `${params.direction} ${params.line}` };
    }
    throw new Error("unknown market");
  }

  function addBet(form) {
    const { modelProb, selection } = priceSelection(form.market, form);
    const impliedProb = americanToProb(form.oddsAmerican);
    let vigFreeProb = impliedProb, vigFree = false;
    if (form.otherSideOdds != null && !Number.isNaN(form.otherSideOdds)) {
      const otherImplied = americanToProb(form.otherSideOdds);
      [vigFreeProb] = devigTwoWay(impliedProb, otherImplied);
      vigFree = true;
    }
    const edge = modelProb - vigFreeProb;
    const stake = kellyStake(modelProb, form.oddsAmerican);

    const bet = {
      bet_id: nextBetId(),
      logged_at: new Date().toISOString(),
      event: form.event, fighter_a: matchup.result.nameA, fighter_b: matchup.result.nameB,
      scheduled_rounds: matchup.scheduledRounds, market: form.market, selection,
      sportsbook: form.sportsbook, odds_american: form.oddsAmerican,
      other_side_odds_american: form.otherSideOdds != null ? form.otherSideOdds : "",
      model_prob: modelProb, implied_prob: impliedProb, vig_free: vigFree, edge,
      kelly_fraction: KELLY_FRACTION, suggested_stake_units: stake,
      status: "pending", settled_at: "", profit_units_flat: "", profit_units_kelly: "", notes: "",
    };
    bets.push(bet);
    save();
    return bet;
  }

  function settleBet(betId, outcome) {
    const bet = bets.find((b) => String(b.bet_id) === String(betId));
    if (!bet) return;
    const odds = Number(bet.odds_american);
    const stake = Number(bet.suggested_stake_units) || 0;
    if (outcome === "push") {
      bet.profit_units_flat = 0; bet.profit_units_kelly = 0;
    } else {
      const won = outcome === "won";
      bet.profit_units_flat = profitUnits(won, odds, 1.0);
      bet.profit_units_kelly = profitUnits(won, odds, stake);
    }
    bet.status = outcome;
    bet.settled_at = new Date().toISOString();
    save();
  }

  function deleteBet(betId) {
    bets = bets.filter((b) => String(b.bet_id) !== String(betId));
    save();
  }

  function computeReport() {
    const settled = bets.filter((b) => b.status !== "pending");
    const decided = settled.filter((b) => b.status !== "push");
    const n = decided.length;
    const wins = decided.filter((b) => b.status === "won").length;
    const flatTotal = decided.reduce((s, b) => s + Number(b.profit_units_flat || 0), 0);
    const kellyStaked = decided.reduce((s, b) => s + Number(b.suggested_stake_units || 0), 0);
    const kellyTotal = decided.reduce((s, b) => s + Number(b.profit_units_kelly || 0), 0);

    const byMarket = {};
    decided.forEach((b) => {
      byMarket[b.market] = byMarket[b.market] || { n: 0, wins: 0, flat: 0, kelly: 0 };
      byMarket[b.market].n += 1;
      if (b.status === "won") byMarket[b.market].wins += 1;
      byMarket[b.market].flat += Number(b.profit_units_flat || 0);
      byMarket[b.market].kelly += Number(b.profit_units_kelly || 0);
    });

    return {
      n, winRate: n ? wins / n : null,
      flatTotal, flatRoi: n ? flatTotal / n : null,
      kellyStaked, kellyTotal, kellyRoi: kellyStaked ? kellyTotal / kellyStaked : null,
      byMarket,
      meanModelProb: n ? decided.reduce((s, b) => s + Number(b.model_prob), 0) / n : null,
    };
  }

  // ---------------------------------------------------------------------------
  // Rendering (all DOM ownership lives here -- the template only provides a
  // single mount point, #prop-tracker)
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
      wrap.appendChild(el("div", "pt-empty-hint", "Call a matchup above to log a prop bet on it."));
      return wrap;
    }
    const r = matchup.result;
    wrap.appendChild(el("div", "pt-matchup-label mono", `Logging for: ${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}`));

    const marketRow = el("div", "pt-row");
    marketRow.innerHTML = `<label>Market</label>
      <select id="pt-market">
        <option value="winner">Winner</option>
        <option value="method">Method of victory</option>
        <option value="round_total">Round total (over/under)</option>
      </select>`;
    wrap.appendChild(marketRow);

    const sideRow = el("div", "pt-row", `<label>Fighter</label>
      <select id="pt-side">
        <option value="a">${escapeHtml(r.nameA)}</option>
        <option value="b">${escapeHtml(r.nameB)}</option>
      </select>`);
    wrap.appendChild(sideRow);

    const methodRow = el("div", "pt-row", `<label>Method</label>
      <select id="pt-method">
        <option value="dec">Decision</option>
        <option value="ko">KO/TKO</option>
        <option value="sub">Submission</option>
      </select>`);
    methodRow.hidden = true;
    wrap.appendChild(methodRow);

    const roundOptions = Array.from({ length: matchup.scheduledRounds }, (_, i) => i + 1)
      .map((n) => `<option value="${n}">Round ${n}</option>`).join("");
    const methodRoundRow = el("div", "pt-row", `<label>Exact round</label>
      <select id="pt-method-round">
        <option value="">Any round</option>
        ${roundOptions}
      </select>`);
    methodRoundRow.hidden = true;
    wrap.appendChild(methodRoundRow);

    const lineRow = el("div", "pt-row", `<label>Line</label>
      <input type="number" id="pt-line" step="0.5" placeholder="e.g. 2.5" style="width:5rem">
      <select id="pt-direction"><option value="over">Over</option><option value="under">Under</option></select>`);
    lineRow.hidden = true;
    wrap.appendChild(lineRow);

    wrap.appendChild(el("div", "pt-row", `<label>Event</label><input type="text" id="pt-event" placeholder="e.g. UFC 300" value="${escapeHtml(r.nameA)} vs ${escapeHtml(r.nameB)}">`));
    wrap.appendChild(el("div", "pt-row", `<label>Sportsbook</label><input type="text" id="pt-book" placeholder="e.g. DraftKings">`));
    wrap.appendChild(el("div", "pt-row", `<label>Odds</label><input type="number" id="pt-odds" placeholder="-150 or +130" style="width:6rem">`));
    wrap.appendChild(el("div", "pt-row", `<label>Other side odds</label><input type="number" id="pt-odds-other" placeholder="optional, for de-vig" style="width:8rem">`));

    const addBtn = el("button", "predict-btn pt-add-btn", "Add to Log");
    addBtn.type = "button";
    wrap.appendChild(addBtn);
    const err = el("div", "pt-error");
    wrap.appendChild(err);

    const marketSel = marketRow.querySelector("#pt-market");
    const methodSel = methodRow.querySelector("#pt-method");
    function syncVisibility() {
      const isMethod = marketSel.value === "method";
      methodRow.hidden = !isMethod;
      lineRow.hidden = marketSel.value !== "round_total";
      sideRow.hidden = marketSel.value === "round_total";
      methodRoundRow.hidden = !(isMethod && methodSel.value !== "dec");
    }
    marketSel.addEventListener("change", syncVisibility);
    methodSel.addEventListener("change", syncVisibility);

    addBtn.addEventListener("click", () => {
      err.textContent = "";
      const market = marketSel.value;
      const roundRaw = wrap.querySelector("#pt-method-round").value;
      const form = {
        market,
        side: wrap.querySelector("#pt-side").value,
        method: methodSel.value,
        round: roundRaw === "" ? null : parseInt(roundRaw, 10),
        line: parseFloat(wrap.querySelector("#pt-line").value),
        direction: wrap.querySelector("#pt-direction").value,
        event: wrap.querySelector("#pt-event").value.trim(),
        sportsbook: wrap.querySelector("#pt-book").value.trim(),
        oddsAmerican: parseFloat(wrap.querySelector("#pt-odds").value),
        otherSideOdds: wrap.querySelector("#pt-odds-other").value.trim() === "" ? null : parseFloat(wrap.querySelector("#pt-odds-other").value),
      };
      if (market === "round_total" && Number.isNaN(form.line)) { err.textContent = "Enter a line, e.g. 2.5"; return; }
      if (Number.isNaN(form.oddsAmerican) || Math.abs(form.oddsAmerican) < 100) { err.textContent = "Enter valid American odds (e.g. -150 or +130)"; return; }
      addBet(form);
      render();
    });

    return wrap;
  }

  function renderPending() {
    const pending = bets.filter((b) => b.status === "pending");
    const box = el("div", "pt-log");
    box.appendChild(el("div", "tape-title", "<span>Pending bets</span>"));
    if (pending.length === 0) {
      box.appendChild(el("div", "pt-empty-hint", "No pending bets logged yet."));
      return box;
    }
    const table = el("div", "pt-table");
    pending.forEach((b) => {
      const row = el("div", "pt-table-row");
      row.innerHTML = `
        <div class="pt-cell pt-cell-main">
          <div class="pt-selection">${escapeHtml(b.selection)}</div>
          <div class="pt-sub mono">${escapeHtml(b.event)} &middot; ${escapeHtml(b.sportsbook)} &middot; ${fmtOdds(b.odds_american)}</div>
        </div>
        <div class="pt-cell mono">model ${pct(b.model_prob)}</div>
        <div class="pt-cell mono">edge ${b.edge >= 0 ? "+" : ""}${pct(b.edge)}</div>
        <div class="pt-cell mono">${Number(b.suggested_stake_units).toFixed(2)}u</div>
        <div class="pt-cell pt-actions-cell"></div>`;
      const actions = row.querySelector(".pt-actions-cell");
      ["won", "lost", "push"].forEach((outcome) => {
        const btn = el("button", "clear-btn pt-settle-btn", outcome[0].toUpperCase() + outcome.slice(1));
        btn.type = "button";
        btn.addEventListener("click", () => { settleBet(b.bet_id, outcome); render(); });
        actions.appendChild(btn);
      });
      const del = el("button", "clear-btn pt-delete-btn", "&times;");
      del.type = "button";
      del.title = "Remove";
      del.addEventListener("click", () => { deleteBet(b.bet_id); render(); });
      actions.appendChild(del);
      table.appendChild(row);
    });
    box.appendChild(table);
    return box;
  }

  function renderReport() {
    const rep = computeReport();
    const box = el("div", "pt-report");
    box.appendChild(el("div", "tape-title", "<span>Settled results</span>"));
    if (rep.n === 0) {
      box.appendChild(el("div", "pt-empty-hint", "No settled bets yet -- results show up here once fights happen and you settle them."));
      return box;
    }
    const summary = el("div", "pt-summary mono");
    summary.innerHTML = `
      n=${rep.n} &middot; win rate ${pct(rep.winRate)}<br>
      flat: ${rep.flatTotal >= 0 ? "+" : ""}${rep.flatTotal.toFixed(2)}u (${rep.flatRoi >= 0 ? "+" : ""}${pct(rep.flatRoi)} ROI)<br>
      kelly: ${rep.kellyTotal >= 0 ? "+" : ""}${rep.kellyTotal.toFixed(2)}u on ${rep.kellyStaked.toFixed(2)}u staked (${rep.kellyRoi != null ? (rep.kellyRoi >= 0 ? "+" : "") + pct(rep.kellyRoi) : "n/a"} ROI)`;
    box.appendChild(summary);

    const marketRows = Object.entries(rep.byMarket).map(([m, s]) =>
      `<div class="pt-market-row mono">${escapeHtml(m)}: n=${s.n} win=${(s.wins / s.n * 100).toFixed(0)}% flat=${s.flat >= 0 ? "+" : ""}${s.flat.toFixed(2)}u</div>`
    ).join("");
    if (marketRows) box.appendChild(el("div", "pt-by-market", marketRows));

    if (rep.n < 30) {
      box.appendChild(el("div", "pt-note", "Fewer than 30 settled bets -- treat all of this as noise for now, same as any small backtest sample."));
    }
    return box;
  }

  function renderActions() {
    const box = el("div", "pt-actions-row");
    const exportBtn = el("button", "clear-btn", "Download backup (CSV)");
    exportBtn.type = "button";
    exportBtn.addEventListener("click", async () => {
      const csv = toCsv(bets);
      if (window.claude && window.claude.downloads) {
        try {
          await window.claude.downloads.save({ filename: "paper_trades.csv", data: csv });
          return;
        } catch (e) { /* fall through to manual download */ }
      }
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "paper_trades.csv";
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
        const count = window.PaperTrade.importCsvText(reader.result, "merge");
        render();
        alert(`Restored ${count} bet(s) from ${file.name}.`);
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
    root.appendChild(el("div", "tape-title", "<span>Prop Bet Tracker</span>"));
    root.appendChild(el("p", "tracker-note", "No historical odds dataset exists for method-of-victory or round-total props, so this logs your real bets against the model's own probability as cards happen, to see the results build up over time."));
    root.appendChild(renderAddForm());
    root.appendChild(renderPending());
    root.appendChild(renderReport());
    root.appendChild(renderActions());
  }

  window.PaperTrade = {
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
        bets = rows;
      } else {
        const byId = new Map(bets.map((b) => [String(b.bet_id), b]));
        rows.forEach((r) => byId.set(String(r.bet_id), r));
        bets = Array.from(byId.values());
      }
      save();
      return rows.length;
    },
  };
})();
