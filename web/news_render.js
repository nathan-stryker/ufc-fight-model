(function () {
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function formatAsOfDate(dateStr) {
    return new Date(dateStr + "T00:00:00Z")
      .toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
  }

  function cardHtml(a) {
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
  }

  // Shared by the home page's 3-headline preview and the standalone news.html
  // page's full grid -- same card markup either way, just a different slice
  // of `news.articles` and an optional "See More" link out to the full page.
  function renderNewsSection(sectionEl, news, opts) {
    opts = opts || {};
    if (!sectionEl) return;
    if (!news || !news.articles || !news.articles.length) {
      sectionEl.hidden = true;
      return;
    }
    const articles = opts.limit ? news.articles.slice(0, opts.limit) : news.articles;
    const cardsHtml = articles.map(cardHtml).join("");
    const seeMore = opts.seeMoreHref
      ? `<a class="news-see-more" href="${escapeHtml(opts.seeMoreHref)}">See More News &rarr;</a>`
      : "";
    sectionEl.innerHTML = `
      <div class="news-header">
        <div class="news-eyebrow">${escapeHtml(opts.eyebrow || "Latest headlines")}</div>
        <h2 class="news-title display">${escapeHtml(opts.title || "News")}</h2>
        <div class="news-asof mono">As of ${escapeHtml(formatAsOfDate(news.asOfDate))}</div>
      </div>
      <div class="news-grid">${cardsHtml}</div>
      ${seeMore}`;
  }

  window.NewsRender = { renderNewsSection };
})();
