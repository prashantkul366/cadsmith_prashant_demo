"use strict";
/* ═══════════════════════════════════════════════════════════════════════
   CADSmith — application logic.

   Every panel on screen is fed by the backend: the Design Plan is the
   Planner agent's JSON, the code is what the Coder wrote, the dimensions
   are measured by the OpenCASCADE kernel, and the verdict is the Opus
   Judge's.  Nothing is simulated, and progress is driven by events the
   pipeline actually emitted rather than by timers.
   ═══════════════════════════════════════════════════════════════════════ */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
// Escapes quotes too: this output is used inside attributes (data-prompt),
// where an unescaped quote would end the attribute early.
const esc = s => String(s ?? "").replace(/&/g, "&amp;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const fmt = n => (n === null || n === undefined || Number.isNaN(n)) ? "—"
  : (Number.isInteger(n) ? String(n) : (Math.round(n * 100) / 100).toString());

const S = {
  jobId: null,
  versions: [],      // one entry per pipeline iteration or applied edit
  selected: -1,
  health: null,
  busy: false,
  stream: null,
  designPlan: null,
  converged: false,
  replay: false,
  seq: 0,          // next unseen event sequence number
  providers: [],
  provider: null,
  efforts: [],        // reasoning levels the picker offers, from the server
  effortDefault: "",  // the level it selects until someone chooses another
  editing: false,
  examples: [],    // kept so a language change can redraw them translated
  catalog: null,   // set when a standard part answered instead of the agents
  usage: null,     // per-agent token counters, rebuilt from the events
  spend: null,     // the server's own spend summary, ceiling included
  stage: null,     // {key, detail} - the pipeline strip, redrawn from state
  codeLines: undefined,
  paramView: "params",  // which view of the script the code panel is showing
  params: [],         // the server's descriptors for the selected version
  paramDraft: {},     // name -> the value its control is holding right now
  paramBase: null,    // the version those descriptors were read from
  paramCode: "",      // and that version's source, which the drafts patch
  paramBusy: false,   // a rebuild is in flight; the controls are read-only
  paramLoading: false,  // the source and its descriptors are still arriving
  editFromPanel: false,
};

/* ── the five stages shown while a run is in flight ─────────────────── */
/* Keys, not labels: the strip is redrawn on a language change, and it is
   redrawn from S.stage rather than from the DOM. */
const STAGES = [
  { key: "plan",    label: "stage.plan" },
  { key: "code",    label: "stage.code" },
  { key: "execute", label: "stage.execute" },
  { key: "judge",   label: "stage.judge" },
  { key: "done",    label: "stage.done" },
];

/* ═══════════════════════ helpers ═══════════════════════ */

let toastTimer;
function toast(message, icon) {
  const el = $("#toast");
  el.innerHTML = (icon ||
    `<svg class="icn" viewBox="0 0 24 24" style="color:var(--valid)"><path d="M20 6 9 17l-5-5"/></svg>`)
    + `<span>${esc(message)}</span>`;
  el.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("on"), 2600);
}

function warnToast(message) {
  toast(message, `<svg class="icn" viewBox="0 0 24 24" style="color:var(--warn)"><path d="M12 8v5M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>`);
}

/* One pass over the raw source, escaping each segment as it is emitted.
   Chained .replace() calls cannot be used here: the first pass injects
   markup, and a later pass then matches inside it - the string rule would
   see the class="c" of a comment span and wrap it, corrupting the output. */
