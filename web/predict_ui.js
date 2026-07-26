(function () {
  const { byId, searchList } = buildFighterIndex(MODEL_DATA.fighters);
  const selected = { a: null, b: null };
  let scheduledRounds = 3;
  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };

  // Same derivation as ui.js's verdictText() (the home page's card-preview
  // line) -- duplicated, not shared, since these are two independent page
  // bundles, same pattern as news_render.js/results_render.js.
  function verdictText(r) {
    const aWinner = r.probAWins >= 0.5;
    const winnerName = aWinner ? r.nameA : r.nameB;
    const methodRanked = Object.entries(r.method).sort((x, y) => y[1] - x[1]);
    const topMethod = methodRanked[0][0];
    let text = `${winnerName} by ${METHOD_NAMES[topMethod]}`;
    if (topMethod !== "dec") {
      const roundRanked = Object.entries(r.roundGivenFinish).sort((x, y) => y[1] - x[1]);
      if (roundRanked.length) text += `, Round ${roundRanked[0][0]}`;
    }
    return { aWinner, winnerName, methodRanked, topMethod, text };
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function flagBadgeHtml(isoCode) {
    const svg = isoCode && MODEL_DATA.flags ? MODEL_DATA.flags[isoCode] : null;
    return svg || `<div class="fighter-badge-empty"></div>`;
  }

  function hint(f) {
    if (f.nickname) return `"${f.nickname}"`;
    if (f.dob != null) return `b. ${new Date(f.dob * MS_PER_DAY).getUTCFullYear()}`;
    return "";
  }

  function setupCorner(corner) {
    const input = document.getElementById(`search-${corner}`);
    const suggBox = document.getElementById(`suggestions-${corner}`);
    const clearBtn = document.querySelector(`[data-clear="${corner}"]`);

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      suggBox.innerHTML = "";
      if (q.length < 2) return;
      const matches = searchList.filter((f) => f.name.toLowerCase().includes(q)).slice(0, 8);
      matches.forEach((m) => {
        const div = document.createElement("div");
        div.className = "suggestion";
        const h = hint(m);
        div.innerHTML = `<span>${escapeHtml(m.name)}</span>` + (h ? `<span class="nick">${escapeHtml(h)}</span>` : "");
        div.addEventListener("click", () => selectFighter(corner, m.id));
        suggBox.appendChild(div);
      });
    });

    input.addEventListener("blur", () => {
      setTimeout(() => { suggBox.innerHTML = ""; }, 150);
    });

    clearBtn.addEventListener("click", () => {
      selected[corner] = null;
      document.getElementById(`card-${corner}`).classList.remove("shown");
      input.value = "";
      input.style.display = "";
      input.focus();
      updatePredictBtn();
    });
  }

  function selectFighter(corner, id) {
    selected[corner] = byId.get(id);
    const f = selected[corner];
    if (!f) return;
    document.getElementById(`suggestions-${corner}`).innerHTML = "";
    document.getElementById(`search-${corner}`).style.display = "none";
    document.getElementById(`badge-${corner}`).innerHTML = flagBadgeHtml(f.iso_code);
    document.getElementById(`name-${corner}`).textContent = f.name;
    document.getElementById(`nick-${corner}`).textContent = f.nickname ? `"${f.nickname}"` : "";

    const todayDays = todayEpochDays();
    const metaParts = [];
    if (f.dob_epoch_days != null) metaParts.push(`${Math.floor((todayDays - f.dob_epoch_days) / 365.25)} yrs`);
    if (f.height_in != null) metaParts.push(`${Math.floor(f.height_in / 12)}'${Math.round(f.height_in % 12)}"`);
    if (f.reach_in != null) metaParts.push(`${f.reach_in}" reach`);
    if (f.stance) metaParts.push(f.stance);
    if (f.elo == null) metaParts.push("no UFC history yet");
    document.getElementById(`meta-${corner}`).textContent = metaParts.join(" - ");

    const divisionEl = document.getElementById(`division-${corner}`);
    if (f.weightclass != null && f.rank != null) {
      divisionEl.textContent = `${f.weightclass} -- #${Math.round(f.rank)} of ${Math.round(f.n_in_division)} all-time by division Elo`;
    } else {
      divisionEl.textContent = "";
    }

    document.getElementById(`card-${corner}`).classList.add("shown");
    updatePredictBtn();
  }

  function updatePredictBtn() {
    document.getElementById("predict-btn").disabled = !(selected.a && selected.b);
    document.getElementById("results").hidden = true;
  }

  function makeRow(label, pct, predicted) {
    const row = document.createElement("div");
    row.className = "tape-row" + (predicted ? " predicted" : "");
    row.innerHTML =
      `<div class="tape-row-label">${escapeHtml(label)}${predicted ? '<span class="predicted-chip">Predicted</span>' : ""}</div>` +
      `<div class="tape-row-track"><div class="tape-row-fill"></div></div>` +
      `<div class="tape-row-pct mono">${(pct * 100).toFixed(1)}%</div>`;
    requestAnimationFrame(() => {
      row.querySelector(".tape-row-fill").style.width = pct * 100 + "%";
    });
    return row;
  }

  function renderResult(r) {
    const results = document.getElementById("results");
    results.hidden = false;

    const v = verdictText(r);
    const aWinner = v.aWinner;
    const methodRanked = v.methodRanked;
    const topMethod = v.topMethod;
    document.getElementById("verdict-line").innerHTML =
      `<span class="${aWinner ? "winner" : ""}">${escapeHtml(r.nameA)}</span> vs ` +
      `<span class="${!aWinner ? "winner" : ""}">${escapeHtml(r.nameB)}</span>`;
    document.getElementById("verdict-detail").textContent = v.text;

    const fillA = document.getElementById("odds-fill-a");
    const fillB = document.getElementById("odds-fill-b");
    fillA.style.width = "50%";
    fillB.style.width = "50%";
    void fillA.offsetWidth;
    requestAnimationFrame(() => {
      fillA.style.width = r.probAWins * 100 + "%";
      fillB.style.width = r.probBWins * 100 + "%";
    });

    document.getElementById("odds-pct-a").textContent = (r.probAWins * 100).toFixed(1) + "%";
    document.getElementById("odds-pct-b").textContent = (r.probBWins * 100).toFixed(1) + "%";
    document.getElementById("odds-name-a").textContent = r.nameA;
    document.getElementById("odds-name-b").textContent = r.nameB;

    const methodRows = document.getElementById("method-rows");
    methodRows.innerHTML = "";
    methodRanked.forEach(([k, v], i) => methodRows.appendChild(makeRow(METHOD_NAMES[k], v, i === 0)));

    const roundRows = document.getElementById("round-rows");
    roundRows.innerHTML = "";
    document.getElementById("finish-chance").textContent = `${(r.pFinish * 100).toFixed(0)}% chance of a finish`;
    const entries = Object.entries(r.roundGivenFinish); // kept in chronological order -- round number is a real sequence
    const topRound = entries.length ? entries.slice().sort((x, y) => y[1] - x[1])[0][0] : null;
    const showRoundPredicted = topMethod !== "dec"; // a decision goes the distance -- no single round to call
    if (entries.length === 0) {
      const div = document.createElement("div");
      div.className = "tape-row-label";
      div.style.color = "var(--ink-dim)";
      div.textContent = "Finish probability too low to break down by round.";
      roundRows.appendChild(div);
    } else {
      entries.forEach(([rnd, p]) => roundRows.appendChild(makeRow(`Round ${rnd}`, p, showRoundPredicted && rnd === topRound)));
    }
  }

  // Shared by the "Call It" button click AND the auto-run path below (a
  // shared/bookmarked ?a=&b=&rounds= link landing here) -- one place
  // computing a prediction and fanning it out to the results panel plus
  // both add-a-pick forms, so the two entry points can never drift into
  // showing different things for the same matchup.
  function runPrediction() {
    if (!selected.a || !selected.b) return;
    const result = predictFull(selected.a, selected.b, scheduledRounds, MODEL_DATA);
    renderResult(result);
    if (window.PaperTrade) window.PaperTrade.setMatchup(scheduledRounds, result);
    if (window.MyPredictions) window.MyPredictions.setMatchup(scheduledRounds, result);
  }

  setupCorner("a");
  setupCorner("b");

  document.getElementById("rounds-toggle").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    scheduledRounds = parseInt(btn.dataset.rounds, 10);
    document.querySelectorAll("#rounds-toggle button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  document.getElementById("predict-btn").addEventListener("click", runPrediction);

  // Landed here from a shared/bookmarked link (?a=<idA>&b=<idB>&rounds=<N>)
  // -- pre-fill both corners and run the prediction immediately, no click
  // needed. The real fight card no longer generates these (it has its own
  // inline "Make Your Pick" panel per bout now), but a link like this still
  // works fine as a way to jump straight to a specific hypothetical
  // matchup. Silently does nothing if the ids don't resolve (stale link,
  // fighter fell out of the active roster, etc.) -- the page still works
  // fine as a blank manual picker in that case.
  function runFromQueryParams() {
    const params = new URLSearchParams(location.search);
    const idA = params.get("a");
    const idB = params.get("b");
    const roundsParam = parseInt(params.get("rounds"), 10);
    if (!idA || !idB || !byId.has(idA) || !byId.has(idB)) return;
    selectFighter("a", idA);
    selectFighter("b", idB);
    if (roundsParam === 3 || roundsParam === 5) {
      scheduledRounds = roundsParam;
      document.querySelectorAll("#rounds-toggle button").forEach((b) => {
        b.classList.toggle("active", parseInt(b.dataset.rounds, 10) === scheduledRounds);
      });
    }
    runPrediction();
  }
  runFromQueryParams();
})();
