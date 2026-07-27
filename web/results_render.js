(function () {
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  const TIER_LABEL = { main_event: "Main Event", co_main: "Co-Main", featured_prelim: "Featured Prelim" };
  const METHOD_NAMES = { dec: "Decision", ko: "KO/TKO", sub: "Submission" };
  const BELT_ICON_SVG = `<svg class="lr-belt-icon" viewBox="0 0 24 14" aria-hidden="true" focusable="false">
    <rect x="0" y="4" width="24" height="6" rx="1" fill="currentColor" opacity="0.55"></rect>
    <circle cx="12" cy="7" r="6" fill="currentColor"></circle>
    <circle cx="12" cy="7" r="3" fill="var(--canvas)"></circle>
  </svg>`;

  // Color-band thresholds per zone, NOT a single scale shared across zones
  // -- head strikes are far more common than leg strikes in a typical UFC
  // fight (see the real distribution this was picked from: round_stats.csv
  // medians are ~17 head / ~5 body / ~3 leg), so a shared scale would make
  // every head count look "hot" and every leg count look "cool" regardless
  // of how that fighter's night actually went. Each zone's own thresholds
  // are roughly its 25th/50th/75th percentile across all fights on record.
  const ZONE_THRESHOLDS = { head: [8, 18, 34], body: [2, 6, 12], leg: [2, 4, 9] };
  const ZONE_BAND_COLORS = ["var(--green)", "var(--gold)", "var(--bronze)", "var(--red)"];

  function zoneColor(zone, count) {
    const thresholds = ZONE_THRESHOLDS[zone];
    let band = 0;
    for (const t of thresholds) {
      if (count >= t) band++;
    }
    return ZONE_BAND_COLORS[band];
  }

  // Minimal front-facing body outline -- head/torso/legs, matching the
  // exact 3-zone granularity round_stats.csv actually has (UFCStats itself
  // only ever breaks a significant strike down as head/body/leg, nothing
  // finer like left vs. right or a specific strike type).
  function bodyDiagramSvg(strikes) {
    const headColor = zoneColor("head", strikes.head);
    const bodyColor = zoneColor("body", strikes.body);
    const legColor = zoneColor("leg", strikes.leg);
    return `
      <svg class="lr-body-diagram" viewBox="0 0 60 150" aria-hidden="true" focusable="false">
        <ellipse cx="30" cy="17" rx="13" ry="15" fill="${headColor}"></ellipse>
        <rect x="12" y="34" width="36" height="50" rx="8" fill="${bodyColor}"></rect>
        <rect x="13" y="86" width="14" height="58" rx="5" fill="${legColor}"></rect>
        <rect x="33" y="86" width="14" height="58" rx="5" fill="${legColor}"></rect>
      </svg>`;
  }

  function strikeSideHtml(name, strikes) {
    return `
      <div class="lr-strike-avatar">
        <div class="lr-strike-name">${escapeHtml(name)}</div>
        ${bodyDiagramSvg(strikes)}
        <div class="lr-strike-caption-small">Absorbed</div>
        <div class="lr-strike-numbers">
          <span><i class="lr-swatch" style="background:${zoneColor("head", strikes.head)}"></i>Head ${strikes.head}</span>
          <span><i class="lr-swatch" style="background:${zoneColor("body", strikes.body)}"></i>Body ${strikes.body}</span>
          <span><i class="lr-swatch" style="background:${zoneColor("leg", strikes.leg)}"></i>Leg ${strikes.leg}</span>
        </div>
      </div>`;
  }

  function fmtCtrl(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  // One "tale of the tape" style row for the fuller fight-stat comparison
  // (see export_web_model.py's _fight_stats()) -- aDisplay/bDisplay are
  // whatever text should actually show (e.g. "14/32" for a landed/attempted
  // pair, or a formatted control-time clock), while aShare/bShare (raw
  // numbers, not display strings) drive the proportional bar between them
  // so a 0-0 stat (e.g. neither fighter attempted a takedown) renders an
  // even, non-misleading 50/50 split rather than a divide-by-zero bar.
  function statRowHtml(label, aShare, bShare, aDisplay, bDisplay) {
    const total = aShare + bShare;
    const aPct = total > 0 ? (aShare / total) * 100 : 50;
    const bPct = 100 - aPct;
    return `
      <div class="lr-stat-row">
        <div class="lr-stat-value lr-stat-value-a mono">${escapeHtml(aDisplay)}</div>
        <div class="lr-stat-mid">
          <div class="lr-stat-label">${escapeHtml(label)}</div>
          <div class="lr-stat-bar"><div class="lr-stat-bar-a" style="width:${aPct}%"></div><div class="lr-stat-bar-b" style="width:${bPct}%"></div></div>
        </div>
        <div class="lr-stat-value lr-stat-value-b mono">${escapeHtml(bDisplay)}</div>
      </div>`;
  }

  // Each fighter's own LANDED totals (offense), side by side -- distinct
  // from the two body-diagram avatars above/beside this block, which show
  // strikes each fighter ABSORBED (the opponent's landed total). Only
  // rendered on the full results.html page (opts.showFullStats), not the
  // home page's compact sidebar widget -- see strikePanelHtml() below.
  function statsBlockHtml(stats) {
    const a = stats.a, b = stats.b;
    const rows = [
      statRowHtml("Sig. Strikes", a.sigStrLanded, b.sigStrLanded, `${a.sigStrLanded}/${a.sigStrAttempted}`, `${b.sigStrLanded}/${b.sigStrAttempted}`),
      statRowHtml("Head Strikes", a.headLanded, b.headLanded, `${a.headLanded}/${a.headAttempted}`, `${b.headLanded}/${b.headAttempted}`),
      statRowHtml("Body Strikes", a.bodyLanded, b.bodyLanded, `${a.bodyLanded}/${a.bodyAttempted}`, `${b.bodyLanded}/${b.bodyAttempted}`),
      statRowHtml("Leg Strikes", a.legLanded, b.legLanded, `${a.legLanded}/${a.legAttempted}`, `${b.legLanded}/${b.legAttempted}`),
      statRowHtml("Takedowns", a.tdLanded, b.tdLanded, `${a.tdLanded}/${a.tdAttempted}`, `${b.tdLanded}/${b.tdAttempted}`),
      statRowHtml("Control Time", a.ctrlSec, b.ctrlSec, fmtCtrl(a.ctrlSec), fmtCtrl(b.ctrlSec)),
      statRowHtml("Sub. Attempts", a.subAtt, b.subAtt, String(a.subAtt), String(b.subAtt)),
      statRowHtml("Knockdowns", a.kd, b.kd, String(a.kd), String(b.kd)),
    ].join("");
    return `<div class="lr-stats-block">${rows}</div>`;
  }

  function strikePanelHtml(bout, opts) {
    const showFullStats = opts.showFullStats && bout.stats;
    return `
      <div class="lr-strike-panel" hidden>
        <div class="lr-strike-layout">
          ${strikeSideHtml(bout.nameA, bout.strikes.a)}
          ${showFullStats ? statsBlockHtml(bout.stats) : ""}
          ${strikeSideHtml(bout.nameB, bout.strikes.b)}
        </div>
      </div>`;
  }

  // Deliberately plain text, not the odds-bar/prediction chrome the main
  // fight-card and Fantasy Matchup pages use -- this is a record of what
  // ALREADY happened, not a forecast, so it should read like a results
  // ticker rather than another "Make Your Pick" row.
  function resultLine(bout) {
    if (bout.outcome === "draw") {
      return `${escapeHtml(bout.nameA)} <span class="lr-verb">drew</span> ${escapeHtml(bout.nameB)}`;
    }
    if (bout.outcome === "nc") {
      return `${escapeHtml(bout.nameA)} vs ${escapeHtml(bout.nameB)} <span class="lr-verb">No Contest</span>`;
    }
    const winner = bout.outcome === "a" ? bout.nameA : bout.nameB;
    const loser = bout.outcome === "a" ? bout.nameB : bout.nameA;
    return `<span class="lr-winner">${escapeHtml(winner)}</span> <span class="lr-verb">def.</span> ${escapeHtml(loser)}`;
  }

  function metaLine(bout) {
    const parts = [];
    if (bout.method) parts.push(bout.method);
    if (bout.round) parts.push(`Round ${bout.round}`);
    if (bout.time) parts.push(bout.time);
    return parts.map(escapeHtml).join(" &middot; ");
  }

  // What the model actually called BEFORE this fight happened (see
  // export_web_model.py's forwarding of scrape_upcoming_card.py's
  // add_model_predictions()) -- a real prediction made ahead of time, not
  // a backtest. Only shown on the full results.html page (opts.showModelPick),
  // not the home page's compact sidebar teaser -- feedback was specifically
  // about the full page, and a 300px column has no room for a second line
  // per row on top of everything else already there.
  function modelPickLine(bout) {
    if (!bout.modelPick) return "";
    const winner = bout.modelPick.side === "a" ? bout.nameA : bout.nameB;
    const methodName = METHOD_NAMES[bout.modelPick.method] || bout.modelPick.method;
    let text = `${winner} by ${methodName}`;
    if (bout.modelPick.round) text += `, Round ${bout.modelPick.round}`;
    return `<div class="lr-model-pick mono"><span class="lr-model-pick-label">Model predicted</span> ${escapeHtml(text)}</div>`;
  }

  function rowHtml(bout, opts) {
    const belt = bout.isTitleFight ? BELT_ICON_SVG : "";
    const tierLabel = TIER_LABEL[bout.tier];
    // Only offered when round_stats.csv actually had rows for this fight --
    // never fabricated, same "omit, don't guess" rule as everything else
    // this section shows (see export_web_model.py's _fight_stats()).
    const strikeToggle = bout.strikes
      ? `<button class="lr-strike-toggle" type="button" aria-expanded="false">View Strike Map</button>`
      : "";
    const strikePanel = bout.strikes ? strikePanelHtml(bout, opts) : "";
    return `
      <div class="lr-row">
        <div class="lr-row-header">
          ${tierLabel ? `<span class="lr-tier-label">${belt}${escapeHtml(tierLabel)}</span>` : ""}
          <span class="lr-weightclass">${escapeHtml(bout.weightClass)}</span>
        </div>
        <div class="lr-result-line">${resultLine(bout)}</div>
        <div class="lr-meta mono">${metaLine(bout)}</div>
        ${opts.showModelPick ? modelPickLine(bout) : ""}
        ${strikeToggle}
        ${strikePanel}
      </div>`;
  }

  function wireStrikeToggles(sectionEl) {
    sectionEl.querySelectorAll(".lr-strike-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = btn.nextElementSibling;
        if (!panel || !panel.classList.contains("lr-strike-panel")) return;
        const expanded = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!expanded));
        btn.textContent = expanded ? "View Strike Map" : "Hide Strike Map";
        panel.hidden = expanded;
      });
    });
  }

  // Shared by the home page's short banner (opts.limit) and the standalone
  // results.html page's full list -- same underlying data either way, just
  // a different slice and an optional "See More" link out to the full page.
  function renderLastResultsSection(sectionEl, results, opts) {
    opts = opts || {};
    if (!sectionEl) return;
    if (!results || !results.bouts || !results.bouts.length) {
      sectionEl.hidden = true;
      return;
    }
    const bouts = opts.limit ? results.bouts.slice(0, opts.limit) : results.bouts;
    const rowsHtml = bouts.map((b) => rowHtml(b, opts)).join("");
    const seeMore = opts.seeMoreHref
      ? `<a class="lr-see-more" href="${escapeHtml(opts.seeMoreHref)}">See More Results &rarr;</a>`
      : "";
    sectionEl.innerHTML = `
      <div class="lr-header">
        <div class="lr-eyebrow">${escapeHtml(opts.eyebrow || "Last Week's Results")}</div>
        <h2 class="lr-title display">${escapeHtml(opts.title || results.eventName)}</h2>
      </div>
      <div class="lr-list">${rowsHtml}</div>
      ${seeMore}`;
    wireStrikeToggles(sectionEl);
  }

  window.ResultsRender = { renderLastResultsSection };
})();