const PY_TOKENS = new RegExp([
  /(#[^\n]*)/,                                   // comment
  /("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')/,     // string
  /\b(import|from|as|def|for|in|return|if|else|not|and|or|None|True|False|lambda|while|range)\b/,
  /\b(\d+\.?\d*)\b/,                              // number
  /\.([A-Za-z_]\w*)(?=\s*\()/,                    // method call
].map(r => r.source).join("|"), "g");

function highlight(code) {
  const CLASSES = ["c", "s", "k", "n", "f"];
  let out = "", last = 0, match;
  PY_TOKENS.lastIndex = 0;
  while ((match = PY_TOKENS.exec(code)) !== null) {
    out += esc(code.slice(last, match.index));
    const group = CLASSES.findIndex((_, i) => match[i + 1] !== undefined);
    const text = match[group + 1];
    // The method-call rule captures the name but matches the leading dot too.
    if (CLASSES[group] === "f") out += ".";
    out += `<span class="${CLASSES[group]}">${esc(text)}</span>`;
    last = match.index + match[0].length;
  }
  return out + esc(code.slice(last));
}

function setCode(code, highlightKeys) {
  let html = highlight(code || "");
  (highlightKeys || []).forEach(key => {
    html = html.replace(
      new RegExp(`(^|\\n)(\\s*${key}\\s*=[^\\n]*)`, "g"),
      (_m, lead, line) => `${lead}<span class="hot">${line}</span>`);
  });
  $("#hl").innerHTML = html + "\n";
  S.codeLines = code ? code.split("\n").length : 0;
  $("#codeStat").textContent = S.codeLines
    ? t("code.stat", { n: S.codeLines }) : t("code.empty");
}

/* ═══════════════════════ health ═══════════════════════ */

async function loadHealth() {
  const chip = $("#healthChip");
  try {
    S.health = await API.health();
  } catch (_) {
    chip.className = "health bad";
    chip.querySelector("span").textContent = t("health.unreachable");
    return;
  }

  const checks = S.health.checks;
  const canGenerate = S.health.can_generate;
  chip.className = "health " + (S.health.ok ? "ok" : (canGenerate ? "warn" : "bad"));
  chip.querySelector("span").textContent =
    S.health.ok ? t("health.ready")
    : canGenerate ? t("health.degraded") : t("health.notready");

  renderDiagRows(checks);

  if (!checks.model_backend.ok) {
    $("#keyBanner").hidden = false;
    // A standard part still works with no backend at all, and saying so is
    // the difference between the two paths made visible.
    $("#keyBannerText").textContent =
      t(checks.catalog && checks.catalog.ok ? "banner.catalog"
                                            : "banner.nobackend");
  } else {
    $("#keyBanner").hidden = true;
  }
  if (!checks.vision_render.ok) {
    const toggle = $("#optVision");
    toggle.classList.remove("on");
    toggle.setAttribute("aria-checked", "false");
    toggle.style.opacity = ".45";
    toggle.style.pointerEvents = "none";
  }
}

/* The check names are translated; the details are not. They quote what the
   machine reported - a version string, a path, a library's own message - and
   quoting is not translating.

   The catalogue is the exception, because its detail is not a quote: the
   server counts the families and names the missing libraries, and the
   sentence around those facts is ours. So the server sends the facts and
   this composes the sentence, which means a Japanese reader gets Japanese
   rather than our English. */
function catalogDetail(check) {
  if (typeof check.families !== "number") return check.detail;
  let text = t("diag.catalog.families", { n: check.families });
  if (check.live && check.live.length) text += ` (${check.live.join(", ")})`;
  if (check.missing && check.missing.length) {
    text += " - " + t("diag.catalog.missing", { names: check.missing.join(", ") });
  }
  return text;
}

/* Each check names its own outcome, so a sentence the server wrote can be
   said in the reader's language instead. A check with no name, or one this
   dictionary has no phrasing for, falls back to the English the server
   sent - which for most of them is the right answer anyway, because it is a
   quote: a version string, a path, a library's own error. */
function checkDetail(name, check) {
  if (name === "catalog") return catalogDetail(check);
  const key = check.code ? `diag.${name}.${check.code}` : null;
  return key && I18N.has(key) ? t(key, check.data || {}) : check.detail;
}

function renderDiagRows(checks) {
  $("#diagRows").innerHTML = Object.entries(checks).map(([name, check]) => `
    <div class="drow">
      <span class="dot ${check.ok ? "ok" : "bad"}"></span>
      <b>${esc(I18N.has("diag." + name) ? t("diag." + name)
                                        : name.replace(/_/g, " "))}</b>
      <span>${esc(checkDetail(name, check))}</span>
    </div>`).join("");
}

/* ═══════════════════════ examples ═══════════════════════ */

async function loadExamples() {
  try { S.examples = await API.examples(); } catch (_) { return; }
  renderExamples();
}

/* The Japanese prompt is what actually gets sent, not a caption over an
   English one: someone who presses a sample has to be able to read the
   request the pipeline receives. Every dimension and axis is carried across
   unchanged, so the part built from either language is the same part. */
function samplePrompt(example) {
  const key = "sample." + example.id;
  return I18N.has(key) ? t(key) : example.prompt;
}

function renderExamples() {
  $("#samples").innerHTML = (S.examples || []).map(e => {
    const prompt = samplePrompt(e);
    const tier = String(e.tier || "").toLowerCase() === "demo"
      ? t("tier.demo") : String(e.tier || "").toUpperCase();
    return `
    <button class="sample" data-prompt="${esc(prompt)}">
      <b>${esc(e.id.toUpperCase())} · ${esc(tier)}</b>
      <small>${esc(prompt.length > 120 ? prompt.slice(0, 120) + "…" : prompt)}</small>
    </button>`;
  }).join("");
  $$("#samples .sample").forEach(button => {
    button.onclick = () => {
      $("#prompt").value = button.dataset.prompt;
      $("#prompt").focus();
    };
  });
}

/* ═══════════════════════ pipeline progress ═══════════════════════ */

function renderStages(activeKey, detail) {
  S.stage = { key: activeKey, detail: detail || "" };
  const activeIndex = STAGES.findIndex(s => s.key === activeKey);
  $("#pipe").innerHTML = STAGES.map((stage, i) => {
    const state = i < activeIndex ? "done" : (i === activeIndex ? "act" : "");
    return `
      <div class="pstep ${state}">
        <div class="pbullet">
          <svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg><i class="pspin"></i>
        </div>
        <div>
          <div class="plabel">${esc(t(stage.label))}</div>
          ${i === activeIndex && detail
            ? `<div class="pdetail">${esc(detail)}</div>` : ""}
        </div>
      </div>${i < STAGES.length - 1 ? '<div class="pline"></div>' : ""}`;
  }).join("");
}

function appendLog(line) {
  const log = $("#plog");
  const row = document.createElement("div");
  row.textContent = line;
  log.appendChild(row);
  while (log.childElementCount > 60) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

function showOverlay(which) {
  $("#ovEmpty").hidden = which !== "empty";
  $("#ovPipe").hidden = which !== "pipe";
  $("#ovErr").hidden = which !== "error";
  // The properties used to float on the model and had to be got out of
  // the way of an overlay. They are a card now, and a card does not
  // cover anything.
  if (which !== "none") showCard("props", false);
}

/* ═══════════════════════ event handling ═══════════════════════ */

const PHASE_STAGE = {
  plan: "plan", code: "code", execute: "execute", error_fix: "execute",
  render: "judge", judge: "judge", refine: "code",
};

/* ══════════ Reasoning panel ══════════
   One collapsible block per agent run, keyed by agent + iteration so the five
   refinement rounds stay distinguishable. Reasoning and output stream into
   separate lanes; a finished block folds itself away. */

/* Keys again. The label and the caption are separate because Japanese puts
   the qualifier in front - "writing CadQuery" is 「CadQuery を記述中」 - so
   the pair cannot be assembled from an English word order. */
const AGENT_KEYS = ["plan", "code", "error_fix", "judge", "refine"];

/* ── what the run spent ──────────────────────────────────────────────
   Each agent event carries autofab's *cumulative* counters, so the cost of
   one call is the step between consecutive events. That is what makes a
   per-agent breakdown possible at all: the job record only holds the total. */

const AGENT_IDS = {
  plan: "planner", code: "coder", error_fix: "errorfix",
  judge: "judge", refine: "refiner",
};
const AGENT_ORDER = ["planner", "coder", "errorfix", "judge", "refiner"];
const agentLabel = id => I18N.has("agent." + id) ? t("agent." + id) : id;
const compact = n => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

function resetUsage() {
  S.usage = { seen: { input: 0, output: 0, calls: 0 }, byAgent: {} };
  S.spend = null;
  const strip = $("#usage");
  if (strip) { strip.hidden = true; strip.innerHTML = ""; }
}

function noteUsage(phase, tokens) {
  if (!tokens || !S.usage) return;
  const input = tokens.input_tokens || 0;
  const output = tokens.output_tokens || 0;
  const calls = tokens.calls || 0;
  const seen = S.usage.seen;

  // Cumulative counters only ever climb; a drop means the run restarted, so
  // rebase rather than recording a negative.
  const step = {
    input: Math.max(0, input - seen.input),
    output: Math.max(0, output - seen.output),
    calls: Math.max(0, calls - seen.calls),
  };
  S.usage.seen = { input, output, calls };

  const name = AGENT_IDS[phase] || phase;
  const entry = S.usage.byAgent[name] || { input: 0, output: 0, calls: 0 };
  entry.input += step.input;
  entry.output += step.output;
  entry.calls += step.calls;
  S.usage.byAgent[name] = entry;
  renderUsage();
}

function renderUsage() {
  const strip = $("#usage");
  if (!strip || !S.usage) return;
  const { seen, byAgent } = S.usage;
  const total = seen.input + seen.output;
  if (!total) {
    // A catalogue part costs nothing, and saying so is the point - it is the
    // difference between the two paths made visible.
    if (S.catalog) {
      showCard("tokens", true);
      strip.innerHTML = `<div class="tilenote unone">${esc(t("usage.free"))}</div>`;
    } else {
      showCard("tokens", false);
    }
    return;
  }

  const parts = AGENT_ORDER
    .filter(name => byAgent[name] && (byAgent[name].input + byAgent[name].output))
    .map(name => {
      const a = byAgent[name];
      return `<div class="tile"><b>${compact(a.input + a.output)}</b>`
           + `<span>${esc(agentLabel(name))}${a.calls > 1 ? ` ×${a.calls}` : ""}</span></div>`;
    });

  // On a metered backend the useful number is not just what this run spent
  // but how close it came to the ceiling that stops it, so show both once
  // the run is a meaningful way through its allowance.
  const cap = S.spend && S.spend.budget;
  const share = cap ? total / cap : 0;
  const budgetNote = share > 0.25
    ? `<span class="ubudget${share > 0.8 ? " near" : ""}">`
      + `${esc(t("usage.budget", { pct: Math.round(share * 100),
                                   cap: compact(cap) }))}</span>`
    : "";
  const costNote = S.spend && S.spend.estimated_cost !== undefined
    ? `<span class="ucost">≈ $${S.spend.estimated_cost.toFixed(4)}</span>` : "";

  // Four totals and one tile per agent, which is the breakdown the app has
  // always computed and never shown as anything but a line of text.
  const totals = [
    [t("usage.tok"), total.toLocaleString()],
    [t("usage.in"), seen.input.toLocaleString()],
    [t("usage.out"), seen.output.toLocaleString()],
    [t("usage.callst"), String(seen.calls)],
  ].map(([label, value]) =>
    `<div class="tile"><b>${esc(value)}</b><span>${esc(label)}</span></div>`);

  showCard("tokens", true);
  strip.innerHTML = totals.join("") + parts.join("")
    + (costNote || budgetNote
        ? `<div class="tilenote">${costNote}${budgetNote}</div>` : "");
}

const TH = { blocks: new Map(), order: 0 };

function thinkReset() {
  TH.blocks.clear();
  TH.order = 0;
  $("#thinkBody").innerHTML = "";
  $("#thinkLive").hidden = true;
}

function thinkKey(agent, iteration) { return `${agent}#${iteration || 0}`; }

function thinkBlock(agent, iteration) {
  const key = thinkKey(agent, iteration);
  let block = TH.blocks.get(key);
  if (block) return block;

  const known = AGENT_KEYS.includes(agent);
  const label = known ? t(`think.${agent}`) : agent;
  const sub = known ? t(`think.${agent}.sub`) : "";
  const el = document.createElement("details");
  el.className = "tblock";
  el.open = true;
  el.dataset.state = "run";
  el.innerHTML = `
    <summary>
      <svg class="tcar" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.5"><path d="M9 6l6 6-6 6"/></svg>
      <b></b><span class="tsub"></span><span class="tms"></span>
    </summary>
    <div class="tstream"></div>`;
  el.querySelector("b").textContent = label;
  el.querySelector(".tsub").textContent =
    iteration ? `${sub} · iteration ${iteration}` : sub;

  const body = $("#thinkBody");
  if (!TH.order) body.innerHTML = "";
  body.appendChild(el);
  TH.order += 1;

  block = { el, stream: el.querySelector(".tstream"), started: Date.now(),
            lanes: {} };
  TH.blocks.set(key, block);
  return block;
}

function thinkAppend(agent, iteration, lane, text) {
  if (!text) return;
  const block = thinkBlock(agent, iteration);
  let node = block.lanes[lane];
  if (!node) {
    node = document.createElement("div");
    node.className = lane === "thinking" ? "tthink" : "ttext";
    block.stream.appendChild(node);
    block.lanes[lane] = node;
  }
  node.textContent += text;

  // Follow the stream only while the reader is already at the bottom, so
  // scrolling back to read something is not yanked away.
  const body = $("#thinkBody");
  const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 60;
  if (atBottom) body.scrollTop = body.scrollHeight;
  $("#thinkLive").hidden = false;
}

function thinkFinish(agent, iteration, ok, ms) {
  const block = TH.blocks.get(thinkKey(agent, iteration));
  if (!block) return;
  block.el.dataset.state = ok ? "done" : "fail";
  const elapsed = ms != null ? ms : Date.now() - block.started;
  block.el.querySelector(".tms").textContent = `${(elapsed / 1000).toFixed(1)}s`;
  // Fold finished steps away, the way a completed thought collapses.
  if (ok) block.el.open = false;
}

function thinkIdle() { $("#thinkLive").hidden = true; }

function handleEvent(event) {
  const { phase, status, message, data } = event;
  S.seq = Math.max(S.seq, event.seq + 1);

  if (S.editing) { handleEditEvent(event); return; }

  if (phase === "log") { appendLog(message); return; }

  if (phase === "catalog") {
    if (data && data.part_id) {
      S.catalog = data;
      const label = t("label.catalog",
                      { backend: String(data.backend || "").toUpperCase() });
      $("#genModelLabel").textContent = label;
      $("#judgeModelLabel").textContent = label;
      renderStages("code", t("detail.fromcatalog"));
      renderPlan(null);
    }
    appendLog(message);
    return;
  }

  if (phase === "thinking") {
    thinkAppend(data.agent || "code", data.iteration || 0,
                data.stream === "thinking" ? "thinking" : "text", message);
    return;
  }

  // A step that produced reasoning is finished when its own phase resolves.
  if (AGENT_KEYS.includes(phase) && (status === "ok" || status === "failed")) {
    thinkFinish(phase, data.iteration || 0, status === "ok", data.ms);
  }

  // Cumulative counters ride on every agent event, so the strip fills in as
  // the run goes rather than only at the end.
  if (data && data.tokens) noteUsage(phase, data.tokens);
  if (data && data.spend) { S.spend = data.spend; renderUsage(); }

  const stage = PHASE_STAGE[phase];
  if (stage) {
    let detail = "";
    if (phase === "ground") detail = t("detail.grounded");
    if (phase === "plan" && status === "started") detail = t("detail.decompose");
    if (phase === "code" && status === "started") detail = t("detail.apidocs");
    if (phase === "code" && status === "ok") detail = t("detail.lines", { n: data.lines });
    if (phase === "execute" && status === "started") detail = t("detail.kernel");
    if (phase === "execute" && status === "failed") detail = t("detail.execfail");
    if (phase === "error_fix" && status === "started") detail = t("detail.errorfix");
    if (phase === "render" && status === "ok") detail = t("detail.render");
    if (phase === "judge" && status === "started") detail = t("detail.judging");
    if (phase === "refine" && status === "started") detail = t("detail.refining");
    renderStages(stage, detail);
  }

  if (phase === "plan" && status === "ok") {
    S.designPlan = data.design_plan;
    renderPlan(data.design_plan);
  }
  if ((phase === "code" || phase === "refine" || phase === "error_fix")
      && status === "ok") {
    setCode(data.code);
  }
  if (phase === "version" && status === "ok") {
    addVersion(data);
  }
  if (phase === "job") {
    if (status === "started" && data.llm) {
      setModelLabels(data.llm.generation_model, data.llm.judge_model);
    }
    if (status === "ok") finishRun(data);
    if (status === "failed") failRun(message);
  }
}

/* ═══════════════════════ versions ═══════════════════════ */

/* ── the four cards on the right ─────────────────────────────────────
   Each shuts away on its own. Which one matters depends on what you are
   doing: checking a dimension does not need the token bill on screen, and
   watching the spend does not need the verdict. What is shut is remembered,
   because it is a preference about how you work rather than about this run. */

const CARD_KEY = "cadsmith.cards";

function cardState() {
  try { return JSON.parse(localStorage.getItem(CARD_KEY) || "{}"); }
  catch (e) { return {}; }
}

function setCardOpen(name, open) {
  const card = document.querySelector(`.rcard[data-card="${name}"]`);
  if (!card) return;
  card.classList.toggle("shut", !open);
  card.querySelector("[data-card-toggle]").setAttribute("aria-expanded", String(open));
  try {
    const state = cardState();
    state[name] = open;
    localStorage.setItem(CARD_KEY, JSON.stringify(state));
  } catch (e) { /* a private window has no storage; the card still works */ }
}

//: Present or absent, which is not the same as open or shut. A card with
//: nothing in it yet should not be a row of empty tiles.
function showCard(name, present) {
  const card = document.querySelector(`.rcard[data-card="${name}"]`);
  if (card) card.hidden = !present;
}

$$(".rcard [data-card-toggle]").forEach(button => {
  const card = button.closest(".rcard");
  button.onclick = () => setCardOpen(card.dataset.card,
                                     card.classList.contains("shut"));
});

(function restoreCards() {
  const state = cardState();
  $$(".rcard").forEach(card => {
    if (state[card.dataset.card] === false) setCardOpen(card.dataset.card, false);
  });
})();

/* ── the thread ──────────────────────────────────────────────────────── */

function showAsk(text) {
  $("#askTurn").hidden = !text;
  $("#askText").textContent = text || "";
  // The starting prompts are an empty state. Once there is a conversation
  // they are clutter in the middle of it.
  $("#samplesField").hidden = Boolean(text);
}

function showVersionPill() {
  const pill = $("#verPill");
  const version = S.versions[S.selected];
  if (!version) { pill.hidden = true; return; }
  pill.hidden = false;
  pill.textContent = version.source === "catalog"
    ? t("iter.catalog")
    : t(version.source === "edit" ? "iter.edit" : "iter.iteration",
        { n: version.iteration });
}

function addVersion(version) {
  const existing = S.versions.findIndex(v => v.iteration === version.iteration);
  if (existing >= 0) S.versions[existing] = version;
  else S.versions.push(version);
  renderIterations();
  selectVersion(S.versions.length - 1, { quiet: true });
  showVersionPill();
  refreshComposer();
}

function renderIterations() {
  if (!S.versions.length) { $("#iters").innerHTML = ""; return; }
  const cards = S.versions.map((v, i) => {
    const kind = v.source === "edit" ? "edit"
               : v.source === "catalog" ? "catalog"
               : (v.passed ? "pass" : "fail");
    const label = v.source === "catalog" ? t("iter.catalog")
      : t(v.source === "edit" ? "iter.edit" : "iter.iteration",
          { n: v.iteration });
    const thumb = v.has_render
      ? `<img src="${API.artifact(S.jobId, v.iteration, "render.png")}" alt="" />`
      : "";
    return `<div class="iter ${i === S.selected ? "sel" : ""}" data-i="${i}">
        ${thumb}
        <div class="ilabel"><i class="${kind}"></i>${label}</div>
      </div>`;
  }).join("");
  const hint = S.versions.length > 1
    ? `<span class="ihint">${esc(t("iter.compare", { n: S.versions.length }))}</span>` : "";
  $("#iters").innerHTML = cards + hint;
  $$("#iters .iter").forEach(card => {
    card.onclick = () => selectVersion(+card.dataset.i);
  });
}

async function selectVersion(index, options) {
  const version = S.versions[index];
  if (!version) return;
  S.selected = index;
  renderIterations();

  // Started before the mesh rather than after it. The panel does not depend
  // on the geometry, and a heavy STL - a swept helix runs to megabytes -
  // otherwise holds the controls back for seconds while the part is already
  // on screen, which reads as the panel having nothing to show.
  const controls = loadParameters(version.iteration);

  try {
    const box = await Viewer.load(
      API.artifact(S.jobId, version.iteration, "model.stl"));
    if (!options || !options.quiet) Viewer.fit(true);
    else Viewer.fit(false);
    showOverlay("none");
    showCard("props", true);
  } catch (error) {
    warnToast(error.message);
  }

  await controls;

  renderKernelFacts(version);
  renderValidation(version);
  sheetSvg = null;
  $("#drawBtn").disabled = false;
  // A parameter patch is rebuilt by the kernel with no model call, so editing
  // stays available without an API key; the agent path reports its own need.
  const canRebuild = !!(S.health && S.health.checks
                        && S.health.checks.cadquery.ok);
  setComposerEnabled(canRebuild);
}

/* ═══════════════════════ panels ═══════════════════════ */

function renderPlan(plan) {
  // A catalogue part has no plan: its dimensions come from the standard.
  if (S.catalog) {
    $("#planBody").innerHTML =
      `<div class="await">${esc(t("plan.catalog"))}</div>`;
    return;
  }
  if (!plan) return;
  const dimensions = (plan.dimensions && plan.dimensions.key_dimensions) || {};
  const bbox = (plan.dimensions && plan.dimensions.overall_bbox) || {};
  const constraints = plan.constraints || {};

  const rows = Object.entries(dimensions).map(([key, value]) => `
    <div class="dim" data-k="${esc(key)}">
      <span>${esc(key.replace(/_/g, " "))}</span>
      <b>${fmt(value)}<u>mm</u></b>
    </div>`).join("");

  const constraintTags = Object.entries(constraints)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `<span class="tag">${esc(k.replace(/_/g, " "))}: ${esc(fmt(v))}</span>`)
    .join("");

  $("#planBody").innerHTML = `
    <div class="plan-desc">${esc(plan.description || "")}</div>
    ${(plan.components || []).length ? `<div class="plan-tags">${
      plan.components.map(c => `<span class="tag">${esc(c)}</span>`).join("")
    }</div>` : ""}
    ${rows ? `<div class="eyebrow" style="margin-bottom:6px">${
      esc(t("plan.dimensions"))}</div>${rows}` : ""}
    ${bbox.xlen ? `<div class="dim"><span>${esc(t("plan.bbox"))}</span><b>${
      fmt(bbox.xlen)} × ${fmt(bbox.ylen)} × ${fmt(bbox.zlen)}<u>mm</u></b></div>` : ""}
    ${constraintTags ? `<div class="eyebrow" style="margin:12px 0 6px">${
      esc(t("plan.constraints"))}</div>
      <div class="plan-tags">${constraintTags}</div>` : ""}`;
}

function renderKernelFacts(version) {
  const geometry = version.geometry || {};
  const bbox = geometry.bounding_box || {};
  $("#mtitle").textContent =
    version.source === "catalog" ? t("facts.standard")
    : version.source === "edit" ? t("facts.updated")
    : t(version.passed ? "facts.validated" : "facts.unvalidated");
  const tiles = [
    [t("facts.bbox"), `${fmt(bbox.xlen)}×${fmt(bbox.ylen)}×${fmt(bbox.zlen)}`],
    [t("facts.volume"), fmt(Math.round(geometry.volume || 0))],
    [t("facts.faces"), geometry.num_faces],
    [t("facts.edges"), geometry.num_edges],
    // A part that is not watertight is not a part, so this tile carries the
    // warning rather than reading like another number.
    [t("facts.solid"), t(geometry.is_valid ? "facts.watertight" : "facts.invalid"),
     geometry.is_valid ? "" : "warn"],
  ];
  $("#mfacts").innerHTML = tiles.map(([label, value, tone]) =>
    `<div class="tile ${tone || ""}"><b>${esc(String(value ?? "—"))}</b>`
    + `<span>${esc(label)}</span></div>`
  ).join("");
  showCard("props", true);
}

function specLabel(check) {
  const advisory = check.hard === false;
  const key = "spec." + check.key + (advisory ? ".advisory" : "");
  if (I18N.has(key)) return t(key);
  if (I18N.has("spec." + check.key)) return t("spec." + check.key);
  return check.label;
}

function specRows(spec) {
  // The measured checks, shown whether they passed or not: the point of this
  // panel is that a number was read off the solid, not asserted about it.
  if (!spec || spec.error || !spec.checks || !spec.checks.length) return "";
  const rows = spec.checks.map((c) => {
    const state = c.passed ? "ok" : (c.hard ? "bad" : "soft");
    const mark = c.passed ? "&#10003;" : (c.hard ? "&#10007;" : "&#8210;");
    return `<div class="specrow ${state}">
      <span class="specmark">${mark}</span>
      <span class="speclabel">${esc(specLabel(c))}</span>
      <span class="specval">${esc(c.actual)}</span>
      <span class="specwant">${esc(t("spec.wanted", { expected: c.expected }))}</span>
    </div>`;
  }).join("");
  return `<div class="eyebrow" style="margin:14px 0 6px">${esc(t("spec.heading"))}</div>
    <div class="specgrid">${rows}</div>`;
}

function renderValidation(version) {
  const passed = version.passed;
  const renderUrl = version.has_render
    ? API.artifact(S.jobId, version.iteration, "render.png") : null;

  // A parameter patch is confirmed by the kernel alone - the Judge is not
  // re-run for it. Saying "accepted by the Judge" there would credit a check
  // that never happened, so the two cases are worded differently.
  const judged = version.judge_passed !== null
                 && version.judge_passed !== undefined;

  const spec = version.spec || null;
  const specFailed = spec && spec.ok === false;

  let heading, body, attribution;
  if (judged) {
    if (specFailed) {
      // A measurement outranks an opinion about the same quantity, so it
      // leads whatever the Judge concluded. Crediting the Judge for a
      // rejection the kernel can prove would also contradict the rows below,
      // which name the measurement that failed.
      const failed = (spec.checks || []).filter(c => !c.passed && c.hard);
      const named = failed.map(c => t("val.refused.item", {
        label: specLabel(c), actual: c.actual, expected: c.expected })).join("; ");
      heading = t("val.refused");
      body = t(version.judge_passed ? "val.refused.judgepassed"
                                    : "val.refused.measured")
        + named + t("val.refused.tail")
        + (version.judge_passed || !version.judge_feedback ? ""
           : t("val.refused.judgetoo", { feedback: version.judge_feedback }));
    } else {
      heading = t(passed ? "val.accepted" : "val.rejected");
      // The Judge's own words, which are model output and stay as written.
      body = version.judge_feedback || version.feedback_text || "";
    }
    const judgeModel = (S.judgeModel || "").toUpperCase() || t("val.src.judge");
    attribution = judgeModel + " · " + t(version.has_render
      ? "val.src.render" : "val.src.metrics");
  } else if (version.source === "catalog") {
    // No agent produced this, so there is nothing for a Judge to have
    // accepted. Say where it came from instead of implying a verdict.
    const cat = version.catalog || {};
    heading = t("val.catalog.heading");
    body = t("val.catalog.body", {
      title: cat.title || t("val.catalog.thispart"),
      standard: cat.standard || t("val.catalog.itsstandard") });
    attribution = t("val.src.catalog", {
      backend: String(cat.backend || "cadsmith").toUpperCase() });
  } else {
    heading = t(passed ? "val.rebuilt" : "val.rebuilt.failed");
    body = passed ? t("val.rebuilt.body")
                  : (version.feedback_text || t("val.rebuilt.body.failed"));
    attribution = t("val.src.kernel");
  }

  $("#valBody").innerHTML = `
    <div class="verdict ${passed ? "pass" : "fail"}">
      <svg class="vi" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${passed ? '<path d="M20 6 9 17l-5-5"/>'
                 : '<path d="M12 8v5M12 17h.01"/><circle cx="12" cy="12" r="9"/>'}
      </svg>
      <div>
        <b>${esc(heading)}</b>
        <p>${esc(body)}</p>
        <div class="judge-src">${esc(attribution)}</div>
      </div>
    </div>
    ${specRows(spec)}
    ${renderUrl ? `
      <div class="eyebrow" style="margin-bottom:6px">${esc(t("val.sawheading"))}</div>
      <img class="rthumb" id="rthumb" src="${renderUrl}" alt="${esc(t("val.renderalt"))}" />
      <div class="rcap">${esc(t("val.sawcaption"))}</div>` : ""}`;

  const thumb = $("#rthumb");
  if (thumb) {
    thumb.onclick = () => {
      $("#lightboxImg").src = renderUrl;
      $("#lightbox").hidden = false;
    };
  }
}

/* ═══════════════════════ run lifecycle ═══════════════════════ */

/* ── one composer ────────────────────────────────────────────────────
   There was a box on the left to describe a part and a second box across
   the foot of the app to change one. Two inputs for what is, to the person
   typing, the same act: say what you want. The composer decides which it
   is from whether there is a part on screen, so nobody has to learn the
   difference between describing and editing. */

function setComposerEnabled(on) {
  $("#prompt").disabled = !on;
  $("#genBtn").disabled = !on;
}

//: True once there is something to change, which is what makes this an edit.
function editing() {
  return Boolean(S.jobId) && S.versions.length > 0 && !S.busy;
}

function submitComposer() {
  if (S.busy) return;
  if (editing()) applyEdit();
  else generate();
}

/* The placeholder is the only thing that says which of the two will happen,
   so it changes rather than staying a compromise between them. */
function refreshComposer() {
  const box = $("#prompt");
  const key = editing() ? "edit.placeholder" : "input.placeholder";
  box.placeholder = t(key);
  box.setAttribute("data-i18n-ph", key);
  $("#genBtn").title = t(editing() ? "edit.apply" : "input.generate");
}

$("#prompt").addEventListener("keydown", event => {
  // Enter sends. A part description is a sentence, not a document, and
  // shift-Enter is there for the rare one that wants two lines.
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitComposer();
  }
});

/* ── the settings behind the kebab ───────────────────────────────────── */

function closeMore() {
  $("#moreMenu").hidden = true;
  $("#moreBtn").setAttribute("aria-expanded", "false");
}
function toggleMore(event) {
  if (event) event.stopPropagation();
  const open = $("#moreMenu").hidden;
  $("#moreMenu").hidden = !open;
  $("#moreBtn").setAttribute("aria-expanded", String(open));
}
$("#moreBtn").onclick = toggleMore;
$("#modelChip").onclick = toggleMore;
document.addEventListener("click", event => {
  if (!event.target.closest("#moreMenu") && !event.target.closest("#moreBtn")
      && !event.target.closest("#modelChip")) closeMore();
});

async function generate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) { warnToast(t("run.needprompt")); return; }
  if (S.busy) return;

  S.busy = true;
  S.runStarted = Date.now();
  showAsk(prompt);
  $("#prompt").value = "";
  $("#verPill").hidden = true;
  setThinkOpen(false);
  S.versions = [];
  S.selected = -1;
  S.designPlan = null;
  S.converged = false;
  S.replay = false;
  resetPill();
  $("#genBtn").disabled = true;
  $("#iters").innerHTML = "";
  $("#plog").innerHTML = "";
  Viewer.clear();
  thinkReset();
  resetUsage();
  S.catalog = null;
  Viewer.building = true;     // slow orbit while the pipeline works
  setCode("");
  paramsReset();
  // Everything on the right belongs to the run that is being replaced, so
  // clear it now rather than leaving the previous part's plan and verdict on
  // screen until the new ones arrive.
  $("#planBody").innerHTML = `<div class="await">${esc(t("plan.planning"))}</div>`;
  $("#valBody").innerHTML = `<div class="await">${esc(t("val.waiting"))}</div>`;
  sheetSvg = null;
  $("#drawBtn").disabled = true;
  setComposerEnabled(false);
  showOverlay("pipe");
  renderStages("plan", t("detail.sending"));

  const options = {
    max_iterations: +$("#optIters").value,
    use_vision: $("#optVision").classList.contains("on"),
    use_catalog: $("#optCatalog").classList.contains("on"),
    ground_dimensions: $("#optGround").classList.contains("on"),
    effort: $("#optEffort").value,
    provider: $("#optProvider").value,
    generation_model: $("#optGenModel").value.trim(),
    judge_model: $("#optJudgeModel").value.trim(),
  };

  try {
    const job = await API.createJob(prompt, options);
    S.jobId = job.id;
    S.seq = 0;
    follow(job.id, 0);
  } catch (error) {
    S.busy = false;
    $("#genBtn").disabled = false;
    failRun(error.message);
  }
}

