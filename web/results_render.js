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
  // fight, so a shared scale would make every head count look "hot" and
  // every leg count look "cool" regardless of how that fighter's night
  // actually went. Each zone's own thresholds are its real 25th/50th/75th
  // percentile across all historical fights (17,426 fighter-fight
  // observations from round_stats.csv/fights.csv, computed directly, not
  // guessed).
  //
  // Per-MINUTE absorbed rate, not raw totals -- a fight that goes 5 full
  // rounds naturally accumulates more raw strikes than one that ends in
  // 90 seconds, which made every long decision look artificially "bloody"
  // and every quick finish look artificially "clean" regardless of how
  // hard either fighter actually got hit. Only used to pick the color
  // band -- the per-minute number itself is never displayed anywhere,
  // the middle stat table still shows plain totals.
  const ZONE_THRESHOLDS_PER_MIN = { head: [0.923, 1.824, 3.178], body: [0.2, 0.533, 1.0], leg: [0.067, 0.369, 0.842] };
  const ZONE_BAND_COLORS = ["var(--green)", "var(--gold)", "var(--bronze)", "var(--red)"];

  function zoneColor(zone, count, durationMinutes) {
    const perMin = durationMinutes > 0 ? count / durationMinutes : 0;
    const thresholds = ZONE_THRESHOLDS_PER_MIN[zone];
    let band = 0;
    for (const t of thresholds) {
      if (perMin >= t) band++;
    }
    return ZONE_BAND_COLORS[band];
  }

  // Total fight time in minutes from the bout's own round/time (e.g.
  // round=5, time="5:00" for a decision; round=2, time="3:38" for a
  // finish) -- UFC rounds are always 5 minutes regardless of weight class
  // or gender, only the SCHEDULED round count varies, so this is just
  // (completed rounds) x 5 + the partial final round. Falls back to
  // treating the final round as a full 5:00 if `time` is missing (rare,
  // same "don't guess a specific value, use the safest assumption"
  // approach as the rest of this payload).
  function fightDurationMinutes(bout) {
    const round = bout.round || 1;
    if (!bout.time) return round * 5;
    const [mm, ss] = String(bout.time).split(":").map(Number);
    return (round - 1) * 5 + mm + (ss || 0) / 60;
  }

  // Real human body silhouette (public domain, Openclipart -- "Man body
  // silhouette" by way of Wikimedia/Openclipart, CC0/public domain,
  // https://openclipart.org/detail/314198/man-body-silhouette), NOT
  // hand-drawn -- earlier attempts at approximating a body from primitive
  // shapes (ellipse+rectangles, then a tapered-hexagon torso, then a
  // bent-arm boxer stance) all read as crude/blobby at this icon size, so
  // this uses an actual traced anatomical silhouette instead, same
  // approach already used for country flags elsewhere on this site
  // (a real asset, not an approximation of one).
  //
  // Sig. strikes only ever break down as head/body/leg (see
  // export_web_model.py's _fight_stats()) -- nothing in the source SVG
  // itself distinguishes those regions, so the SAME path is drawn three
  // times, each clipped to a horizontal band and filled with that zone's
  // color, rather than trying to trace three separate region paths by
  // hand. Band boundaries use standard figure-drawing proportions (head
  // ends at ~1/7.5 of total height, hips at ~1/2) -- verified against
  // this specific path by rendering it locally with guide lines at those
  // fractions and confirming they land on the neck and hip lines, not
  // guessed blind.
  const SILHOUETTE_VIEWBOX = "0 0 604.502 1628.762";
  const SILHOUETTE_PATH_D = "M307.71,934.044c-2.887-37.612,3.116-111.464-6.141-106.729c0,0-1.513,6.585-1.773,8.642c-1.752,13.994-0.121,74.406-2.134,96.522c0,0-7.163,57.876-11.151,74.107c-3.988,16.228-11.166,115.227-19.144,139.574c-7.976,24.345-16.75,56.8-8.774,81.958c7.976,25.157,16.752,67.352,8.774,105.492c-7.976,38.14-16.75,91.288-11.964,118.069c3.521,19.706,4.786,38.546,7.978,42.603c3.188,4.057,0,12.169,0,22.721c0,10.547,1.594,33.271-1.995,41.793c0,6.082,5.183,22.719,2.394,30.427c-2.793,7.711,0,12.174-3.591,15.417c-3.589,3.247-9.572,11.77-22.733,8.525c-7.978-2.438-8.375-8.525-7.178-9.742c1.195-1.216-4.389-0.402-4.389-0.402c-2.78,5.181-12.76,6.868-17.548-0.406c-0.796-1.218-3.587,4.461-9.969,3.243s-3.589-4.055-3.589-4.055s-8.377,0.404-10.37-4.463c-0.399,1.216-4.387,2.839-7.579-0.406c-3.19-3.245-2.791-13.793-1.594-19.07c1.195-5.277,6.796-14.401,8.774-17.854c2.791-4.867,13.161-23.533,12.762-28.806c-0.248-3.263,0.796-27.998,3.19-34.081c2.394-6.089,2.793-13.391,2.793-21.505c0-8.116,1.995-53.965-13.959-110.363c-15.954-56.396-23.531-83.984-23.928-122.938c-0.399-38.952,17.147-62.483,6.777-121.312c-10.368-58.836-14.755-97.785-15.952-101.439c-1.197-3.647-7.675-87.088-7.675-87.088c-0.914-90.865,2.12-75.593,3.35-108.574c2.353-63.252,1.051-52.022,10.05-88.612c1.577-12.158,2.454-23.04,4.031-35.203c0.657-5.071,2.01-11.418,2.669-16.489c9.196-31.653,9.142-25.304,5.191-54.251c-2.61-19.17,0.658-16.691,2.614-36.464c0.344-3.505,3.794-65.532-2.78-99.005c-4.466-13.066-8.932-26.134-13.4-39.197h-0.557c0.201,32.151-11.049,55.538-16.752,82.933c-1.867,13.001-2.392,23.885-4.297,36.877c-0.585,4.014-1.713,6.857-2.315,10.995c-2.596,17.861,2.82,24.968-3.437,57.216c-7.242,37.317-22.927,69.907-30.15,107.358c-1.197,6.198-0.553,12.864-0.316,18.911c0.585,4.031,1.615,6.33,2.475,10.552c1.195,5.861,1.78,13.168,2.863,18.818c1.334,6.942,1.438,15.31,1.664,23.435c0.207,7.346,1.037,12.54,0.288,21.87c-0.218,2.72-0.033,36.328-3.134,48.688c-1.434,5.7-4.692,5.273-6.077,4.279c-5.716-7.654-0.615-25.119-6.28-43.599c-0.559,0.38-0.559,0.046-1.118,0.425c0.084,4.047-0.667,9.273-0.179,15.482c0.779,9.977,0.378,14.142,0.07,18.034c-0.832,10.572-1.344,19.719-3.924,25.218c-1.395,2.974-5.2,5.59-8.669,1.478c-1.937-3.302-2.208-8.173-2.411-15.058c-0.878-30.054-0.969-20.294-1.334-26.969c-0.388-7.183-0.61-12.768-0.61-12.768c-0.89-0.236-1.494-0.354-2.345-0.022c-2.167,19.698-0.178,15.719-2.96,39.445c-0.491,4.187-0.139,12.028-1.225,17.079c-2.229,10.363-11.671,9.05-12.444,1.027c-0.265-2.74-0.886-5.687-1.238-8.086c-0.38-2.592-0.164-6.26-0.254-8.989c-0.139-4.209-0.565-7.888-0.888-12.069c-0.373-4.839,2.084-17.895,0.023-27.551c-0.026,0-1.142,0-1.116,0c-0.734,4.359-2.245,10.954-3.969,19.445c-0.265,1.309-0.399,3.632-0.681,4.975c-1.549,7.394-1.393,11.575-2.166,16.148c-1.214,7.224,0.053,8.318-2.505,13.124c-2.791,5.249-7.135,2.857-8.296,0.08c-1.801-4.311-2.814-11.342-2.795-19.975c0.037-15.995,2.716-19.356,2.825-40.619c0.023-4.404,0.267-8.277-0.282-12.349v2.129c-2.435,4.109-3.373,8.129-7.816,10.222c-2.213,0.79-4.001,1.246-5.663,0.365c-1.624-0.853-2.718-0.523-2.119-3.736c0.461-2.47,1.59-5.861,2.014-8.907c0.638-4.582,0.555-8.698,1.641-13.506c0.632-2.789,2.368-6.204,3.203-8.885c1.366-4.384,1.958-10.449,3.156-12.473c0.903-1.533,3.004-3.975,4.31-5.698c0.346-0.457,8.944-13.182,12.286-17.574c3.356-4.409,5.699-8.14,5.699-8.14c0.051-11.746,3.059-18.778,2.08-30.076c-1.692-19.557-0.495,1.76-2.339-121.232c4.78-68.261,11.045-49.621,17.136-111.518c4.058-41.052,4.798-56.274,7.364-64.797c2.452-8.147,6.34-29.092,5.657-43.675c-0.459-9.801-0.45-14.221-1.543-20.477c-2.05-11.754-1.431-42.739,11.725-69.299c11.477-23.175,27.318-34.048,49.629-43.289c15.531-6.434,14.433-2.79,42.978-18.213c17.074-9.227,57.814-33.258,65.621-50.863c0.124-16.319-0.366-14.443,0.009-29.778c0,0-3.213-13.298-4.53-22.591c-6.854-0.074-10.769-6.449-13.127-14.318c-2.094-6.98-1.877-19.262-1.918-20.898c-0.163-6.367-0.441-12.45,4.995-14.77c1.445-0.341,1.701-0.376,2.351-0.208c0.836,0.213,1.278,1.131,2.115,1.344c-1.056-33.236,4.238-59.246,25.686-73.844c38.147-25.962,84.194-4.385,96.595,31.244c4.15,11.926,4.212,28.343,2.791,42.601h0.557c1.212-1.02,1.445-1.628,3.877-1.237c4.303,1.889,5.591,6.919,5.712,15.964c0.177,13.445-0.6,22.432-9.367,31.903c-2.189,2.366-4.282,2.09-7.477,3.358c-0.207,4.645-2.703,18.616-2.703,18.616s-1.703,28.168-0.651,31.938c4.364,15.563,55.746,47.859,85.792,61.08c17.748,7.814,48.444,11.768,69.031,44.574c13.863,22.079,19.151,53.497,15.704,74.476c-1.369,8.304-2.896,28.95-0.455,42.944c10.918,54.033,5.22,16.283,12.421,88.953c3.703,37.295,4.626,32.485,12.068,67.063c0.877,4.079,0.794,6.836,1.346,12.065c1.663,15.866,5.62,30.424,2.492,104.929c-2.799,66.377-3.96,53.491-0.943,68.354c1.208,5.992-3.063,8.431,14.057,30.796c1.5,1.958,3.088,4.873,4.581,6.495c1.694,1.845,3.269,2.407,4.457,4.93c1.314,2.802,0.723,5.179,1.38,8.273c0.807,3.74,1.647,6.727,4.105,12.349c1.013,2.327-0.075,8.781,0.653,13.461c0.41,2.637,1.961,5.16,2.388,7.739c0.002,0.022,0.939,1.3,0.762,2.483c-0.256,1.687-2.004,3.38-5.381,2.653c-6.446-1.04-7.101-6.232-10.611-10.035c0.08,5.339-0.595,7.281,1.099,29.728c0.427,5.661,3.893,30.336-1.199,40.461c-1.756,3.495-5.721,2.996-7.803,0.51c-5.565-6.642-0.373-10.685-8.925-51.36c-1.116-5.271-2.349-0.61-2.349-0.61c-0.16,25.464,1.666,13.068-0.25,31.836c-0.942,9.126-0.375,27.282-5.445,28.639c-4.658,1.253-7.366-2.318-8.181-5.416c-2.122-8.108-1.956-18.062-2.014-19.063c-0.154-2.729-1.026-9.119-1.135-11.913c-0.365-9.214,0.497-12.819-1.302-26.917c-0.143-1.174-1.462-1.35-1.462-1.35c-1.961,1.819-0.851,8.454-1.186,11.551c-3.15,28.922,0.442,32.063-4.351,43.031c-1.628,3.721-6.48,3.881-8.433,0.491c-1.442-2.512-1.526-5.726-1.705-6.352c-1.756-6.089-1.334-12.805-1.863-18.569c-0.354-3.81-0.926-4.884-0.856-7.958c0.233-10.437,2.309-16.964,0.412-27.651c-0.373-0.187-0.747-0.378-1.118-0.564c-0.745,1.157-0.459,2.19-0.832,3.716c-1.212,4.928-1.404,12.154-2.204,17.859c-1.259,9.017,0.911,20.359-4.784,22.732c-2.791-0.191-2.603-0.38-4.274-2.084c-5.376-13.557-1.805-31.088-3.117-47.522c-1.586-19.77-0.064-18.681,0.35-25.185c1.917-31.072,0.966-16.394,3.205-32.181c2.262-15.944,3.054-13.863,4.133-21.228c2.059-14.053-0.666-20.851-4.999-37.704c-0.491-1.921-1.163-3.497-1.622-5.483c-2.089-8.967-5.855-19.003-8.234-27.605c-19.318-69.827-14.488-54.078-17.153-72.648c-1.286-8.943-1.133-5.494-0.113-35.667c-0.809-5.598-2.364-10.439-3.177-16.035c-1.797-12.391-2.844-25.539-4.639-37.927c-5.657-26.218-15.956-48.792-16.193-80.094c-0.369,0.189-0.743,0.378-1.116,0.569c-2.808,11.112-8.142,23.815-12.783,35.175c-2.405,5.894-0.418,6.326-2.522,15.378c-2.886,12.424-4.145,63.823-0.885,88.047c0.927,6.952,1.197,1.809,2.793,20.448c0.284,3.354-0.164,5.8-0.448,9.638c-0.233,3.137-0.224,7.706-0.638,10.272c-1.468,9.087-3.239,15.532-1.15,24.966c2.02,9.109,2.677,4.255,8.751,34.942c0.994,5.012,0.751,7.619,1.466,13.365c0.565,4.546,2.078,12.258,2.836,16.265c0.745,3.916,1.063,8.954,1.788,12.814c1.568,8.348,8.083,29.891,8.46,62.064c0.704,59.53,4.476,55.504,4.024,102.244c-0.614,56.92-8.584,147.539-14.226,174.122c-7.577,35.704-12.762,81.961-9.967,90.885c2.787,8.926,12.363,79.119,6.775,111.58c-5.582,32.455-34.296,139.976-33.897,161.887c0.397,21.911-5.919,41.448,0.397,55.584c3.99,8.926,1.199,27.188,2.793,32.459c1.596,5.275,3.589,20.288,9.173,24.751c5.584,4.465,15.154,27.184,13.161,34.489c-1.995,7.302-5.185,12.983-10.37,10.956c-4.385,4.869-9.971,3.651-11.166,3.245c-1.197-0.406-4.387,8.926-13.959,1.624c-2.392,3.649-5.582,6.488-12.365,3.649c-6.779-2.839-4.784-3.649-4.784-3.649l-5.185,0.81c0,0,0.796,10.55-8.776,10.55c-9.57,0-23.529-6.493-22.731-17.04c0.796-10.552-0.798-24.753,3.988-39.358c-4.786-10.144-5.185-26.372-2.791-34.085c2.392-7.704,0-17.85-0.401-23.123c-0.399-5.277,7.579-37.33,7.579-46.254c0-8.93,0.798-90.483-4.786-102.654c-5.584-12.169-12.762-60.049-4.387-93.316c0,0,10.11-48.282,10.37-60.455c0.397-18.666-20.341-75.874-20.341-98.593c0-22.723-13.56-109.147-15.154-115.64C315.225,977.372,307.71,934.044,307.71,934.044";
  const SILHOUETTE_HEAD_BOTTOM = 227;
  const SILHOUETTE_HIP_LINE = 814;
  const SILHOUETTE_TOTAL_HEIGHT = 1629;
  // Below the hip line, the silhouette's hands hang down alongside the
  // upper legs (confirmed by sampling the actual path geometry: at
  // y=814-925 the figure is three separate horizontal segments -- left
  // hand, the two leg columns, right hand -- not two like above the hip
  // line). A plain horizontal band there would count knuckle/wrist pixels
  // as "leg", which is wrong -- hand strikes are body-zone strikes. Fixed
  // by making the leg clip a narrower CENTRAL column (the two leg columns
  // top out around x=145-460 at every y sampled from 814 down to the
  // feet) and adding the two outer strips to the body clip instead, so
  // hands fall under body coloring like the rest of the arm above them.
  const SILHOUETTE_LEG_LEFT = 145;
  const SILHOUETTE_LEG_RIGHT = 460;
  let silhouetteIdCounter = 0;

  function bodyDiagramSvg(strikes, durationMinutes) {
    const headColor = zoneColor("head", strikes.head, durationMinutes);
    const bodyColor = zoneColor("body", strikes.body, durationMinutes);
    const legColor = zoneColor("leg", strikes.leg, durationMinutes);
    const uid = `sil${silhouetteIdCounter++}`;
    const legWidth = SILHOUETTE_LEG_RIGHT - SILHOUETTE_LEG_LEFT;
    const belowHipHeight = SILHOUETTE_TOTAL_HEIGHT - SILHOUETTE_HIP_LINE;
    return `
      <svg class="lr-body-diagram" viewBox="${SILHOUETTE_VIEWBOX}" aria-hidden="true" focusable="false">
        <defs>
          <path id="${uid}-shape" d="${SILHOUETTE_PATH_D}"></path>
          <clipPath id="${uid}-head"><rect x="0" y="0" width="605" height="${SILHOUETTE_HEAD_BOTTOM}"></rect></clipPath>
          <clipPath id="${uid}-body">
            <rect x="0" y="${SILHOUETTE_HEAD_BOTTOM}" width="605" height="${SILHOUETTE_HIP_LINE - SILHOUETTE_HEAD_BOTTOM}"></rect>
            <rect x="0" y="${SILHOUETTE_HIP_LINE}" width="${SILHOUETTE_LEG_LEFT}" height="${belowHipHeight}"></rect>
            <rect x="${SILHOUETTE_LEG_RIGHT}" y="${SILHOUETTE_HIP_LINE}" width="${605 - SILHOUETTE_LEG_RIGHT}" height="${belowHipHeight}"></rect>
          </clipPath>
          <clipPath id="${uid}-legs"><rect x="${SILHOUETTE_LEG_LEFT}" y="${SILHOUETTE_HIP_LINE}" width="${legWidth}" height="${belowHipHeight}"></rect></clipPath>
        </defs>
        <use href="#${uid}-shape" fill="${headColor}" clip-path="url(#${uid}-head)"></use>
        <use href="#${uid}-shape" fill="${bodyColor}" clip-path="url(#${uid}-body)"></use>
        <use href="#${uid}-shape" fill="${legColor}" clip-path="url(#${uid}-legs)"></use>
      </svg>`;
  }

  function strikeSideHtml(name, strikes, durationMinutes) {
    return `
      <div class="lr-strike-avatar">
        <div class="lr-strike-name">${escapeHtml(name)}</div>
        ${bodyDiagramSvg(strikes, durationMinutes)}
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
    const duration = fightDurationMinutes(bout);
    return `
      <div class="lr-strike-panel" hidden>
        <div class="lr-strike-layout">
          ${strikeSideHtml(bout.nameA, bout.strikes.a, duration)}
          ${showFullStats ? statsBlockHtml(bout.stats) : ""}
          ${strikeSideHtml(bout.nameB, bout.strikes.b, duration)}
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
    // this section shows (see export_web_model.py's _fight_stats()). Also
    // gated on opts.showStrikeMap -- the home page's compact sidebar widget
    // wants just the plain result line, no strike map at all (feedback:
    // "should just show the fight results"), so it omits this option.
    const strikeToggle = opts.showStrikeMap && bout.strikes
      ? `<button class="lr-strike-toggle" type="button" aria-expanded="false">View Strike Map</button>`
      : "";
    const strikePanel = opts.showStrikeMap && bout.strikes ? strikePanelHtml(bout, opts) : "";
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

  // Read-only peek at My Predictions' own localStorage log -- deliberately a
  // small duplicate read here rather than embedding the whole predictions.js
  // module on pages that don't otherwise need it (home page sidebar/
  // results.html), same "duplicated, not shared" call already made for
  // verdictText() across ui.js/predict_ui.js/predictions.js. Only ever reads;
  // never writes/settles anything here, so a mismatched or corrupt entry can
  // at worst just fail to match (falls back to "you didn't pick this one"),
  // never corrupts the real log.
  const MY_PREDICTIONS_STORAGE_KEY = "ufc_my_predictions_v1";
  function loadMyPredictions() {
    try {
      const raw = localStorage.getItem(MY_PREDICTIONS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  // Scored against the WHOLE event (results.bouts), not just whatever slice
  // opts.limit is currently showing -- a compact 4-bout sidebar teaser should
  // still report accuracy for the full 12-bout card. Winner-only (matches the
  // "9/12 correct winners" framing this was asked for) -- draws/no-contests
  // are skipped on both sides, same "omit, don't guess" rule as everywhere
  // else in this file. A user prediction counts as "for this fight" if its
  // stored fighter names match the bout's pair in either order; no fuzzier
  // matching than that is attempted.
  function computeAccuracySummary(results) {
    let modelN = 0, modelHits = 0;
    let userN = 0, userHits = 0;
    const myPreds = loadMyPredictions();
    results.bouts.forEach((b) => {
      if (b.outcome !== "a" && b.outcome !== "b") return;
      const winnerName = b.outcome === "a" ? b.nameA : b.nameB;
      if (b.modelPick) {
        modelN++;
        if (b.modelPick.side === b.outcome) modelHits++;
      }
      const pred = myPreds.find((p) =>
        (p.fighter_a === b.nameA && p.fighter_b === b.nameB) ||
        (p.fighter_a === b.nameB && p.fighter_b === b.nameA)
      );
      if (pred) {
        userN++;
        if (pred.picked_winner === winnerName) userHits++;
      }
    });
    return { modelN, modelHits, userN, userHits };
  }

  function accuracySummaryHtml(results) {
    const { modelN, modelHits, userN, userHits } = computeAccuracySummary(results);
    if (modelN === 0 && userN === 0) return "";
    const parts = [];
    if (modelN > 0) parts.push(`Model called <strong>${modelHits}/${modelN}</strong> correct`);
    if (userN > 0) parts.push(`You called <strong>${userHits}/${userN}</strong> correct`);
    return `<div class="lr-accuracy-summary mono">${parts.join(" &middot; ")}</div>`;
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
      ${accuracySummaryHtml(results)}
      <div class="lr-list">${rowsHtml}</div>
      ${seeMore}`;
    wireStrikeToggles(sectionEl);
  }

  window.ResultsRender = { renderLastResultsSection };
})();
