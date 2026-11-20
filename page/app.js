// Beta Quest Seed Explorer: the page. Python runs in worker.js; this only draws.
//
// A lookup shows the board first (the quick overview), then asks again with the glitch
// behind each square named, which takes a few seconds more. A square's details are one
// more call. The address keeps the seed and square (#274451/3), so a view can be shared.

// Square difficulty fifths over 5,000 reachable squares of 200 random seeds at the hard
// tier (2026-11-19): a square below 14.9 is in the lightest fifth, 35.0 and over in the
// heaviest.
const BIN_CUTS = [14.9, 20.4, 26.1, 35.0];
const BIN_LABELS = ["Very light", "Light", "Medium", "Heavy", "Very heavy"];
const TIER_SHORT = { common_glitches: "Common", hard_glitches: "Hard" };
const TIER_ORDER = ["hard_glitches", "common_glitches"];

const $ = (id) => document.getElementById(id);
const statusLine = $("status");
const form = $("seed-form");
const input = $("seed-input");

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function setStatus(text, busy = false, error = false) {
  statusLine.textContent = text || "";
  statusLine.classList.toggle("busy", Boolean(text) && busy);
  statusLine.classList.toggle("error", error);
}

// ---------------------------------------------------------------- the worker
const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
const pending = new Map();
let nextId = 0;
worker.onmessage = (event) => {
  const message = event.data;
  if (message.status) return setStatus(message.status, true);
  const waiting = pending.get(message.id);
  if (!waiting) return;
  pending.delete(message.id);
  if (message.ok) waiting.resolve(message.result);
  else waiting.reject(new Error(message.error));
};
worker.onerror = (event) => {
  setStatus(`The page could not start Python: ${event.message || "unknown error"}.`, false, true);
};
function call(name, args) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, call: name, args });
  });
}

// ---------------------------------------------------------------- build info
let build = { effort_quantiles: null };
const buildReady = fetch(new URL("./build.json", import.meta.url), { cache: "no-cache" })
  .then((response) => (response.ok ? response.json() : build))
  .then((info) => { build = info; renderFooter(); })
  .catch(() => renderFooter());

function renderFooter() {
  const foot = $("foot");
  foot.replaceChildren(
    h("p", {}, "Everything runs in your browser: the board is BingoSync's own generator, the doors are ",
      "Beta Quest's shuffle for the seed's file name, and the rest is the project's reachability model. ",
      "Difficulty and workload are model estimates that may be wildly off; ",
      "a route is the fewest loading zones the model finds, not the fastest way."),
    h("p", {}, `Model ${build.profile_version || "?"} · Pyodide ${build.pyodide_version || "?"}`
      + (build.built ? ` · built ${build.built}` : ""),
      build.source_url ? " · " : null,
      build.source_url ? h("a", { href: build.source_url, rel: "noopener" }, "Source on GitHub") : null),
  );
}

function effortShare(effort) {
  const q = build.effort_quantiles;
  if (!q || effort === null || effort === undefined) return null;
  let low = 0;
  let high = q.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (q[mid] < effort) low = mid + 1; else high = mid;
  }
  return Math.min(1, low / (q.length - 1));
}

// ---------------------------------------------------------------- helpers
function bin(difficulty) {
  let index = 0;
  while (index < BIN_CUTS.length && difficulty >= BIN_CUTS[index]) index += 1;
  return index;
}

function prettyRule(rule) {
  return rule
    .replace(/can_use\((\w+)\)/g, "$1")
    .replace(/can_play\((\w+)\)/g, "play $1")
    .replace(/'([^']+)'/g, "$1")
    .replace(/\bis_adult\b/g, "adult")
    .replace(/\bis_child\b/g, "child")
    .replace(/\bhas_explosives\b/g, "explosives")
    .replace(/\bcan_dive\b/g, "diving")
    .replace(/\b(glitch|logic|bq)_(\w+)/g, (_, kind, name) => `${kind === "logic" ? "trick" : "glitch"} "${name.replace(/_/g, " ")}"`)
    .replace(/_/g, " ");
}

function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

// ---------------------------------------------------------------- state
const state = { seed: null, overview: null, attributed: false, selected: null, token: 0 };

function setAddress() {
  const square = state.selected === null ? "" : `/${state.selected}`;
  history.replaceState(null, "", `#${state.seed}${square}`);
}