function follow(jobId, fromSeq) {
  if (S.stream) S.stream.close();
  S.stream = API.stream(jobId, {
    fromSeq: fromSeq || 0,
    onEvent: handleEvent,
    onEnd: () => { S.stream = null; },
    onError: () => {
      S.busy = false;
      $("#genBtn").disabled = false;
      warnToast(t("run.lostconn"));
    },
  });
}

/* "worked for 1m 33s" - the disclosure's own summary, so the reasoning can
   stay shut and still say what it cost in time. */
function thinkSummary() {
  if (!S.runStarted) return;
  const seconds = Math.max(1, Math.round((Date.now() - S.runStarted) / 1000));
  const text = seconds >= 60
    ? `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`
    : `${seconds}s`;
  $("#thinkSummary").textContent = t("think.workedfor", { time: text });
}

function finishRun(data) {
  thinkSummary();
  refreshComposer();
  S.busy = false;
  Viewer.building = false;
  thinkIdle();
  S.converged = !!data.converged;
  $("#genBtn").disabled = !(S.health && S.health.can_generate);

  if (!S.versions.length) {
    failRun(t("run.nogeometry"));
    return;
  }

  selectVersion(S.versions.length - 1);
  const cost = data.tokens
    ? t("run.tokens", { n: (data.tokens.input_tokens
                            + data.tokens.output_tokens).toLocaleString() })
    : "";
  const seconds = data.total_ms
    ? t("run.seconds", { s: (data.total_ms / 1000).toFixed(1) }) : "";

  if (S.catalog) {
    toast(t("run.catalogdone", { title: S.catalog.title || "", seconds }));
  } else if (S.converged) {
    // Japanese has no plural agreement, so {s} resolves to nothing there.
    toast(t("run.converged", { n: data.iterations, seconds, cost,
                               s: data.iterations === 1 ? "" : "s" }));
  } else {
    warnToast(t("run.notconverged", { n: data.iterations }));
  }
  loadHistory();
}

