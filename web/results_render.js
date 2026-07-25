(function () {
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  const TIER_LABEL = { main_event: "Main Event", co_main: "Co-Main", featured_prelim: "Featured Prelim" };
  const BELT_ICON_SVG = `<svg class="lr-belt-icon" viewBox="0 0 24 14" aria-hidden="true" focusable="false">
    <rect x="0" y="4" width="24" height="6" rx="1" fill="currentColor" opacity="0.55"></rect>
    <circle cx="12" cy="7" r="6" fill="currentColor"></circle>
    <circle cx="12" cy="7" r="3" fill="var(--canvas)"></circle>
  </svg>`;

  // Deliberately plain text, not the odds-bar/prediction chrome the main
  // fight-card and predictor sections use -- this is a record of what
  // ALREADY happened, not a forecast, so it should read like a results
  // ticker rather than another "Call This Fight" row.
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

  function rowHtml(bout) {
    const belt = bout.isTitleFight ? BELT_ICON_SVG : "";
    const tierLabel = TIER_LABEL[bout.tier];
    return `
      <div class="lr-row">
        <div class="lr-row-header">
          ${tierLabel ? `<span class="lr-tier-label">${belt}${escapeHtml(tierLabel)}</span>` : ""}
          <span class="lr-weightclass">${escapeHtml(bout.weightClass)}</span>
        </div>
        <div class="lr-result-line">${resultLine(bout)}</div>
        <div class="lr-meta mono">${metaLine(bout)}</div>
      </div>`;
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
    const rowsHtml = bouts.map(rowHtml).join("");
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
  }

  window.ResultsRender = { renderLastResultsSection };
})();
