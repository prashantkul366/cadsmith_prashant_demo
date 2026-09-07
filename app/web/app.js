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
  editing: false,
  examples: [],    // kept so a language change can redraw them translated
  stage: null,     // {key, detail} - the pipeline strip, redrawn from state
  codeLines: undefined,
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
    $("#keyBannerText").textContent = t("banner.nobackend");
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
   quoting is not translating. */
function renderDiagRows(checks) {
  $("#diagRows").innerHTML = Object.entries(checks).map(([name, check]) => `
    <div class="drow">
      <span class="dot ${check.ok ? "ok" : "bad"}"></span>
      <b>${esc(I18N.has("diag." + name) ? t("diag." + name)
                                        : name.replace(/_/g, " "))}</b>
      <span>${esc(check.detail)}</span>
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
  if (which !== "none") $("#minfo").hidden = true;
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

  if (phase === "thinking") {
    thinkAppend(data.agent || "code", data.iteration || 0,
                data.stream === "thinking" ? "thinking" : "text", message);
    return;
  }

  // A step that produced reasoning is finished when its own phase resolves.
  if (AGENT_KEYS.includes(phase) && (status === "ok" || status === "failed")) {
    thinkFinish(phase, data.iteration || 0, status === "ok", data.ms);
  }

  const stage = PHASE_STAGE[phase];
  if (stage) {
    let detail = "";
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

function addVersion(version) {
  const existing = S.versions.findIndex(v => v.iteration === version.iteration);
  if (existing >= 0) S.versions[existing] = version;
  else S.versions.push(version);
  renderIterations();
  selectVersion(S.versions.length - 1, { quiet: true });
}

function renderIterations() {
  if (!S.versions.length) { $("#iters").innerHTML = ""; return; }
  const cards = S.versions.map((v, i) => {
    const kind = v.source === "edit" ? "edit" : (v.passed ? "pass" : "fail");
    const label = t(v.source === "edit" ? "iter.edit" : "iter.iteration",
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

  try {
    const box = await Viewer.load(
      API.artifact(S.jobId, version.iteration, "model.stl"));
    if (!options || !options.quiet) Viewer.fit(true);
    else Viewer.fit(false);
    showOverlay("none");
    $("#minfo").hidden = false;
  } catch (error) {
    warnToast(error.message);
  }

  try {
    const response = await fetch(
      API.artifact(S.jobId, version.iteration, "code.py"));
    if (response.ok) setCode(await response.text());
  } catch (_) { /* code panel keeps its last content */ }

  renderKernelFacts(version);
  renderValidation(version);
  sheetSvg = null;
  $("#drawBtn").disabled = false;
  // A parameter patch is rebuilt by the kernel with no model call, so editing
  // stays available without an API key; the agent path reports its own need.
  const canRebuild = !!(S.health && S.health.checks
                        && S.health.checks.cadquery.ok);
  $("#cmdIn").disabled = !canRebuild;
  $("#applyBtn").disabled = !canRebuild;
}

/* ═══════════════════════ panels ═══════════════════════ */

function renderPlan(plan) {
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
  $("#mtitle").textContent = version.source === "edit"
    ? t("facts.updated")
    : t(version.passed ? "facts.validated" : "facts.unvalidated");
  $("#mfacts").innerHTML = [
    [t("facts.bbox"), `${fmt(bbox.xlen)}×${fmt(bbox.ylen)}×${fmt(bbox.zlen)}`],
    [t("facts.volume"), fmt(Math.round(geometry.volume || 0))],
    [t("facts.faces"), geometry.num_faces],
    [t("facts.edges"), geometry.num_edges],
    [t("facts.solid"), t(geometry.is_valid ? "facts.watertight" : "facts.invalid")],
  ].map(([label, value]) =>
    `<div class="fact"><b>${esc(String(value ?? "—"))}</b><span>${esc(label)}</span></div>`
  ).join("");

  const icon = $("#mIcon");
  if (icon) icon.style.color = version.passed ? "var(--valid)" : "var(--warn)";
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

  let heading, body, attribution;
  if (judged) {
    heading = t(passed ? "val.accepted" : "val.rejected");
    // The Judge's own words, which are model output and stay as written.
    body = version.judge_feedback || version.feedback_text || "";
    const judgeModel = (S.judgeModel || "").toUpperCase() || t("val.src.judge");
    attribution = judgeModel + " · " + t(version.has_render
      ? "val.src.render" : "val.src.metrics");
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

async function generate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) { warnToast(t("run.needprompt")); return; }
  if (S.busy) return;

  S.busy = true;
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
  Viewer.building = true;     // slow orbit while the pipeline works
  setCode("");
  // Everything on the right belongs to the run that is being replaced, so
  // clear it now rather than leaving the previous part's plan and verdict on
  // screen until the new ones arrive.
  $("#planBody").innerHTML = `<div class="await">${esc(t("plan.planning"))}</div>`;
  $("#valBody").innerHTML = `<div class="await">${esc(t("val.waiting"))}</div>`;
  sheetSvg = null;
  $("#drawBtn").disabled = true;
  $("#cmdIn").disabled = true;
  $("#applyBtn").disabled = true;
  showOverlay("pipe");
  renderStages("plan", t("detail.sending"));

  const options = {
    max_iterations: +$("#optIters").value,
    use_vision: $("#optVision").classList.contains("on"),
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

function finishRun(data) {
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

  if (S.converged) {
    // Japanese has no plural agreement, so {s} resolves to nothing there.
    toast(t("run.converged", { n: data.iterations, seconds, cost,
                               s: data.iterations === 1 ? "" : "s" }));
  } else {
    warnToast(t("run.notconverged", { n: data.iterations }));
  }
  loadHistory();
}

function failRun(message) {
  S.busy = false;
  Viewer.building = false;
  thinkIdle();
  $("#genBtn").disabled = !(S.health && S.health.can_generate);
  $("#errTitle").textContent = t("err.title");
  $("#errMsg").textContent = message || t("err.unknown");
  $("#errFix").textContent = t(S.versions.length
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
    $("#enginePill").textContent = t("hist.replaypill");
    $("#enginePill").classList.add("replaying");
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

$("#genBtn").onclick = generate;
$("#prompt").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate();
});

$("#optIters").oninput = e => { $("#optItersOut").value = e.target.value; };
$("#optVision").onclick = () => {
  const on = $("#optVision").classList.toggle("on");
  $("#optVision").setAttribute("aria-checked", String(on));
};

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

$$(".vt[data-view]").forEach(button => {
  button.onclick = () => {
    $$(".vt[data-view]").forEach(b => b.classList.remove("on"));
    button.classList.add("on");
    $("#spinBtn").classList.remove("on");
    Viewer.view(button.dataset.view, true);
  };
});
// Collapse every finished step; the running one stays open.
$("#thinkClear").onclick = () => {
  document.querySelectorAll(".tblock").forEach(el => {
    if (el.dataset.state !== "run") el.open = false;
  });
};

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

  const preferred = S.providers.find(p => p.id === payload.default && p.ready)
    || S.providers.find(p => p.ready)
    || S.providers[0];
  if (preferred) {
    select.value = preferred.id;
    applyProvider(preferred.id);
  }
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

  const needsSetup = !provider.ready;
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
    note.textContent = (provider.hint_key && I18N.has(provider.hint_key)
      ? t(provider.hint_key, provider.hint_params || {})
      : provider.hint) + ".";
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
  $("#genBtn").disabled = !(kernelOk && ready);
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
  Viewer.building = true;     // slow orbit while the pipeline works
  setCode("");
  showOverlay("pipe");
  renderStages("plan", t("detail.replaying"));
  $("#enginePill").textContent = t("hist.replaypill");
  $("#enginePill").classList.add("replaying");

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

function resetPill() {
  $("#enginePill").textContent = t("app.engine");
  $("#enginePill").classList.remove("replaying");
}

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
  S.editing = false;
  S.busy = false;
  $("#applyBtn").disabled = false;
  $("#cmdIn").disabled = false;

  if (!ok) {
    warnToast(message || t("edit.failed"));
    return;
  }
  $("#cmdIn").value = "";
  const method = t(data.method === "parameter patch"
    ? "edit.method.patch" : "edit.method.agent");
  const seconds = data.total_ms
    ? t("run.seconds", { s: (data.total_ms / 1000).toFixed(1) }) : "";
  toast(t("edit.done", { method, seconds }));
}

async function applyEdit() {
  const instruction = $("#cmdIn").value.trim();
  if (!instruction) { warnToast(t("edit.needinstruction")); return; }
  if (S.busy || !S.jobId || !S.versions.length) return;

  S.busy = true;
  S.editing = true;
  S.editSkipValidate = false;
  $("#applyBtn").disabled = true;
  $("#cmdIn").disabled = true;
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

$("#applyBtn").onclick = applyEdit;
$("#cmdIn").addEventListener("keydown", e => {
  if (e.key === "Enter") applyEdit();
});

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

/* Rasterise the sheet in the browser. The SVG is self-contained - no external
   references - so it can be drawn straight onto a canvas. */
function exportDrawingPng() {
  if (!sheetSvg) { warnToast(t("draw.needdrawing")); return; }
  const svg = $("#paper").querySelector("svg");
  const width = +svg.getAttribute("width") || 1120;
  const height = +svg.getAttribute("height") || 780;
  const scale = 2;

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

$("#drawBtn").onclick = openDrawing;
$("#back3d").onclick = () => $("#sheet").classList.remove("on");
$("#expPng").onclick = exportDrawingPng;

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
    $("#keyBannerText").textContent = t("banner.nobackend");
  }

  if (S.health && S.health.checks) renderDiagRows(S.health.checks);
  renderExamples();
  // Not applyProvider(): that resets the model fields to the provider's
  // defaults and would silently discard a model id someone had typed. Only
  // the text it writes is redrawn.
  if (S.provider) {
    const models = S.provider.models || [];
    $("#optGenModel").placeholder = models.length
      ? t("ph.modelid.count", { n: models.length }) : t("ph.modelid");
    $("#optJudgeModel").placeholder = $("#optGenModel").placeholder;
    $("#providerKey").placeholder = t(S.provider.needs_key
      ? "ph.apikey.memory" : "ph.apikey.none");
    updateProviderNote();
  }
  if (S.genModel || S.judgeModel) setModelLabels(S.genModel, S.judgeModel);
  if (S.codeLines !== undefined) {
    $("#codeStat").textContent = S.codeLines
      ? t("code.stat", { n: S.codeLines }) : t("code.empty");
  }
  if (S.stage) renderStages(S.stage.key, S.stage.detail);
  if (!S.replay) resetPill();
  renderIterations();
  if (S.designPlan) renderPlan(S.designPlan);
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
  Viewer.fit(false);
})();