/* A run that died on the model id is the one failure the browser can answer
   by itself: the provider said what it serves when the picker was filled, so
   name those rather than sending the reader off to look at a panel. Bedrock
   is where this bites - an account can list a model the runtime then refuses,
   and the id is long enough that nobody spots the difference by eye. */
function modelAdvice(message) {
  const text = String(message || "");
  if (!/not_found|does not exist|ValidationException|inference profile|invalid/i
        .test(text)) return "";
  const offered = (S.provider && S.provider.models) || [];
  const chosen = [$("#optGenModel").value.trim(), $("#optJudgeModel").value.trim()];
  // Only when the id really is not on offer. A 404 for another reason should
  // not be answered with a confident, wrong explanation.
  if (!offered.length || !chosen.some(m => m && offered.indexOf(m) < 0)) return "";
  const shortlist = offered.filter(m => /sonnet|opus|haiku/i.test(m)).slice(0, 3);
  return t("err.badmodel", {
    n: offered.length, names: (shortlist.length ? shortlist : offered.slice(0, 3)).join(", "),
  });
}

function failRun(message) {
  S.busy = false;
  Viewer.building = false;
  thinkIdle();
  $("#genBtn").disabled = !(S.health && S.health.can_generate);
  $("#errTitle").textContent = t("err.title");
  $("#errMsg").textContent = message || t("err.unknown");
  $("#errFix").textContent = modelAdvice(message) || t(S.versions.length
    ? "err.haveattempt" : "err.checkenv");
  $("#errKeep").hidden = !S.versions.length;
  showOverlay("error");
}

/* ═══════════════════════ history ═══════════════════════ */