async function lookUp(seed, square = null) {
  const token = ++state.token;
  Object.assign(state, { seed, overview: null, attributed: false, selected: square });
  setAddress();
  input.value = String(seed);
  document.title = `Seed ${seed} · Beta Quest Seed Explorer`;
  setStatus(`Analyzing seed ${seed}…`, true);
  form.querySelector("button[type=submit]").disabled = true;
  try {
    await buildReady;
    const quick = await call("overview", { seed, attribute: false });
    if (token !== state.token) return;
    state.overview = quick;
    $("intro").hidden = true;
    $("main").hidden = false;
    renderAll();
    const glitchy = Object.keys(quick.report.tier_squares).length > 0;
    if (glitchy) setStatus("Working out which glitches each square needs…", true);
    else setStatus("");
    if (state.selected !== null) showSquare(state.selected);
    if (glitchy) {
      const full = await call("overview", { seed, attribute: true });
      if (token !== state.token) return;
      state.overview = full;
      state.attributed = true;
      renderAll();
      setStatus("");
      if (state.selected !== null) showSquare(state.selected);
    } else {
      state.attributed = true;
    }
  } catch (error) {
    if (token === state.token) setStatus(`Something went wrong: ${error.message}`, false, true);
  } finally {
    if (token === state.token) form.querySelector("button[type=submit]").disabled = false;
  }
}

function renderAll() {
  renderSummary();
  renderBoard();
  renderLegend();
  if (state.selected === null) renderDetailHint();
}

// ---------------------------------------------------------------- summary
function renderSummary() {
  const page = state.overview;
  const report = page.report;
  const share = effortShare(report.effort);
  const workload = report.effort === null
    ? h("dd", {}, "None", h("small", {}, "no level of glitches reaches every square"))
    : h("dd", {}, `${report.effort_band} · ${report.effort.toFixed(1)} of 100`,
      h("small", {}, share === null
        ? "an estimate, not a time"
        : `more work than ${Math.min(share * 100, 99.9).toFixed(share < 0.01 || share > 0.99 ? 1 : 0)}% of seeds that can be finished; an estimate, not a time`));
  const facts = h("dl", { class: "facts" },
    h("div", {}, h("dt", {}, "Seed"), h("dd", {}, String(page.seed),
      h("small", {}, `file name ${page.filename}`))),
    h("div", {}, h("dt", {}, "Glitches needed"), h("dd", {}, report.access_tier_label)),
    h("div", {}, h("dt", {}, "Workload"), workload),
    h("div", {}, h("dt", {}, "A new file starts in"), h("dd", {}, page.start.child,
      h("small", {}, `as adult: ${page.start.adult}`))),
  );
  $("summary").replaceChildren(facts, h("div", { class: "reasons" }, ...reasonNodes(page)));
}

function reasonNodes(page) {
  const report = page.report;
  const tier = report.access_tier;
  if (tier === "trapped") {
    return [
      h("p", {}, h("strong", {}, "Not one square is reachable: "),
        "Link can't leave the area the file starts in."),
      report.pocket.length ? h("p", {}, "Link is stuck in: ", report.pocket.join("; ")) : null,
    ];
  }
  if (tier === "impossible") {
    return [
      h("p", {}, h("strong", {}, `${plural(Object.keys(report.impossible_causes).length, "square")} ` +
        "can never be reached"), ", even with every glitch allowed and every item the seed can give:"),
      h("ul", {}, Object.entries(report.impossible_causes).map(([square, cause]) =>
        h("li", {}, h("strong", {}, square), `: ${cause}`))),
    ];
  }
  if (tier === "unproven" || tier === "unproven_marginal") {
    return [
      h("p", {}, h("strong", {}, `The model found no route for ${plural(report.unrouted.length, "square")}`),
        " at any level of glitches. The model may be missing a way, so this doesn't prove they're impossible."),
    ];
  }
  const tiers = report.tier_squares;
  if (!Object.keys(tiers).length) return [h("p", {}, "Every square has a glitchless route.")];
  const opener = Object.fromEntries(page.squares.map((square) => [square.name, square.opened_by]));
  const nodes = [h("p", {}, "Every other square has a glitchless route. These need glitches:")];
  for (const name of TIER_ORDER) {
    const reasons = tiers[name];
    if (!reasons || !reasons.length) continue;
    nodes.push(h("h3", {}, `${name === "hard_glitches" ? "Hard" : "Common"} glitches`));
    if (!state.attributed) {
      nodes.push(h("p", {}, reasons.map((reason) => reason.square).join("; "),
        " ", h("span", { class: "pending" }, "(working out which glitches…)")));
      continue;
    }
    const groups = new Map();
    for (const reason of reasons) {
      const key = opener[reason.square] || "not named";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(reason.square);
    }
    nodes.push(h("ul", {}, [...groups].map(([by, squares]) =>
      h("li", {}, h("strong", {}, by), `: ${squares.join("; ")}`))));
  }
  return nodes;
}

