(function () {
  const { byId, searchList } = buildFighterIndex(MODEL_DATA.fighters);
  const fightCountEl = document.getElementById("fight-count");
  if (fightCountEl) fightCountEl.textContent = MODEL_DATA.total_fights.toLocaleString();

  const selected = { a: null, b: null };
  let scheduledRounds = 3;
  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };

  // Single declarative "who/how/when" derivation, shared by the full results
  // panel (renderResult) and the home-page card list (renderUpcomingCard) --
  // both read the top-ranked entries of the SAME sorted distributions a
  // predictFull() result carries, so a headline can never disagree with the
  // detail bars it's summarizing, no matter which section is rendering it.
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

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // An earlier design here was a procedurally-generated fighter medallion
  // (first a bust silhouette, then a boxing glove) -- replaced with real
  // country flags per user request. The site's own fighter roster is
  // already active-UFC-only (see export_web_model.py), and nationality for
  // that roster was looked up from Sherdog.com (src/data/scrape_nationality.py)
  // since neither UFCStats nor our other data sources carry it. Flags
  // themselves are MIT-licensed SVGs from lipis/flag-icons, embedded in
  // MODEL_DATA.flags keyed by ISO code (only the codes the roster actually
  // needs, not the whole flag set) -- not every fighter matched a Sherdog
  // profile, so this degrades to an empty plate rather than guessing.
  function flagBadgeHtml(isoCode) {
    const svg = isoCode && MODEL_DATA.flags ? MODEL_DATA.flags[isoCode] : null;
    return svg || `<div class="fighter-badge-empty"></div>`;
  }

  function selectFighter(corner, id) {
    selected[corner] = byId.get(id);
    const f = selected[corner];
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

  // Home-page "this week's card" -- scraped from Sherdog.com at build time
  // (src/data/scrape_upcoming_card.py), not fetched live in-browser (this
  // site has no server and Artifact CSP blocks cross-origin fetches anyway).
  // A bout only gets a "Call This Fight" button if BOTH fighters matched our
  // own roster by exact name -- a UFC debutant, or a name-spelling mismatch
  // between Sherdog and our data, has genuinely nothing to predict from, so
  // it's shown as plain text rather than wired to a broken/guessed action.
  function renderUpcomingCard() {
    const section = document.getElementById("fight-card");
    if (!section) return;
    const card = MODEL_DATA.upcoming_card;
    if (!card || !card.bouts || !card.bouts.length) {
      section.hidden = true;
      return;
    }

    const eventDate = new Date(card.eventDate + "T00:00:00Z")
      .toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

    // Tier now comes from ufc.com's real Main Card/Prelims/Early Prelims
    // segment membership (falls back to the old positional guess only if
    // ufc.com's segment data wasn't available for this event) -- see
    // assign_tiers_ufc()/assign_tiers() in scrape_upcoming_card.py.
    const TIER_LABEL = { main_event: "Main Event", co_main: "Co-Main", featured_prelim: "Featured Prelim" };
    const TIER_ROW_CLASS = { main_event: "fc-row--main-event", co_main: "fc-row--co-main", featured_prelim: "fc-row--featured-prelim" };
    const BELT_ICON_SVG = `<svg class="fc-belt-icon" viewBox="0 0 24 14" aria-hidden="true" focusable="false">
      <rect x="0" y="4" width="24" height="6" rx="1" fill="currentColor" opacity="0.55"></rect>
      <circle cx="12" cy="7" r="6" fill="currentColor"></circle>
      <circle cx="12" cy="7" r="3" fill="var(--canvas)"></circle>
    </svg>`;
    const FORM_VERB = { W: "def.", L: "lost to", D: "drew", NC: "no contest vs." };

    // Last-up-to-5 UFC results per fighter, data from fights.csv via
    // export_web_model.py's _recent_results_payload() -- scoped to just
    // this week's card fighters for now. Each badge is a <button> (not a
    // plain hover target) since hover has no mobile equivalent -- tap
    // toggles the tooltip open via the click handler wired below, :hover/
    // :focus in the CSS cover desktop for free on top of that.
    function formBadgesHtml(fighterId) {
      // recent_results now always has a key (even an empty array) for
      // every fighter the payload actually looked up -- lets a genuine
      // "zero recorded UFC fights" debut be shown as "UFC Debut" instead
      // of silently rendering nothing, which used to be indistinguishable
      // from "not applicable" (an unmatched fighter with no id at all).
      const results = fighterId && MODEL_DATA.recent_results ? MODEL_DATA.recent_results[fighterId] : undefined;
      if (results === undefined) return "";
      if (!results.length) return `<div class="fc-debut-label">UFC Debut</div>`;
      const badges = results.map((r) => {
        const cls = r.result === "W" ? "fc-form-badge--w" : r.result === "L" ? "fc-form-badge--l" : "fc-form-badge--nd";
        const bits = [`${FORM_VERB[r.result]} ${r.opponent}`];
        if (r.method) bits.push(r.method);
        if (r.round) bits.push(`R${r.round}`);
        const tip = bits.join(" · ");
        return `<button type="button" class="fc-form-badge ${cls}">${r.result}<span class="fc-form-tip">${escapeHtml(tip)}</span></button>`;
      }).join("");
      return `<div class="fc-form">${badges}</div>`;
    }

    function boutRowClass(b) {
      // A co-main that's ALSO a title fight (a real double-title-card
      // scenario, e.g. UFC 330: Makhachev/Della Maddalena + Dern/Robertson)
      // gets the main-event's gold treatment instead of the usual silver --
      // per the user's explicit ask, not just a belt icon on a silver row.
      if (b.tier === "co_main" && b.isTitleFight) return "fc-row--co-main fc-row--co-main-title";
      return TIER_ROW_CLASS[b.tier] || "";
    }

    function boutRowHtml(b) {
      // Match by name against the FULL historical roster in scrape_upcoming_card.py,
      // but MODEL_DATA.fighters (byId) is active-roster-only (see export_web_model.py) --
      // a fighter returning from a 24+ month layoff could match by name yet still be
      // missing from byId, so predictability is gated on the byId lookup actually
      // resolving, not just on the scraper having found a fighter_id.
      const fA = b.idA ? byId.get(b.idA) : null;
      const fB = b.idB ? byId.get(b.idB) : null;
      const predictable = !!(fA && fB);
      const badgeA = fA ? `<div class="fc-badge">${flagBadgeHtml(fA.iso_code)}</div>` : "";
      const badgeB = fB ? `<div class="fc-badge">${flagBadgeHtml(fB.iso_code)}</div>` : "";
      const action = predictable
        ? `<button class="fc-call-btn" data-a="${escapeHtml(b.idA)}" data-b="${escapeHtml(b.idB)}" type="button">Call This Fight</button>`
        : `<div class="fc-nodata">No prediction available</div>`;
      // Computed up front for every predictable bout (not gated behind a
      // click) so the card reads as a preview of the model's take on the
      // whole night, not just a launcher into the full predictor below.
      // No scheduled-round data comes from the scrape, so this assumes 5
      // for the main event and 3 for everything else (standard UFC
      // convention) -- "Call This Fight" still opens the full predictor
      // where the round toggle can be corrected for a 5-round co-main, etc.
      const modelPick = predictable
        ? `<div class="fc-model-pick mono"><span class="fc-model-pick-label">Model predicts</span> ${escapeHtml(verdictText(predictFull(fA, fB, b.tier === "main_event" ? 5 : 3, MODEL_DATA)).text)}</div>`
        : "";
      const beltIcon = b.isTitleFight ? BELT_ICON_SVG : "";
      // Divisional rank, scraped from ufc.com's ranks-row alongside the
      // rest of the card data -- "C" for the reigning champion, "#N" for a
      // ranked challenger, nothing for an unranked fighter (no placeholder).
      function rankChipHtml(rank) {
        if (!rank) return "";
        const cls = rank === "C" ? "fc-rank-chip fc-rank-chip--champ" : "fc-rank-chip";
        return `<span class="${cls}">${escapeHtml(rank)}</span>`;
      }
      // Tier label (Main Event/Co-Main/Featured Prelim) sits above the
      // weight class in a left-aligned corner block, not in the "vs" spot
      // between fighter names -- the "vs" spot is just "vs" for every row
      // now, per user feedback that the tier text belongs with the weight
      // class, not swapped in as the divider.
      const tierLabel = TIER_LABEL[b.tier]
        ? `<div class="fc-tier-label">${escapeHtml(TIER_LABEL[b.tier])}</div>`
        : "";
      return `
        <div class="fc-row ${boutRowClass(b)}">
          <div class="fc-row-header">
            ${tierLabel}
            <div class="fc-weight mono">${beltIcon}${escapeHtml(b.weightClass || "")}</div>
          </div>
          <div class="fc-matchup">
            <div class="fc-fighter-block">
              <div class="fc-fighter">${badgeA}${rankChipHtml(b.rankA)}<span>${escapeHtml(b.nameA)}</span></div>
              ${formBadgesHtml(b.idA)}
            </div>
            <div class="fc-vs">vs</div>
            <div class="fc-fighter-block">
              <div class="fc-fighter">${badgeB}${rankChipHtml(b.rankB)}<span>${escapeHtml(b.nameB)}</span></div>
              ${formBadgesHtml(b.idB)}
            </div>
          </div>
          ${action}
          ${modelPick}
        </div>`;
    }

    const mainEvent = card.bouts.filter((b) => b.tier === "main_event");
    const restOfMainCard = card.bouts.filter((b) => b.tier === "co_main" || b.tier === "main_card");
    const prelims = card.bouts.filter((b) => b.tier === "featured_prelim" || b.tier === "prelim");

    let bodyHtml = mainEvent.map(boutRowHtml).join("");
    if (restOfMainCard.length) {
      bodyHtml += `<div class="fc-group-label">Main Card</div><div class="fc-rows">${restOfMainCard.map(boutRowHtml).join("")}</div>`;
    }
    if (prelims.length) {
      bodyHtml += `<div class="fc-group-label">Prelims</div><div class="fc-rows">${prelims.map(boutRowHtml).join("")}</div>`;
    }

    section.innerHTML =
      `<div class="fc-header">
        <div class="fc-eyebrow">This week's card</div>
        <h2 class="fc-event-name display">${escapeHtml(card.eventName)}</h2>
        <div class="fc-event-meta mono">${escapeHtml(eventDate)} &middot; ${escapeHtml(card.eventLocation)}</div>
      </div>
      ${bodyHtml}`;

    section.querySelectorAll(".fc-call-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectFighter("a", btn.dataset.a);
        selectFighter("b", btn.dataset.b);
        document.getElementById("predict-btn").click();
      });
    });

    section.querySelectorAll(".fc-form-badge").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const wasOpen = btn.classList.contains("open");
        section.querySelectorAll(".fc-form-badge.open").forEach((b) => b.classList.remove("open"));
        if (!wasOpen) btn.classList.add("open");
      });
    });
    document.addEventListener("click", () => {
      section.querySelectorAll(".fc-form-badge.open").forEach((b) => b.classList.remove("open"));
    });
  }

  // Weekly-scraped headlines (src/data/scrape_news.py -> export_web_model.py's
  // _news_payload()) -- always links out to the real article on ufc.com,
  // never reproduces its body text, only the headline/teaser/thumbnail the
  // source itself surfaces as a preview. Relative timestamps like "10 hours
  // ago" would read as wrong on a site that only refreshes on a schedule, so
  // those are discarded at scrape time in favor of a single "As of <date>"
  // line reflecting when THIS payload was built.
  function renderNews() {
    const section = document.getElementById("news-section");
    if (!section) return;
    const news = MODEL_DATA.news;
    if (!news || !news.articles || !news.articles.length) {
      section.hidden = true;
      return;
    }
    const asOfDate = new Date(news.asOfDate + "T00:00:00Z")
      .toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

    const cardsHtml = news.articles.map((a) => {
      const image = a.imageUrl
        ? `<img class="news-card-image" src="${escapeHtml(a.imageUrl)}" alt="" loading="lazy">`
        : "";
      const tag = a.tag ? `<div class="news-card-tag">${escapeHtml(a.tag)}</div>` : "";
      const teaser = a.teaser ? `<p class="news-card-teaser">${escapeHtml(a.teaser)}</p>` : "";
      return `
        <a class="news-card" href="${escapeHtml(a.url)}" target="_blank" rel="noopener">
          ${image}
          <div class="news-card-body">
            ${tag}
            <h3 class="news-card-headline display">${escapeHtml(a.headline)}</h3>
            ${teaser}
          </div>
        </a>`;
    }).join("");

    section.innerHTML = `
      <div class="news-header">
        <div class="news-eyebrow">Latest headlines</div>
        <h2 class="news-title display">News</h2>
        <div class="news-asof mono">As of ${escapeHtml(asOfDate)}</div>
      </div>
      <div class="news-grid">${cardsHtml}</div>`;
  }

  renderUpcomingCard();
  renderNews();

  setupCorner("a");
  setupCorner("b");

  document.getElementById("rounds-toggle").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    scheduledRounds = parseInt(btn.dataset.rounds, 10);
    document.querySelectorAll("#rounds-toggle button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  document.getElementById("predict-btn").addEventListener("click", () => {
    const result = predictFull(selected.a, selected.b, scheduledRounds, MODEL_DATA);
    renderResult(result);
    if (window.PaperTrade) window.PaperTrade.setMatchup(scheduledRounds, result);
    if (window.MyPredictions) window.MyPredictions.setMatchup(scheduledRounds, result);
  });

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

    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Sticky-nav scrollspy -- highlights whichever section is actually in
  // view so the nav answers "where am I" while scrolling, not just when you
  // click a link. Watches the same 4 sections the nav links point to; picks
  // the entry closest to the top of the viewport among those intersecting,
  // so two adjacent sections both being partially visible doesn't flicker
  // between them.
  function setupScrollspy() {
    const nav = document.getElementById("site-nav");
    if (!nav || typeof IntersectionObserver === "undefined") return;
    const links = new Map([...nav.querySelectorAll("a[data-nav]")].map((a) => [a.dataset.nav, a]));
    const sections = ["fight-card", "news-section", "predict-section", "prop-tracker", "my-predictions"]
      .map((id) => document.getElementById(id)).filter(Boolean);

    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting);
      if (visible.length === 0) return;
      visible.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      const activeId = visible[0].target.id;
      links.forEach((a, id) => a.classList.toggle("active", id === activeId));
    }, { rootMargin: "-4rem 0px -70% 0px", threshold: 0 });

    sections.forEach((s) => observer.observe(s));
  }
  setupScrollspy();
})();