async function loadHistory() {
  let jobs = [];
  try { jobs = await API.jobs(); } catch (_) { return; }

  $("#hlist").innerHTML = jobs.length ? jobs.map(job => {
    const when = job.created_at
      ? new Date(job.created_at * 1000).toLocaleString() : "";
    const badge = job.status === "error"
      ? `<span class="hbadge fail">${esc(t("hist.failed"))}</span>`
      : job.converged ? `<span class="hbadge pass">${esc(t("hist.converged"))}</span>`
      : `<span class="hbadge fail">${esc(t("hist.notconverged"))}</span>`;
    // Provenance is stated, never implied: a replay is a recording, and a
    // fixture had its agent replies scripted rather than generated.
    const origin =
      job.source === "replay"
        ? `<span class="hbadge replay">${esc(t("hist.replay"))}</span>`
      : job.source === "catalog"
        ? `<span class="hbadge catalog">${esc(t("hist.catalog"))}</span>`
      : job.source === "fixture"
        ? `<span class="hbadge fixture">${esc(t("hist.fixture"))}</span>`
      : "";
    return `
      <div class="hrow">
        <button class="hitem" data-job="${esc(job.id)}">
          <div class="hnote">${esc(job.prompt.slice(0, 88))}${job.prompt.length > 88 ? "…" : ""}</div>
          <div class="hmeta">
            ${badge}${origin}
            <span class="hbadge">${esc(t("hist.versions", { n: job.versions.length }))}</span>
            <span class="htime">${esc(when)}</span>
          </div>
        </button>
        <button class="hreplay" data-replay="${esc(job.id)}" title="${esc(t("hist.replaytip"))}">
          <svg viewBox="0 0 24 24"><path d="M6 4l13 8-13 8z"/></svg>
        </button>
      </div>`;
  }).join("") : `<div class="await" style="padding:14px">${esc(t("hist.empty"))}</div>`;

  $$("#hlist .hitem").forEach(item => {
    item.onclick = () => openJob(item.dataset.job);
  });
  $$("#hlist .hreplay").forEach(item => {
    item.onclick = () => startReplay(item.dataset.replay);
  });
}

async function openJob(jobId) {
  let state;
  try { state = await API.job(jobId); }
  catch (error) { warnToast(error.message); return; }

  const job = state.job;
  S.replay = job.source === "replay";
  if (S.replay) {
    setPill(t("hist.replaypill"));
  } else {
    resetPill();
  }
  S.jobId = job.id;
  S.versions = job.versions || [];
  S.selected = -1;
  S.designPlan = job.design_plan;
  S.converged = job.converged;
  S.busy = false;

  $("#prompt").value = job.prompt;
  S.seq = (state.events || []).length;
  $("#plog").innerHTML = "";
  (state.events || [])
    .filter(e => e.phase === "log")
    .forEach(e => appendLog(e.message));

  const started = (state.events || []).find(
    e => e.phase === "job" && e.status === "started" && e.data && e.data.llm);
  if (started) {
    setModelLabels(started.data.llm.generation_model,
                   started.data.llm.judge_model);
  }

  renderPlan(job.design_plan);
  renderIterations();
  $("#hist").classList.remove("open");

  if (S.versions.length) {
    await selectVersion(S.versions.length - 1);
    toast(t(job.converged ? "hist.loaded.converged" : "hist.loaded.unconverged"));
  } else {
    showOverlay("error");
    $("#errTitle").textContent = t("hist.nogeometry");
    $("#errMsg").textContent = job.error || t("hist.stoppedearly");
    $("#errFix").textContent = "";
  }
}

/* ═══════════════════════ wiring ═══════════════════════ */

$("#genBtn").onclick = submitComposer;
$("#prompt").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate();
});

$("#optIters").oninput = e => { $("#optItersOut").value = e.target.value; };
for (const id of ["#optVision", "#optCatalog", "#optGround"]) {
  $(id).onclick = () => {
    const on = $(id).classList.toggle("on");
    $(id).setAttribute("aria-checked", String(on));
  };
}

$("#healthChip").onclick = () => {
  const panel = $("#diag");
  panel.hidden = !panel.hidden;
};
document.addEventListener("click", e => {
  if (!$("#diag").hidden && !$("#diag").contains(e.target)
      && e.target.closest("#healthChip") === null) {
    $("#diag").hidden = true;
  }
});

/* ISO, FRONT, TOP and RIGHT are the gizmo's job now. What is left of this
   is the one thing the buttons did that the gizmo cannot: stop the model
   spinning when somebody asks for a fixed view. */
Viewer.onView = () => $("#spinBtn").classList.remove("on");
// Collapse every finished step; the running one stays open.
/* The reasoning is a disclosure now: shut by default once it has something
   to disclose, because it is the longest thing in the thread and almost
   never the thing being looked for. Opening it also tidies the finished
   steps, which is what this button used to do on its own. */
function setThinkOpen(open) {
  $("#thinkSec").classList.toggle("open", open);
  $("#thinkClear").setAttribute("aria-expanded", String(open));
  if (open) {
    document.querySelectorAll(".tblock").forEach(el => {
      if (el.dataset.state !== "run") el.open = false;
    });
  }
}
$("#thinkClear").onclick = () =>
  setThinkOpen(!$("#thinkSec").classList.contains("open"));

$("#fitBtn").onclick = () => Viewer.fit(true);
$("#wireBtn").onclick = () => $("#wireBtn").classList.toggle("on", Viewer.toggleWire());
$("#spinBtn").onclick = () => {
  Viewer.spin = !Viewer.spin;
  $("#spinBtn").classList.toggle("on", Viewer.spin);
};

$("#histBtn").onclick = () => { loadHistory(); $("#hist").classList.add("open"); };
$("#histClose").onclick = () => $("#hist").classList.remove("open");

$("#copyBtn").onclick = async () => {
  const version = S.versions[S.selected];
  if (!version) return;
  const response = await fetch(API.artifact(S.jobId, version.iteration, "code.py"));
  await navigator.clipboard.writeText(await response.text());
  toast(t("code.copied"));
};

function download(name) {
  const version = S.versions[S.selected];
  if (!version) { warnToast(t("draw.needpart")); return; }
  const link = document.createElement("a");
  link.href = API.artifact(S.jobId, version.iteration, name);
  link.download = "";
  link.click();
}
/* ── the export menu ─────────────────────────────────────────────────
   Five formats that were spread over the code panel and the drawing sheet.
   The drawing two need a drawing, so they build one first rather than
   refusing - asking someone to visit another view before they may download
   a DXF is a rule the app invented, not one the file format has. */

function closeExport() {
  $("#exportMenu").hidden = true;
  $("#exportBtn").setAttribute("aria-expanded", "false");
}

$("#exportBtn").onclick = event => {
  event.stopPropagation();
  const open = $("#exportMenu").hidden;
  $("#exportMenu").hidden = !open;
  $("#exportBtn").setAttribute("aria-expanded", String(open));
};
document.addEventListener("click", event => {
  if (!event.target.closest(".expwrap")) closeExport();
});
$$("#exportMenu .expitem").forEach(item => {
  item.addEventListener("click", closeExport);
});

$("#dlPy").onclick = () => download("code.py");
$("#dlStep").onclick = () => download("model.step");
$("#dlStl").onclick = () => download("model.stl");

$("#errRetry").onclick = () => generate();
$("#errKeep").onclick = () => {
  if (S.versions.length) selectVersion(S.versions.length - 1);
};

$("#lightbox").onclick = () => { $("#lightbox").hidden = true; };

addEventListener("keydown", e => {
  if (e.target.matches("input,textarea")) return;
  const key = e.key.toLowerCase();
  if (key === "1") Viewer.view("iso", true);
  if (key === "2") Viewer.view("front", true);
  if (key === "3") Viewer.view("top", true);
  if (key === "4") Viewer.view("right", true);
  if (key === "f") Viewer.fit(true);
  if (key === "w") $("#wireBtn").click();
  if (key === "h") $("#histBtn").click();
  if (key === "escape") {
    $("#lightbox").hidden = true;
    $("#diag").hidden = true;
    $("#sheet").classList.remove("on");
    $("#hist").classList.remove("open");
  }
  if (key === "d") $("#drawBtn").click();
});





/* ═══════════════════════ model backend ═══════════════════════ */

/* The pipeline reaches every model through one function in autofab.agents,
   so the whole thing can be pointed at OpenAI, a local Ollama, or anything
   else speaking the same API. Keys entered here are held in server memory
   for this process only — never written to disk and never sent back. */

async function loadProviders() {
  let payload;
  try { payload = await API.providers(true); } catch (_) { return; }

  S.providers = payload.providers || [];
  const select = $("#optProvider");
  select.innerHTML = S.providers.map(p => {
    const state = p.ready ? "" : t("prov.needssetup");
    return `<option value="${esc(p.id)}">${esc(p.label)}${esc(state)}</option>`;
  }).join("");

  S.effortDefault = payload.effort || "";
  renderEffort(payload.efforts || [], S.effortDefault);

  const preferred = S.providers.find(p => p.id === payload.default && p.ready)
    || S.providers.find(p => p.ready)
    || S.providers[0];
  if (preferred) {
    select.value = preferred.id;
    applyProvider(preferred.id);
  }
}

/* Effort is the one option that trades wait against reasoning, so the levels
   come from the server rather than a list copied into the browser: pinning
   CADSMITH_EFFORT to a level the picker omits still leaves it selectable. */
function renderEffort(levels, selected) {
  const select = $("#optEffort");
  const keep = selected || select.value || S.effortDefault || "";
  if (levels) S.efforts = levels;
  select.innerHTML = (S.efforts || []).map(level =>
    `<option value="${esc(level)}">${esc(t("opt.effort." + level))}</option>`
  ).join("");
  if ((S.efforts || []).indexOf(keep) >= 0) select.value = keep;
}

function currentProvider() {
  return S.providers.find(p => p.id === $("#optProvider").value) || null;
}