// ---------------------------------------------------------------- board
function renderBoard() {
  const board = $("board");
  board.replaceChildren(...state.overview.squares.map((square) => {
    const routed = square.difficulty !== null;
    const which = routed ? bin(square.difficulty) : null;
    const chip = square.lowest_tier === null ? "No route" : TIER_SHORT[square.lowest_tier];
    const label = [
      square.name,
      routed ? `${BIN_LABELS[which]} (${square.difficulty.toFixed(1)})` : "no route found",
      square.lowest_tier ? square.lowest_tier_label : null,
    ].filter(Boolean).join(". ");
    return h("button", {
      type: "button",
      class: `square ${routed ? `bin-${which}` : "no-route"}`,
      "aria-pressed": String(state.selected === square.index),
      "aria-label": label,
      title: label,
      onclick: () => showSquare(square.index, true),
    },
    routed ? h("span", { class: "score", "aria-hidden": "true" }, square.difficulty.toFixed(0)) : null,
    chip ? h("span", { class: "chip", "aria-hidden": "true" }, chip) : null,
    h("span", { class: "name" }, square.name));
  }));
}

function renderLegend() {
  const items = BIN_LABELS.map((label, index) => h("span", { class: "item" },
    h("span", { class: `swatch bin-${index}` }), label));
  items.push(h("span", { class: "item" }, h("span", { class: "swatch no-route" }), "No route"));
  $("legend").replaceChildren(...items, h("p", {},
    "Shade: how hard the square is, from Very light to Very heavy (each shade is a fifth of 5,000 random squares). ",
    "The number in the corner is its difficulty from 0 to 100. ",
    "A Common or Hard tag means the square needs those glitches; no tag means it needs none."));
}

// ---------------------------------------------------------------- detail
function renderDetailHint() {
  $("detail").replaceChildren(
    h("h2", {}, "Pick a square"),
    h("p", { class: "hint" }, "Click any square to see how hard it is, what it needs, and a route to it from where a new file starts."),
  );
}

const stacked = window.matchMedia("(max-width: 979px)");

async function showSquare(index, tapped = false) {
  state.selected = index;
  setAddress();
  // On a phone the details sit under the board; bring them up after a tap.
  if (tapped && stacked.matches) $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  [...$("board").children].forEach((node, i) => node.setAttribute("aria-pressed", String(i === index)));
  const summary = state.overview?.squares[index];
  const detail = $("detail");
  detail.replaceChildren(
    h("h2", {}, summary ? summary.name : "Square"),
    h("p", { class: "hint" }, state.attributed ? "Finding routes…" : "Finishing the glitch check, then finding routes…"),
  );
  const token = state.token;
  try {
    const square = await call("square", { seed: state.seed, index });
    if (token !== state.token || state.selected !== index) return;
    renderDetail(square);
  } catch (error) {
    if (token === state.token && state.selected === index) {
      detail.replaceChildren(h("h2", {}, summary ? summary.name : "Square"),
        h("p", { class: "note" }, `Something went wrong: ${error.message}`));
    }
  }
}

function renderDetail(square) {
  const routed = square.difficulty !== null;
  const which = routed ? bin(square.difficulty) : null;
  const badges = h("div", { class: "badges" },
    h("span", { class: "badge" }, routed ? h("span", { class: `swatch bin-${which}` }) : null,
      routed ? `${BIN_LABELS[which]} · ${square.difficulty.toFixed(1)} of 100` : "No route found"),
    h("span", { class: "badge" }, square.lowest_tier ? square.lowest_tier_label : "Not reachable even with glitches"),
  );
  const nodes = [h("h2", {}, square.name), badges];
  if (square.lowest_tier && square.lowest_tier !== "glitchless") {
    nodes.push(h("p", {}, h("strong", {}, `Needs ${square.lowest_tier_label.toLowerCase()}: `),
      square.opened_by || (state.attributed ? "a combination of glitches" : "working out which…")));
  }
  if (square.after_sky_chest) {
    nodes.push(h("p", {}, "Only reachable after you beat the Sky Temple and open its chest."));
  }
  if (routed && square.factors.length) {
    nodes.push(h("h3", {}, "What makes it hard"),
      h("ul", { class: "factors" }, square.factors.map((factor) => h("li", {}, factor))));
  }
  nodes.push(...routeNodes(square));
  $("detail").replaceChildren(...nodes);
}

