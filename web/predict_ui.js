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
    if (f.style) metaParts.push(f.style);
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

  function renderResult(r, explanation) {
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

    renderBreakdown(explanation);
  }

  function formatMonthYear(isoDate) {
    if (!isoDate) return "";
    const d = new Date(isoDate + "T00:00:00");
    if (isNaN(d.getTime())) return isoDate;
    return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }

  // DOM-node version of ui.js's categorySectionHtml() -- same reasoning as
  // verdictText()/makeRow() above for why this is a separate implementation
  // rather than a shared one.
  function makeFactorRow(f, nameA, nameB) {
    const row = document.createElement("div");
    row.className = "factor-row";
    const towardA = f.favors === "a";
    row.innerHTML =
      `<div class="factor-label">${escapeHtml(f.label)}<span class="factor-value mono">${escapeHtml(f.valueText)}</span></div>` +
      `<div class="factor-bar-track"><div class="factor-bar factor-bar-a"></div><div class="factor-bar factor-bar-b"></div></div>` +
      `<div class="factor-favors mono">${escapeHtml(towardA ? nameA : nameB)}</div>`;
    requestAnimationFrame(() => {
      const pct = f.relativeMagnitude * 50;
      row.querySelector(towardA ? ".factor-bar-a" : ".factor-bar-b").style.width = pct + "%";
    });
    return row;
  }

  function makeCategorySection(title, factors, nameA, nameB) {
    if (!factors.length) return null;
    const section = document.createElement("div");
    section.className = "tape";
    section.innerHTML = `<div class="tape-title"><span>${escapeHtml(title)}</span></div>`;
    const wrap = document.createElement("div");
    wrap.className = "why-factors";
    factors.forEach((f) => wrap.appendChild(makeFactorRow(f, nameA, nameB)));
    section.appendChild(wrap);
    return section;
  }

  // One fight from engine.js's recordVsStyle() -- DOM-node equivalent of
  // ui.js's reuse of prefightRowHtml() (same .debut-fight-row classes for
  // visual consistency, this file just doesn't have that function since
  // it's not a fight-card page).
  function makeStyleFightRow(f) {
    const row = document.createElement("div");
    row.className = "debut-fight-row";
    const detailParts = [];
    if (f.method) detailParts.push(f.method);
    if (f.round) detailParts.push(`R${f.round}`);
    if (f.event) detailParts.push(f.event);
    if (f.eventDate) detailParts.push(formatMonthYear(f.eventDate));
    row.innerHTML =
      `<span class="debut-fight-result ${f.outcome === "W" ? "win" : "loss"}">${f.outcome}</span>` +
      `<span class="debut-fight-body">` +
      `<span class="debut-fight-opp">${f.outcome === "W" ? "def." : "lost to"} ${escapeHtml(f.opponentName)}</span>` +
      `<span class="debut-fight-detail mono">${escapeHtml(detailParts.join(" · "))}</span>` +
      `</span>`;
    return row;
  }

  function makeStyleRecordBlock(fighterName, opponentStyle, rec) {
    if (!rec) return null;
    const block = document.createElement("div");
    block.className = "style-record-block";
    const summary = document.createElement("div");
    summary.className = "style-record-summary";
    // No pluralization attempted ("vs Wrestlers"/"vs Sambo fighters") --
    // UFC.com's own style tags mix person-nouns and discipline names
    // inconsistently, so there's no single grammatically-safe rule.
    summary.innerHTML = `${escapeHtml(fighterName)}: ${rec.wins}-${rec.losses} vs ${escapeHtml(opponentStyle)} ` +
      `<span class="fc-style-record-note">(${rec.knownCount} of ${rec.totalFights} career fights)</span>`;
    block.appendChild(summary);
    rec.fights.forEach((f) => block.appendChild(makeStyleFightRow(f)));
    return block;
  }

  // "Breakdown" -- odds/method/round are already always shown above this
  // (this page has no per-bout toggle, unlike the fight card); this panel
  // is everything explain.js/recordVsStyle add on top: categorized
  // factors, both fighters' UFC.com style tags, and each fighter's record
  // vs. the OTHER's style with the actual fight(s) listed. Collapsed and
  // re-rendered on every new prediction (one fixed results panel, unlike
  // the fight card's N independent rows) so a stale explanation from the
  // previous matchup can never be left showing.
  function renderBreakdown(explanation) {
    const panel = document.getElementById("breakdown-panel");
    const btn = document.getElementById("breakdown-toggle");
    if (!panel || !btn) return;
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    panel.innerHTML = "";

    [["Striking", explanation.striking], ["Grappling", explanation.grappling], ["Intangibles", explanation.intangibles]]
      .forEach(([title, factors]) => {
        const section = makeCategorySection(title, factors, explanation.nameA, explanation.nameB);
        if (section) panel.appendChild(section);
      });

    if (explanation.styleA || explanation.styleB) {
      const stylesSection = document.createElement("div");
      stylesSection.className = "tape";
      stylesSection.innerHTML = `<div class="tape-title"><span>Fighting Styles</span></div>`;
      if (explanation.styleA) {
        const row = document.createElement("div");
        row.className = "style-tag-row";
        row.innerHTML = `<div class="factor-label">${escapeHtml(explanation.nameA)}</div><div class="fc-style mono">${escapeHtml(explanation.styleA)}</div>`;
        stylesSection.appendChild(row);
      }
      if (explanation.styleB) {
        const row = document.createElement("div");
        row.className = "style-tag-row";
        row.innerHTML = `<div class="factor-label">${escapeHtml(explanation.nameB)}</div><div class="fc-style mono">${escapeHtml(explanation.styleB)}</div>`;
        stylesSection.appendChild(row);
      }
      panel.appendChild(stylesSection);
    }

    const recA = recordVsStyle(selected.a.fighter_id, selected.b.style, byId, MODEL_DATA.fighter_history);
    const recB = recordVsStyle(selected.b.fighter_id, selected.a.style, byId, MODEL_DATA.fighter_history);
    if (recA || recB) {
      const recordSection = document.createElement("div");
      recordSection.className = "tape";
      recordSection.innerHTML = `<div class="tape-title"><span>Record vs. Opponent's Style</span></div>`;
      const blockA = makeStyleRecordBlock(explanation.nameA, selected.b.style, recA);
      const blockB = makeStyleRecordBlock(explanation.nameB, selected.a.style, recB);
      if (blockA) recordSection.appendChild(blockA);
      if (blockB) recordSection.appendChild(blockB);
      panel.appendChild(recordSection);
    }

    const caption = document.createElement("div");
    caption.className = "why-caption";
    caption.textContent = "Based on the model's core prediction (Elo, physical attributes, UFC record, and striking/grappling rates); a small blend toward historical Elo trends can shift the win% shown above by a couple points without changing which factors drove it.";
    panel.appendChild(caption);
  }

  // Shared by the "Call It" button click AND the auto-run path below (a
  // shared/bookmarked ?a=&b=&rounds= link landing here) -- one place
  // computing a prediction and fanning it out to the results panel, so the
  // two entry points can never drift into showing different things for the
  // same matchup. No MyPredictions/PaperTrade handoff involved at all --
  // this page is just for fun, not meant to build a track record.
  function runPrediction() {
    if (!selected.a || !selected.b) return;
    const result = predictFull(selected.a, selected.b, scheduledRounds, MODEL_DATA);
    const explanation = explainWin(selected.a, selected.b, MODEL_DATA);
    renderResult(result, explanation);
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

  // Icon-only button (see its markup in predict_template.html) -- no
  // text-swap on toggle, unlike the old "Breakdown"/"Hide" version:
  // aria-expanded alone drives both the accessible state and the CSS
  // hover/expanded look, matching ui.js's corner-icon treatment on This
  // Week's Card.
  const breakdownToggleBtn = document.getElementById("breakdown-toggle");
  if (breakdownToggleBtn) {
    breakdownToggleBtn.addEventListener("click", () => {
      const panel = document.getElementById("breakdown-panel");
      const expanded = breakdownToggleBtn.getAttribute("aria-expanded") === "true";
      breakdownToggleBtn.setAttribute("aria-expanded", String(!expanded));
      panel.hidden = expanded;
    });
  }

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