function applyProvider(providerId) {
  const provider = S.providers.find(p => p.id === providerId);
  if (!provider) return;
  S.provider = provider;

  const models = provider.models || [];
  $("#genModels").innerHTML = models.map(m => `<option value="${esc(m)}">`).join("");
  $("#judgeModels").innerHTML = $("#genModels").innerHTML;

  // Use the provider's own defaults where it declares them. Where it does
  // not — a gateway offering hundreds of models — leave the field empty and
  // let the datalist suggest, rather than picking an arbitrary first entry
  // and implying it was chosen for the job.
  $("#optGenModel").value = provider.default_generation_model || "";
  $("#optJudgeModel").value = provider.default_judge_model
    || provider.default_generation_model || "";
  $("#optGenModel").placeholder = models.length
    ? t("ph.modelid.count", { n: models.length }) : t("ph.modelid");
  $("#optJudgeModel").placeholder = $("#optGenModel").placeholder;

  // Effort is a Claude parameter. A local Llama or an OpenAI-compatible
  // gateway does not take it, so do not offer a control that would do
  // nothing.
  $("#effortRow").hidden = !(provider.kind === "anthropic"
                             || provider.kind === "bedrock");

  // Bedrock is the one backend a key cannot fix: it authenticates with the
  // AWS credential chain, so offering the box next to its setup warning
  // invites a paste that is quietly ignored. The note says what to do.
  const needsSetup = !provider.ready && provider.kind !== "bedrock";
  $("#keyRow").hidden = !(needsSetup || provider.key_from_session);
  $("#providerBase").hidden = provider.id !== "custom";
  $("#providerBase").value = provider.base_url || "";
  $("#providerKey").placeholder = t(provider.needs_key
    ? "ph.apikey.memory" : "ph.apikey.none");

  setModelLabels($("#optGenModel").value, $("#optJudgeModel").value);
  updateProviderNote();
  updateGenerateAvailability();
}

/* Name the models that actually did the work, rather than the ones the
   pipeline happens to default to. */
function setModelLabels(generation, judge) {
  S.genModel = generation || "";
  S.judgeModel = judge || "";
  const short = name => (name || "").split("/").pop().toUpperCase() || "—";
  $("#genModelLabel").textContent =
    t("label.planner.model", { model: short(generation) });
  $("#judgeModelLabel").textContent =
    t("label.judge.model", { model: short(judge) });
  // The composer names the model that will do the work, the way the design
  // does. The full set is one click away behind the kebab.
  const chip = $("#modelChipName");
  if (chip) chip.textContent = (generation || "").split("/").pop() || "—";
}

/* Whether the catalogue can serve a part right now. Two callers depend on
   it agreeing: the Generate button stays live because of it, and the note
   under the provider picker has to say why. */
function catalogueLive() {
  return !!(S.health && S.health.checks && S.health.checks.catalog
            && S.health.checks.catalog.ok);
}

function updateProviderNote() {
  const provider = S.provider;
  const note = $("#providerNote");
  if (!provider) { note.textContent = ""; return; }

  const generation = $("#optGenModel").value.trim();
  const judge = $("#optJudgeModel").value.trim();

  if (!provider.ready) {
    note.className = "optnote warn";
    // The server sends the same sentence as a key, so it can be shown in
    // whatever language the switch is on; `hint` is the fallback.
    let text = (provider.hint_key && I18N.has(provider.hint_key)
      ? t(provider.hint_key, provider.hint_params || {})
      : provider.hint) || "";
    // Some hints are sentences and some are fragments; only the fragments
    // need the full stop.
    if (!/[.。！!？?]$/.test(text)) text += ".";
    // Generate is not greyed out in this state, because the catalogue can
    // still answer. Saying so here is what makes the live button honest -
    // otherwise it looks like the setup warning is being ignored.
    if (catalogueLive()) text += " " + t("prov.catalogonly");
    note.textContent = text;
    return;
  }
  if (!generation || !judge) {
    note.className = "optnote warn";
    note.textContent = t("prov.bothroles");
    return;
  }
  if (generation === judge) {
    // The pipeline judges with a separate, stronger model on purpose.
    note.className = "optnote warn";
    note.textContent = t("prov.samemodel");
    return;
  }
  note.className = "optnote ok";
  note.textContent = provider.local ? t("prov.local") : t("prov.ready");
}

function updateGenerateAvailability() {
  const provider = S.provider;
  const kernelOk = !!(S.health && S.health.checks
                      && S.health.checks.cadquery.ok);
  const ready = !!(provider && provider.ready
                   && $("#optGenModel").value.trim()
                   && $("#optJudgeModel").value.trim());
  // The catalogue answers a standard part with no model call, so a missing
  // provider key is not a reason to grey this out - the note right above it
  // says standard parts still work, and it is telling the truth. Ask for
  // something the catalogue cannot serve and the server says so.
  $("#genBtn").disabled = !(kernelOk && (ready || catalogueLive()));
}

async function saveProviderKey() {
  const provider = currentProvider();
  if (!provider) return;

  const button = $("#saveKeyBtn");
  button.disabled = true;
  try {
    const updated = await API.setProviderKey(
      provider.id, $("#providerKey").value.trim(),
      $("#providerBase").value.trim());
    Object.assign(provider, updated);
    $("#providerKey").value = "";
    applyProvider(provider.id);

    const select = $("#optProvider");
    const option = [...select.options].find(o => o.value === provider.id);
    if (option) option.textContent =
      provider.label + (provider.ready ? "" : t("prov.needssetup"));

    toast(t(provider.ready ? "prov.isready" : "prov.stillneeds",
            { label: provider.label }));
    loadHealth();
  } catch (error) {
    warnToast(error.message);
  } finally {
    button.disabled = false;
  }
}

$("#optProvider").onchange = e => applyProvider(e.target.value);
function onModelEdited() {
  setModelLabels($("#optGenModel").value, $("#optJudgeModel").value);
  updateProviderNote();
  updateGenerateAvailability();
}
$("#optGenModel").oninput = onModelEdited;
$("#optJudgeModel").oninput = onModelEdited;
$("#saveKeyBtn").onclick = saveProviderKey;
$("#providerKey").addEventListener("keydown", e => {
  if (e.key === "Enter") saveProviderKey();
});

/* ═══════════════════════ replay ═══════════════════════ */

/* A replay re-emits the events a real run produced, against the artifacts
   that run exported. Nothing is simulated; only the pacing differs, so a
   demo does not depend on the network or on a part converging this time. */
async function startReplay(sourceJobId) {
  if (S.busy) { warnToast(t("run.busy")); return; }

  S.busy = true;
  S.replay = true;
  S.versions = [];
  S.selected = -1;
  S.designPlan = null;
  S.seq = 0;
  $("#hist").classList.remove("open");
  $("#iters").innerHTML = "";
  $("#plog").innerHTML = "";
  Viewer.clear();
  thinkReset();
  resetUsage();
  S.catalog = null;
  Viewer.building = true;     // slow orbit while the pipeline works
  setCode("");
  paramsReset();
  showOverlay("pipe");
  renderStages("plan", t("detail.replaying"));
  setPill(t("hist.replaypill"));

  try {
    const job = await API.replay(sourceJobId, 6);
    S.jobId = job.id;
    follow(job.id, 0);
  } catch (error) {
    S.busy = false;
    S.replay = false;
    resetPill();
    failRun(error.message);
  }
}

function setPill(text) {
  const pill = $("#enginePill");
  if (!pill) return;
  pill.textContent = text || "";
  pill.hidden = !text;
  pill.classList.toggle("replaying", Boolean(text));
}

function resetPill() { setPill(""); }

/* ═══════════════════════ natural-language edits ═══════════════════════ */

/* The steps mirror what actually happens. A parameter patch skips the Judge:
   it changes a number the script already declares, so the kernel alone can
   confirm it. The Refiner writes new code, so the full check is worth it. */
const EDIT_STEPS = [
  { key: "read",     label: "edit.step.read" },
  { key: "apply",    label: "edit.step.apply" },
  { key: "rebuild",  label: "edit.step.rebuild" },
  { key: "validate", label: "edit.step.validate" },
  { key: "done",     label: "edit.step.done" },
];

function renderEditSteps(activeKey, skipValidate) {
  const steps = skipValidate
    ? EDIT_STEPS.filter(s => s.key !== "validate") : EDIT_STEPS;
  const activeIndex = steps.findIndex(s => s.key === activeKey);
  $("#actSteps").innerHTML = steps.map((step, i) => {
    const state = i < activeIndex ? "done" : (i === activeIndex ? "act" : "");
    return `<div class="ast ${state}"><i></i>${esc(t(step.label))}</div>`
      + (i < steps.length - 1 ? `<span class="arrow">→</span>` : "");
  }).join("");
}

function handleEditEvent(event) {
  const { phase, status, message, data } = event;

  if (phase === "edit") {
    S.editMethod = data.method;
    S.editSkipValidate = data.method === "parameter patch";
    renderEditSteps("apply", S.editSkipValidate);
    if (data.changes && data.changes.length) {
      $("#actDiff").innerHTML = data.changes.map(c =>
        `<span class="diffpill">${esc(c.name.replace(/_/g, " "))}
           <span class="strike">${fmt(c.old)}</span>${fmt(c.new)}</span>`).join("");
    } else {
      $("#actDiff").innerHTML =
        `<span class="diffpill">${esc(t("edit.refineragent"))}</span>`;
    }
    return;
  }

  if (phase === "refine" && status === "started") {
    renderEditSteps("apply", false);
  }
  if (phase === "execute") {
    renderEditSteps("rebuild", S.editSkipValidate);
  }
  if (phase === "judge") {
    renderEditSteps("validate", false);
  }
  if (phase === "version" && status === "ok") {
    addVersion(data);
  }
  if ((phase === "code" || phase === "refine" || phase === "error_fix")
      && status === "ok") {
    setCode(data.code);
  }
  if (phase === "job" && status === "ok") {
    renderEditSteps("done", S.editSkipValidate);
    setTimeout(() => { $("#act").hidden = true; }, 900);
    finishEdit(true, data);
  }
  if (phase === "job" && status === "failed") {
    $("#act").hidden = true;
    finishEdit(false, data, message);
  }
}

function finishEdit(ok, data, message) {
  const fromPanel = S.editFromPanel;
  S.editing = false;
  S.busy = false;
  setComposerEnabled(true);
  endParameterRebuild();

  if (!ok) {
    warnToast(message || t("edit.failed"));
    return;
  }
  // A parameter the panel set did not come from the instruction box, so
  // whatever is half-typed in there is still the person's.
  if (!fromPanel) $("#prompt").value = "";
  const method = t(data.method === "parameter patch"
    ? "edit.method.patch" : "edit.method.agent");
  const seconds = data.total_ms
    ? t("run.seconds", { s: (data.total_ms / 1000).toFixed(1) }) : "";
  toast(t("edit.done", { method, seconds }));
}