function routeNodes(square) {
  const nodes = [h("h3", {}, square.routes.length > 1 ? `Routes to the ${square.routes.length} places it needs` : "Route")];
  if (!square.start) {
    nodes.push(h("p", {}, "This seed has no start the model can route from."));
    return nodes;
  }
  if (!square.routes.some((entry) => entry.route)) {
    nodes.push(h("p", {}, `No route from where a new file starts (${square.start}) reaches it, `
      + `even with ${square.route_tier_label.toLowerCase()} allowed.`));
    return nodes;
  }
  nodes.push(h("p", { class: "explain" },
    `From where a new file starts (${square.start}), as child, with ${square.route_tier_label.toLowerCase()} allowed. `,
    "Each step is a loading zone: the door named by where it leads in the unshuffled game, then where it really goes on this seed. ",
    "A step reads what you will have by the end, except what this place gives, so go in an order where you already hold what it needs."));
  if (square.places_needed > square.routes_shown) {
    nodes.push(h("p", { class: "note" }, `Showing the first ${square.routes_shown} of ${square.places_needed} places.`));
  }
  square.routes.forEach((entry, i) => {
    const route = entry.route;
    if (!route) {
      nodes.push(h("div", { class: "route" }, h("strong", {}, entry.target), h("p", {}, "No route from the start reaches it.")));
      return;
    }
    const meta = [
      plural(route.loading_zones, "loading zone"),
      `ends as ${route.age}`,
      route.level ? route.level_note : null,
    ].filter(Boolean).join(" · ");
    const steps = route.steps.length
      ? h("ol", { class: "steps" }, route.steps.map(stepNode))
      : h("p", {}, "It's where the file starts.");
    nodes.push(h("details", { class: "route", open: i === 0 },
      h("summary", {}, entry.target, h("span", { class: "meta" }, `${route.ends_in} · ${meta}`)),
      route.without_target ? null
        : h("p", { class: "note" }, "No order reaches this before its own item, so this route assumes you already have it."),
      steps));
  });
  return nodes;
}

function stepNode(step) {
  const parts = [];
  if (step.age) parts.push(h("span", { class: "age" }, step.age));
  if (step.at) parts.push(h("span", { class: "where" }, `${step.at}: `));
  parts.push(step.do);
  if (step.arrive) parts.push(" → ", h("span", { class: "arrive" }, step.arrive));
  if (step.becomes) parts.push(h("span", { class: "grow" }, `now ${step.becomes}`));
  if (step.kind === "refire" && step.deaths?.length) {
    parts.push(h("ol", { class: "deaths" }, step.deaths.map((death, n) =>
      h("li", {}, `${n === 0 ? "Die" : "Die again"} (re-fires ${death.refires}) → `,
        h("span", { class: "arrive" }, death.arrive || "?")))));
  }
  if (step.needs) parts.push(h("span", { class: "needs", title: step.needs }, `Needs: ${prettyRule(step.needs)}`));
  return h("li", {}, ...parts);
}

// ---------------------------------------------------------------- wiring
form.addEventListener("submit", (event) => {
  event.preventDefault();
  const seed = Number(input.value.trim());
  if (!Number.isInteger(seed) || seed < 1 || seed > 999999) {
    setStatus("A seed is a whole number from 1 to 999999.", false, true);
    return;
  }
  lookUp(seed);
});
$("random-seed").addEventListener("click", () => lookUp(1 + Math.floor(Math.random() * 999999)));
for (const button of document.querySelectorAll("[data-seed]")) {
  button.addEventListener("click", () => lookUp(Number(button.dataset.seed)));
}

function fromAddress() {
  const match = /^#(\d{1,6})(?:\/(\d{1,2}))?$/.exec(location.hash);
  if (!match) return false;
  const seed = Number(match[1]);
  const square = match[2] === undefined ? null : Number(match[2]);
  if (seed < 1 || seed > 999999 || (square !== null && square > 24)) return false;
  lookUp(seed, square);
  return true;
}
renderFooter();
if (!fromAddress()) input.focus();
window.addEventListener("hashchange", () => {
  const match = /^#(\d{1,6})/.exec(location.hash);
  if (match && Number(match[1]) !== state.seed) fromAddress();
});
