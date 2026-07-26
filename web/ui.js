(function () {
  // Fighter index/predictFull() are still needed here even though the
  // manual "pick any two fighters" picker lives on its own Fantasy Matchup
  // page (predict.html, a fun side toy) -- the fight-card's own "Model
  // predicts" preview line AND its per-bout "Make Your Pick" breakdown
  // (both in boutRowHtml() below) run a live prediction for every bout on
  // page load, no click needed for either.
  const { byId } = buildFighterIndex(MODEL_DATA.fighters);
  const fightCountEl = document.getElementById("fight-count");
  if (fightCountEl) fightCountEl.textContent = MODEL_DATA.total_fights.toLocaleString();

  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };

  // Single declarative "who/how/when" derivation -- also duplicated in
  // predict_ui.js (predict.html's own results panel), both reading the
  // top-ranked entries of the SAME sorted distributions a predictFull()
  // result carries, so a headline can never disagree with the detail bars
  // it's summarizing, no matter which page is rendering it.
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

  // Full model breakdown (odds bar + method/round tapes), rendered as an
  // HTML string rather than DOM nodes -- boutRowHtml() below builds the
  // whole fight card in one big innerHTML assignment, same as the rest of
  // this function. Deliberately duplicates predict_ui.js's renderResult()/
  // makeRow() rather than sharing them: that version is built around fixed
  // DOM ids for ONE result at a time, but a fight card needs N of these
  // live at once (one per predictable bout), so a string-builder keyed off
  // nothing but the result object itself is the simpler fit here -- same
  // "duplicated, not shared" call already made for verdictText() across
  // ui.js/predict_ui.js/predictions.js.
  function tapeRowHtml(label, p, predicted) {
    return `<div class="tape-row${predicted ? " predicted" : ""}">
      <div class="tape-row-label">${escapeHtml(label)}${predicted ? '<span class="predicted-chip">Predicted</span>' : ""}</div>
      <div class="tape-row-track"><div class="tape-row-fill" style="width:${(p * 100).toFixed(1)}%"></div></div>
      <div class="tape-row-pct mono">${(p * 100).toFixed(1)}%</div>
    </div>`;
  }

  function predictBreakdownHtml(r) {
    const methodRanked = Object.entries(r.method).sort((x, y) => y[1] - x[1]);
    const topMethod = methodRanked[0][0];
    const methodRows = methodRanked.map(([k, p], i) => tapeRowHtml(METHOD_NAMES[k], p, i === 0)).join("");

    const roundEntries = Object.entries(r.roundGivenFinish);
    const showRoundPredicted = topMethod !== "dec";
    let roundRows;
    if (roundEntries.length === 0) {
      roundRows = `<div class="tape-row-label" style="color:var(--ink-dim)">Finish probability too low to break down by round.</div>`;
    } else {
      const topRound = roundEntries.slice().sort((x, y) => y[1] - x[1])[0][0];
      roundRows = roundEntries.map(([rnd, p]) => tapeRowHtml(`Round ${rnd}`, p, showRoundPredicted && rnd === topRound)).join("");
    }

    return `
      <div class="fc-predict-breakdown">
        <div class="odds-bar">
          <div class="odds-fill odds-fill-a" style="width:${(r.probAWins * 100).toFixed(1)}%"></div>
          <div class="odds-fill odds-fill-b" style="width:${(r.probBWins * 100).toFixed(1)}%"></div>
        </div>
        <div class="odds-labels">
          <div class="side-a"><div class="pct mono">${(r.probAWins * 100).toFixed(1)}%</div><div>${escapeHtml(r.nameA)}</div></div>
          <div class="side-b"><div class="pct mono">${(r.probBWins * 100).toFixed(1)}%</div><div>${escapeHtml(r.nameB)}</div></div>
        </div>
        <div class="tape">
          <div class="tape-title"><span>Method of Victory</span></div>
          <div>${methodRows}</div>
        </div>
        <div class="tape">
          <div class="tape-title"><span>Round</span><span class="mono">${(r.pFinish * 100).toFixed(0)}% chance of a finish</span></div>
          <div>${roundRows}</div>
        </div>
      </div>`;
  }

  // Home-page "this week's card" -- scraped from Sherdog.com at build time
  // (src/data/scrape_upcoming_card.py), not fetched live in-browser (this
  // site has no server and Artifact CSP blocks cross-origin fetches anyway).
  // A bout only gets the inline "Make Your Pick" breakdown if BOTH fighters
  // matched our own roster by exact name -- a UFC debutant, or a name-
  // spelling mismatch between Sherdog and our data, has genuinely nothing
  // to predict from, so it's shown as plain text rather than wired to a
  // broken/guessed action.
  function renderUpcomingCard() {
    const section = document.getElementById("fight-card");
    if (!section) return;
    const card = MODEL_DATA.upcoming_card;
    if (!card || !card.bouts || !card.bouts.length) {
      section.hidden = true;
      return;
    }
    // Parallel to the "Make Your Pick" toggle buttons that end up in the
    // DOM, in the exact same order (only predictable bouts push here, and
    // only predictable bouts render a toggle) -- lets the post-render
    // wiring below pair each button with its own already-computed result
    // by plain array index, no data-attributes or JSON-in-HTML needed.
    const boutResults = [];

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
      // Main events and title fights (anywhere on the card) are scheduled
      // for 5 rounds, everything else for 3 -- same rule the "Model
      // predicts" preview line and the full breakdown below both use. No
      // scheduled-round data comes from the scrape, so this is a standard-
      // UFC-convention assumption, not a scraped fact.
      const callRounds = b.tier === "main_event" || b.isTitleFight ? 5 : 3;
      let modelPick = "";
      let action = `<div class="fc-nodata">No prediction available</div>`;
      if (predictable) {
        // Computed once per bout, reused for both the one-line preview AND
        // the full expand-on-demand breakdown below -- no second inference
        // call when a fight is expanded.
        const result = predictFull(fA, fB, callRounds, MODEL_DATA);
        boutResults.push({ result, scheduledRounds: callRounds });
        modelPick = `<div class="fc-model-pick mono"><span class="fc-model-pick-label">Model predicts</span> ${escapeHtml(verdictText(result).text)}</div>`;
        action = `
          <button class="fc-predict-toggle" type="button" aria-expanded="false">Make Your Pick</button>
          <div class="fc-predict-panel" hidden>
            ${predictBreakdownHtml(result)}
            <div class="fc-pick-mount"></div>
          </div>`;
      }
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
          ${modelPick}
          ${action}
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

    // Each toggle's matchup result is looked up by plain array index -- see
    // the boutResults comment above. The pick-form itself is mounted lazily
    // on first expand (not for every bout up front), and only once per row;
    // MyPredictions.mountCardPick() feeds it the same already-computed
    // result, so it's a live pick against the model's real output for this
    // exact bout, not a re-simulation.
    [...section.querySelectorAll(".fc-predict-toggle")].forEach((btn, i) => {
      const panel = btn.nextElementSibling;
      if (!panel || !panel.classList.contains("fc-predict-panel")) return;
      const matchupObj = boutResults[i];
      let mounted = false;
      btn.addEventListener("click", () => {
        const expanded = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!expanded));
        btn.textContent = expanded ? "Make Your Pick" : "Hide";
        panel.hidden = expanded;
        if (!expanded && !mounted && window.MyPredictions) {
          window.MyPredictions.mountCardPick(panel.querySelector(".fc-pick-mount"), matchupObj);
          mounted = true;
        }
      });
    });
  }

  // Meet the Debut Fighters -- spotlights anyone on this week's card with
  // zero recorded UFC fights, using the exact same "UFC Debut" signal
  // formBadgesHtml() above already uses (MODEL_DATA.recent_results[id]
  // resolving to a defined-but-empty array -- undefined means "never
  // looked up", not "debut"). Only bio fields (age/height/reach/stance/
  // flag/weight class) get shown, since that's genuinely all there is for
  // a fighter with no fight history to compute rolling-form stats from.
  // Degrades to hidden if nobody on this week's card is a debut, same
  // pattern as every other data-dependent home-page section.
  function renderDebutFighters() {
    const section = document.getElementById("debut-fighters");
    if (!section) return;
    const card = MODEL_DATA.upcoming_card;
    if (!card || !card.bouts || !card.bouts.length || !MODEL_DATA.recent_results) {
      section.hidden = true;
      return;
    }

    function isDebut(fighterId) {
      const results = fighterId ? MODEL_DATA.recent_results[fighterId] : undefined;
      return results !== undefined && results.length === 0;
    }

    const debuts = [];
    card.bouts.forEach((b) => {
      if (isDebut(b.idA)) debuts.push({ id: b.idA, name: b.nameA, opponent: b.nameB, weightClass: b.weightClass });
      if (isDebut(b.idB)) debuts.push({ id: b.idB, name: b.nameB, opponent: b.nameA, weightClass: b.weightClass });
    });
    if (!debuts.length) {
      section.hidden = true;
      return;
    }

    const todayDays = todayEpochDays();
    const cardsHtml = debuts.map((d) => {
      const f = d.id ? byId.get(d.id) : null;
      const badge = f ? flagBadgeHtml(f.iso_code) : `<div class="fighter-badge-empty"></div>`;
      const metaParts = [];
      if (f && f.dob_epoch_days != null) metaParts.push(`${Math.floor((todayDays - f.dob_epoch_days) / 365.25)} yrs`);
      if (f && f.height_in != null) metaParts.push(`${Math.floor(f.height_in / 12)}'${Math.round(f.height_in % 12)}"`);
      if (f && f.reach_in != null) metaParts.push(`${f.reach_in}" reach`);
      if (f && f.stance) metaParts.push(f.stance);
      return `
        <div class="debut-card">
          <div class="debut-badge">${badge}</div>
          <div class="debut-name">${escapeHtml(d.name)}</div>
          ${f && f.nickname ? `<div class="debut-nick">"${escapeHtml(f.nickname)}"</div>` : ""}
          ${metaParts.length ? `<div class="debut-meta mono">${escapeHtml(metaParts.join(" - "))}</div>` : ""}
          ${d.weightClass ? `<div class="debut-division mono">${escapeHtml(d.weightClass)}</div>` : ""}
          <div class="debut-opponent">Faces <strong>${escapeHtml(d.opponent)}</strong> this week</div>
        </div>`;
    }).join("");

    section.innerHTML = `
      <div class="section-header debut-header">
        <h2 class="section-title display">Meet the Debut Fighters</h2>
      </div>
      <div class="debut-grid">${cardsHtml}</div>`;
  }

  // Weekly-scraped headlines (src/data/scrape_news.py -> export_web_model.py's
  // _news_payload()) -- always links out to the real article on ufc.com,
  // never reproduces its body text, only the headline/teaser/thumbnail the
  // source itself surfaces as a preview. Relative timestamps like "10 hours
  // ago" would read as wrong on a site that only refreshes on a schedule, so
  // those are discarded at scrape time in favor of a single "As of <date>"
  // line reflecting when THIS payload was built.
  //
  // Home page only gets the top 3 headlines, with a "See More" link out to
  // the standalone news.html page -- shared card markup lives in
  // news_render.js so this and the full news page never drift apart.
  function renderNews() {
    const section = document.getElementById("news-section");
    if (!section || !window.NewsRender) return;
    window.NewsRender.renderNewsSection(section, MODEL_DATA.news, {
      limit: 3,
      seeMoreHref: "news.html",
      compact: true,
    });
  }

  // Last week's card + its results, derived from data this project already
  // has (see export_web_model.py's _last_results_payload()) -- no separate
  // results scraper. Home page only gets a handful of bouts, with a "See
  // More" link out to the standalone results.html page -- shared row
  // markup lives in results_render.js so this and the full page never
  // drift apart.
  function renderLastResults() {
    const section = document.getElementById("last-results-section");
    if (!section || !window.ResultsRender) return;
    window.ResultsRender.renderLastResultsSection(section, MODEL_DATA.last_results, {
      limit: 4,
      seeMoreHref: "results.html",
    });
  }

  renderUpcomingCard();
  renderDebutFighters();
  renderNews();
  renderLastResults();

  // Sticky-nav scrollspy -- highlights "This Week's Card" while it's in
  // view. Every other nav link now goes off-page (news.html, results.html,
  // predict.html, edge-calculator.html, predictions.html), so this is the
  // only section left with an on-page anchor to track.
  function setupScrollspy() {
    const nav = document.getElementById("site-nav");
    if (!nav || typeof IntersectionObserver === "undefined") return;
    const links = new Map([...nav.querySelectorAll("a[data-nav]")].map((a) => [a.dataset.nav, a]));
    const sections = ["fight-card"]
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