async function applyEdit() {
  const instruction = $("#prompt").value.trim();
  if (instruction) showAsk(instruction);
  if (!instruction) { warnToast(t("edit.needinstruction")); return; }
  if (S.busy || !S.jobId || !S.versions.length) return;

  S.busy = true;
  S.editing = true;
  S.editSkipValidate = false;
  setComposerEnabled(false);
  $("#actDiff").innerHTML = "";
  $("#act").hidden = false;
  renderEditSteps("read", false);

  try {
    // Edit the version on screen, which is not always the newest one.
    const base = S.versions[S.selected];
    await API.edit(S.jobId, instruction, base ? base.iteration : undefined);
    follow(S.jobId, S.seq);
  } catch (error) {
    $("#act").hidden = true;
    finishEdit(false, {}, error.message);
  }
}


/* ═══════════════════════ the parameters view ═══════════════════════
   The same script the Code view shows, as one control per dimension it
   declares. Not a simplified model of the part: the controls are read from
   the source by the server, patched by the same function a natural-language
   edit uses, and rebuilt by the same kernel. Someone who never opens the
   Code view is doing exactly what someone who does would be doing. */

/* Python's `f"{value:g}"`, closely enough. The server rewrites the line for
   real when it rebuilds; this is only so the Code view reads correctly while
   a slider is moving, and the two agree on every value a control can send. */
function pyNumber(value, isInteger) {
  if (isInteger && Number.isInteger(value)) return String(value);
  let text = String(Number(value.toPrecision(6)));
  if (!text.includes(".") && !text.includes("e")) text += ".0";
  return text;
}

const ASSIGNMENT = /^([A-Za-z_]\w*)(\s*=\s*)(-?\d+(?:\.\d+)?)(\s*(?:#.*)?)$/;

/* The base source with every draft value written in. Always rebuilt from the
   base rather than from the last patch, so dragging a slider back and forth
   cannot accumulate rounding. */
function codeWithDrafts() {
  const lines = S.paramCode.split("\n");
  S.params.forEach(p => {
    const value = S.paramDraft[p.name];
    if (value === undefined || lines[p.line] === undefined) return;
    const match = ASSIGNMENT.exec(lines[p.line]);
    if (!match || match[1] !== p.name) return;
    lines[p.line] = match[1] + match[2] + pyNumber(value, p.integer) + match[4];
  });
  return lines.join("\n");
}

function draftedNames() {
  return S.params
    .filter(p => Math.abs((S.paramDraft[p.name] ?? p.value) - p.value) > 1e-9)
    .map(p => p.name);
}

/* Show the moved values in the Code view as they move, with the changed
   lines marked - the two views are of one script, so they never disagree. */
function refreshDraftCode() {
  const changed = draftedNames();
  setCode(codeWithDrafts(), changed);
  $$("#paramsBody .prow").forEach(row => {
    row.classList.toggle("dirty", changed.includes(row.dataset.name));
  });
  const reset = $("#paramsReset");
  if (reset) reset.hidden = !changed.length || S.paramBusy;
}

function paramRow(p) {
  const value = S.paramDraft[p.name] ?? p.value;
  const step = p.step || (p.integer ? 1 : 0.1);
  return `<div class="prow" data-name="${esc(p.name)}">
      <div class="prow-top">
        <span class="prow-name" title="${esc(p.name)}">${esc(p.label)}</span>
        <span class="prow-val">
          <input class="prow-num" type="number" inputmode="decimal"
                 data-name="${esc(p.name)}" value="${fmt(value)}"
                 min="0" step="${step}"
                 aria-label="${esc(p.label)}" />
          <span class="prow-unit">${esc(p.unit)}</span>
        </span>
      </div>
      <input type="range" data-name="${esc(p.name)}"
             min="${p.min}" max="${p.max}" step="${step}" value="${value}"
             aria-label="${esc(p.label)}" />
    </div>`;
}

function renderParameters() {
  const body = $("#paramsBody");
  if (!S.jobId || !S.versions.length) {
    body.innerHTML = `<div class="await">
        <svg class="icn" viewBox="0 0 24 24" style="opacity:.5"><circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/></svg>
        <span>${esc(t("params.await"))}</span>
      </div>`;
    return;
  }
  if (S.paramLoading) {
    // A part is on screen; its dimensions are on their way. Saying "generate
    // a part" here would be telling someone to do what they just did.
    body.innerHTML = `<div class="await">
        <svg class="icn" viewBox="0 0 24 24" style="opacity:.5"><circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/></svg>
        <span>${esc(t("params.loading"))}</span>
      </div>`;
    return;
  }
  if (!S.params.length) {
    // Nothing to put a control on, so nothing to show: an empty card is
    // worse than no card.
    showCard("params", false);
    body.innerHTML = `<div class="await"><span>${esc(t("params.none"))}</span></div>`;
    return;
  }
  showCard("params", true);

  body.innerHTML =
    `<div class="params-hint">${esc(t("params.hint"))}</div>`
    + S.params.map(paramRow).join("")
    + `<div class="params-foot">
         <span class="params-note" id="paramsNote"></span>
         <button class="btn sm" id="paramsReset" hidden>${esc(t("params.reset"))}</button>
       </div>`;

  $$("#paramsBody input[type=range]").forEach(slider => {
    // `input` fires all the way through a drag and only moves numbers;
    // `change` fires when the person lets go, and that is what costs a
    // rebuild. Rebuilding on every frame of a drag would queue dozens of
    // kernel runs to show one result.
    slider.addEventListener("input", () => {
      setDraft(slider.dataset.name, parseFloat(slider.value));
    });
    slider.addEventListener("change", () => commitParameters());
  });

  $$("#paramsBody .prow-num").forEach(field => {
    field.addEventListener("input", () => {
      const typed = parseFloat(field.value);
      if (Number.isFinite(typed) && typed > 0) {
        setDraft(field.dataset.name, typed, { from: "number" });
      }
    });
    field.addEventListener("change", () => commitParameters());
    field.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); field.blur(); }
    });
  });

  const reset = $("#paramsReset");
  if (reset) reset.onclick = () => {
    S.paramDraft = {};
    renderParameters();
    refreshDraftCode();
  };

  refreshDraftCode();
  setStat();
}

/* One value moved. The slider and the number field show the same number, so
   whichever was used updates the other. */
function setDraft(name, value, options) {
  if (!Number.isFinite(value)) return;
  S.paramDraft[name] = value;
  const row = $(`#paramsBody .prow[data-name="${CSS.escape(name)}"]`);
  if (row) {
    const slider = row.querySelector("input[type=range]");
    const field = row.querySelector(".prow-num");
    // A typed value may sit outside the slider's range; widen rather than
    // snap, so the field is never overruled by its own slider.
    if (slider) {
      if (value < parseFloat(slider.min)) slider.min = value;
      if (value > parseFloat(slider.max)) slider.max = value;
      slider.value = value;
    }
    if (field && (!options || options.from !== "number")) field.value = fmt(value);
  }
  refreshDraftCode();
}

/* Send every moved value at once: one rebuild, one version, whether the
   person moved one slider or typed into four fields. */
async function commitParameters() {
  if (S.paramBusy || S.busy || !S.jobId || !S.params.length) return;
  const changes = {};
  S.params.forEach(p => {
    const value = S.paramDraft[p.name];
    if (value !== undefined && Math.abs(value - p.value) > 1e-9) {
      changes[p.name] = value;
    }
  });
  if (!Object.keys(changes).length) return;

  S.paramBusy = true;
  S.busy = true;
  S.editing = true;
  S.editFromPanel = true;
  S.editSkipValidate = true;
  $("#paramsBody").classList.add("busy");
  const note = $("#paramsNote");
  if (note) { note.textContent = t("params.rebuilding"); note.classList.add("work"); }
  const reset = $("#paramsReset");
  if (reset) reset.hidden = true;
  $("#actDiff").innerHTML = "";
  $("#act").hidden = false;
  renderEditSteps("read", true);

  try {
    await API.setParameters(S.jobId, changes, S.paramBase);
    follow(S.jobId, S.seq);
  } catch (error) {
    $("#act").hidden = true;
    endParameterRebuild();
    finishEdit(false, {}, error.message);
    // The part on screen is still the one the kernel built, so put the
    // controls back to it rather than leaving them showing a value that
    // was refused.
    S.paramDraft = {};
    renderParameters();
    refreshDraftCode();
  }
}

function endParameterRebuild() {
  S.paramBusy = false;
  S.editFromPanel = false;
  $("#paramsBody").classList.remove("busy");
  const note = $("#paramsNote");
  if (note) { note.textContent = ""; note.classList.remove("work"); }
}

/* Read the controls for a version. The ranges the server computes are
   anchored to the value it read, so a rebuilt part would otherwise re-centre
   every slider under the hand that just moved it; a range that still holds
   the new value is kept. */
async function loadParameters(iteration) {
  const previous = new Map(S.params.map(p => [p.name, p]));
  S.paramBase = iteration;
  S.paramDraft = {};
  S.paramLoading = true;
  if (S.paramView === "params") renderParameters();

  try {
    // Both at once, and both here: the controls patch the source, so a
    // descriptor from one version against the code of another would write
    // the right number onto the wrong line.
    const [code, data] = await Promise.all([
      fetch(API.artifact(S.jobId, iteration, "code.py"))
        .then(r => (r.ok ? r.text() : null)),
      API.parameters(S.jobId, iteration),
    ]);
    if (code !== null) { S.paramCode = code; setCode(code); }
    S.params = (data.parameters || []).map(p => {
      const before = previous.get(p.name);
      if (before && p.value >= before.min && p.value <= before.max
          && before.kind === p.kind) {
        return Object.assign({}, p,
                             { min: before.min, max: before.max, step: before.step });
      }
      return p;
    });
  } catch (_) {
    S.params = [];
  }

  S.paramLoading = false;
  if (S.paramView === "params") renderParameters();
  setStat();
}

/* No part on screen, so nothing to put a control on. */
function paramsReset() {
  S.params = [];
  S.paramDraft = {};
  S.paramCode = "";
  S.paramBase = null;
  S.paramLoading = false;
  endParameterRebuild();
  if (S.paramView === "params") renderParameters();
  setStat();
}

/* ── code and parameters ─────────────────────────────────────────────
   They were two tabs of one panel. They are not two views of one thing:
   the source is a document to read, and the dimensions are controls to
   move, and the second is wanted far more often than the first. So the
   dimensions live in a card on the right, where they are visible beside
   the model they change, and the source has the centre to itself. */

function setStat() {
  const stat = $("#codeStat");
  stat.hidden = false;
  stat.textContent = S.codeLines
    ? t("code.stat", { n: S.codeLines }) : t("code.empty");
}

//: Kept as the one entry point the header switch and the old callers share.
function showParamView(which) {
  S.paramView = which === "params" ? "params" : "code";
  if (S.paramView === "params") {
    // Parameters are not a view of the centre any more. Asking for them
    // opens their card and puts it where the eye is.
    showCard("params", true);
    setCardOpen("params", true);
    renderParameters();
    const card = document.querySelector('.rcard[data-card="params"]');
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  setStat();
}

function chooseParamView(which) { showParamView(which); }

/* ═══════════════════════ drawing sheet ═══════════════════════ */

let sheetSvg = null;

async function openDrawing() {
  const version = S.versions[S.selected];
  if (!version) { warnToast(t("draw.needpart")); return; }

  const button = $("#drawBtn");
  button.disabled = true;
  $("#paper").innerHTML = `<div style="padding:60px;color:#666;font-family:monospace;font-size:12px">${esc(t("draw.projecting"))}</div>`;
  $("#sheet").classList.add("on");

  try {
    // Fetched directly rather than through API.json(), so it has to ask for
    // its language itself: the server explains a failed projection.
    const url = API.artifact(S.jobId, version.iteration, "drawing.svg")
                + `?lang=${encodeURIComponent(I18N.current)}`;
    const response = await fetch(url);
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    sheetSvg = await response.text();
    $("#paper").innerHTML = sheetSvg;
  } catch (error) {
    sheetSvg = null;
    $("#paper").innerHTML =
      `<div style="padding:60px;color:#B00;font-family:monospace;font-size:12px;max-width:640px">`
      + `${esc(t("draw.failed"))}<br><br>${esc(error.message)}</div>`;
  } finally {
    button.disabled = false;
  }
}

/* The PNG is made from the sheet, so there has to be a sheet. Building one
   costs a projection on the server and no model call, which is cheaper than
   telling someone to go and open another view before they may have their
   file. */
async function ensureDrawing() {
  if (sheetSvg) return true;
  if (S.selected < 0) { warnToast(t("draw.needpart")); return false; }
  await openDrawing();
  return Boolean(sheetSvg);
}

/* Rasterise the sheet in the browser. The SVG is self-contained - no external
   references - so it can be drawn straight onto a canvas. */
function exportDrawingPng() {
  if (!sheetSvg) { warnToast(t("draw.needdrawing")); return; }
  const svg = $("#paper").querySelector("svg");
  const box = (svg.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
  const width = box.length === 4 && box[2] ? box[2] : 420;
  const height = box.length === 4 && box[3] ? box[3] : 297;
  // 8 px per mm is about 200 dpi: enough to read a 2.5mm note when printed.
  const scale = 8;

  const blob = new Blob([sheetSvg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = new Image();

  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);

    canvas.toBlob(pngBlob => {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(pngBlob);
      link.download = `${S.jobId}_drawing.png`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      toast(t("draw.exported"));
    }, "image/png");
  };
  image.onerror = () => {
    URL.revokeObjectURL(url);
    warnToast(t("draw.rasterfail"));
  };
  image.src = url;
}

// Through the switch, not straight to the sheet, so the header cannot
// show the model tab while a drawing is on screen.
$("#drawBtn").onclick = () => showView("drawing");

/* Reload re-reads the built part from the server rather than rebuilding it:
   no model call, no kernel run, nothing billed. It is for a canvas that has
   got itself into a state, which is the only thing a reload can honestly
   promise. */
$("#reloadBtn").onclick = async () => {
  if (S.selected < 0) { warnToast(t("draw.needpart")); return; }
  await selectVersion(S.selected);
  toast(t("view.reloaded"));
};
$("#back3d").onclick = () => showView("model");

/* ── the four ways to look at a part ─────────────────────────────────
   One switch, in the header, over what used to be three controls in three
   places: the right column's own Code/Parameters toggle, and a Drawing
   button on the viewport toolbar. They are the same kind of choice, so they
   are now the same control, and the old ones still work underneath it. */

const VIEWS = ["model", "code", "params", "drawing"];

function showView(which) {
  if (!VIEWS.includes(which)) which = "model";
  if (which === "drawing" && $("#drawBtn").disabled) {
    // Nothing to draw yet. Say so rather than switching to a blank sheet.
    toast(t("view.needpart"));
    return;
  }
  S.view = which;
  // The stage and the code panel are the same slot in the centre column.
  // Parameters are a card on the right now, not a view of the centre, so
  // asking for them leaves the model on screen - which is the point, since
  // they are controls for the thing you are looking at.
  const source = which === "code";
  $("#stage").hidden = source;
  $(".vtools").hidden = source;          // Spin/Fit mean nothing over code
  $("#codeSec").hidden = !source;
  $("#sheet").classList.toggle("on", which === "drawing");
  if (which === "drawing") openDrawing();
  if (which === "code") setStat();
  if (which === "params") chooseParamView("params");
  $$("#viewSeg .vsegb").forEach(button => {
    // "params" opens a card without changing the centre, so it flashes
    // rather than latches: the centre is still the model.
    const on = which === "params"
      ? button.dataset.view === "model"
      : button.dataset.view === which;
    button.classList.toggle("on", on);
    button.setAttribute("aria-selected", String(on));
  });
}

$$("#viewSeg .vsegb").forEach(button => {
  button.onclick = () => showView(button.dataset.view);
});

/* The drawing segment follows the button it replaces, which the run itself
   enables and disables - so the two cannot disagree about whether there is
   a part to draw. */
new MutationObserver(() => {
  $('#viewSeg .vsegb[data-view="drawing"]').disabled = $("#drawBtn").disabled;
}).observe($("#drawBtn"), { attributes: true, attributeFilter: ["disabled"] });

$("#fullBtn").onclick = () => {
  const doc = document;
  if (doc.fullscreenElement) doc.exitFullscreen();
  else doc.documentElement.requestFullscreen().catch(() => {
    // Refused (an iframe without the permission, or a browser that asks
    // first). Nothing is broken; the page simply stays as it is.
  });
};
$("#expPng").onclick = async () => {
  if (await ensureDrawing()) exportDrawingPng();
};

/* The DXF is the drawing; the SVG on screen is a picture of it. Its
   dimensions are real DIMENSION entities, so whatever opens the file
   re-measures the geometry rather than trusting a string. */
$("#expDxf").onclick = () => {
  const version = S.versions[S.selected];
  if (!S.jobId || !version) { warnToast(t("draw.needpart")); return; }
  const link = document.createElement("a");
  link.href = API.artifact(S.jobId, version.iteration, "drawing.dxf");
  link.download = `${S.jobId}_v${version.iteration}_drawing.dxf`;
  link.click();
  toast(t("draw.dxfstarted"));
};

/* ═══════════════════════ interface language ═══════════════════════ */

/* Two buttons, each written in its own language, so someone who cannot read
   the current interface can still find their way out of it. */
function buildLangSwitch() {
  const box = $("#langSw");
  box.setAttribute("aria-label", t("app.language"));
  box.innerHTML = I18N.LANGS.map(l =>
    `<button class="lang${l.code === I18N.current ? " on" : ""}" `
    + `data-lang="${esc(l.code)}" lang="${esc(l.code)}" `
    + `aria-pressed="${l.code === I18N.current}">${esc(l.label)}</button>`
  ).join("");
  $$("#langSw .lang").forEach(button => {
    button.onclick = () => I18N.set(button.dataset.lang);
  });
}

/* Everything on screen that JavaScript wrote rather than the markup.
   I18N.apply() has already redrawn the static text by the time this runs;
   these panels hold state, and each is redrawn from that state rather than
   from the DOM, so nothing is translated twice. */
function relocalise() {
  buildLangSwitch();

  const chip = $("#healthChip").querySelector("span");
  if (!S.health) chip.textContent = t("health.unreachable");
  else chip.textContent = S.health.ok ? t("health.ready")
    : S.health.can_generate ? t("health.degraded") : t("health.notready");
  if (S.health && S.health.checks && !S.health.checks.model_backend.ok) {
    const c = S.health.checks.catalog;
    $("#keyBannerText").textContent = t(c && c.ok ? "banner.catalog"
                                                  : "banner.nobackend");
  }

  if (S.health && S.health.checks) renderDiagRows(S.health.checks);
  renderExamples();
  // Not applyProvider(): that resets the model fields to the provider's
  // defaults and would silently discard a model id someone had typed. Only
  // the text it writes is redrawn.
  renderEffort(null, $("#optEffort").value);
  if (S.provider) {
    const models = S.provider.models || [];
    $("#optGenModel").placeholder = models.length
      ? t("ph.modelid.count", { n: models.length }) : t("ph.modelid");
    $("#optJudgeModel").placeholder = $("#optGenModel").placeholder;
    $("#providerKey").placeholder = t(S.provider.needs_key
      ? "ph.apikey.memory" : "ph.apikey.none");
    updateProviderNote();
  }
  if (S.catalog) {
    // applyProvider has just put the model ids back; restore what actually
    // built this part.
    const label = t("label.catalog",
                    { backend: String(S.catalog.backend || "").toUpperCase() });
    $("#genModelLabel").textContent = label;
    $("#judgeModelLabel").textContent = label;
  } else if (S.genModel || S.judgeModel) {
    setModelLabels(S.genModel, S.judgeModel);
  }
  if (S.paramView === "params") renderParameters();
  if (S.codeLines !== undefined || S.paramView === "params") setStat();
  if (S.stage) renderStages(S.stage.key, S.stage.detail);
  renderUsage();
  if (!S.replay) resetPill();
  renderIterations();
  // A catalogue part has no design plan, but its panel still has text.
  if (S.designPlan || S.catalog) renderPlan(S.designPlan);
  const version = S.versions[S.selected];
  if (version) { renderKernelFacts(version); renderValidation(version); }
  if ($("#hist").classList.contains("open")) loadHistory();
}

I18N.onChange(relocalise);

/* ═══════════════════════ boot ═══════════════════════ */

(async function boot() {
  I18N.apply();
  buildLangSwitch();
  await loadHealth();
  await loadProviders();
  await loadExamples();
  await loadHistory();
  setCode("");
  paramsReset();
  Viewer.fit(false);
})();
