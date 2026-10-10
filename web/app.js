/* Guided cases. Numbers are from the local pipeline, not a live model call.
   Evaluation block matches data/last_eval.json from the 60-question bench. */

const STAGES = {
  query: ["User query", "The case the visitor chooses. The page replays a prepared run rather than accepting an open-ended chat."],
  orchestrator: ["Orchestrator", "Classifies the case: regulatory research, a liquidity scenario, or an independent review. It does not answer from memory."],
  search: ["Regulatory search", "Hybrid retrieval over the ECB, EBA and Basel briefings. Passages that reach the answer are the ones cited."],
  scenario: ["Scenario analysis", "Applies a stated shock to outflow amounts and sends the new balance sheet to the ratio function. Run-off weights stay at the regulatory values."],
  calculator: ["Risk metric calculator", "LCR is high-quality liquid assets divided by net cash outflow, after the 75 percent inflow cap. The arithmetic is Python, not the language model."],
  vector: ["Vector index", "BM25 plus a vector index over the briefing chunks. The live site shows passages already retrieved for these three cases."],
  "python-scenario": ["Python", "Recomputes gross outflows, the inflow cap, and net cash outflow under the shock."],
  "python-calc": ["Python", "The same ratio function the reviewer calls again before a number is released."],
  draft: ["Grounded generation", "The answer is written from the retrieved passages and the tool output. When a model key is configured locally, that draft still has to pass the reviewer."],
  reviewer: ["Risk reviewer", "Independently checks whether material claims are supported by the retrieved evidence, and recomputes any ratio."],
  citations: ["Citation check", "Every regulatory sentence in these cases points at a passage in the indexed briefings. A claim without that support is not released."],
  answer: ["Final answer", "Released only when the review clears it. Otherwise the desk withholds the unsupported part and says so."],
};

const EVAL = {
  n: 60,
  note: "Latest local run of the 60-question bench. Fact coverage is the share of expected facts present in the answer. It is not a model-judged faithfulness score.",
  cards: [
    ["Retrieval Recall@5", "92.3%", "Share of the gold passages that appear in the top five retrieved by the full desk."],
    ["Citation correctness", "85.0%", "Share of gold passages actually cited. On unknown instruments, the correct outcome is a refusal."],
    ["Fact coverage", "76.0%", "Share of the expected facts that appear in the desk’s answer."],
    ["Calculation accuracy", "100%", "Share of ratio questions where the reported percentage matches the Python tool."],
  ],
  series: [
    ["Recall@5", [["Closed book", 0], ["Basic RAG", 87.5], ["Hybrid", 81.7], ["Agentic desk", 92.3]]],
    ["Fact coverage", [["Closed book", 5.8], ["Basic RAG", 70.2], ["Hybrid", 61.5], ["Agentic desk", 76.0]]],
    ["Citations", [["Closed book", 0], ["Basic RAG", 67.5], ["Hybrid", 65.8], ["Agentic desk", 85.0]]],
    ["Calculations", [["Closed book", 8.3], ["Basic RAG", 0], ["Hybrid", 0], ["Agentic desk", 100]]],
  ],
  refusal: "On the 8 questions that name an instrument absent from the corpus, the desk refused every time. The other three systems answered all 8.",
};

const CASES = [
  {
    id: "research",
    kicker: "01  Regulatory intelligence",
    label: "Regulatory research",
    question: "What are the ECB expectations for liquidity stress testing?",
    trace: [
      ["Analysing query", "Regulatory research, not a calculation."],
      ["Identified task", "ECB expectations for liquidity stress testing."],
      ["Searching regulatory knowledge base", "ECB Guide to the ILAAP, alongside the binding LCR standard."],
      ["Retrieved relevant passages", "Stress testing beyond 30 days · Survival horizon · ILAAP role."],
      ["Checking citations against passages", "Each sentence below is taken from one of those passages."],
      ["Risk reviewer", "No ratio to recompute. Claims stay inside the cited text."],
      ["Generating evidence-grounded response", "Released with three sources."],
    ],
    paragraphs: [
      "The ECB Guide to the ILAAP treats liquidity stress testing as the bank’s own process, not as a second copy of the LCR return. It expects idiosyncratic, market-wide and combined scenarios, across several time horizons, including horizons longer than the 30-day LCR window. [1]",
      "Institutions are expected to estimate an internal survival horizon, and to hold internal liquidity buffers where the risk profile requires resources above the regulatory minimum. That horizon is not a figure the LCR Delegated Act defines as a single legal minimum. [2]",
      "Public legal minima still come from the CRR and Commission Delegated Regulation (EU) 2015/61. A stress framework that only reproduces the standardised 30-day weights is not the internal test the Guide describes. [3]",
    ],
    sources: [
      ["ECB Guide to the ILAAP", "Stress testing beyond the 30-day ratio", "The ECB Guide expects liquidity stress testing under idiosyncratic, market-wide, and combined scenarios, across several time horizons, including horizons longer than the 30-day LCR window. The standardised LCR scenario remains the regulatory ratio."],
      ["ECB Guide to the ILAAP", "Survival horizon and internal buffers", "The ECB Guide expects institutions to estimate an internal survival horizon and to hold internal liquidity buffers where the risk profile requires resources above the regulatory minimum. The horizon is an internal risk metric. It is not a number defined as a single EU legal minimum in the LCR Delegated Act."],
      ["ECB Guide to the ILAAP", "Role of the ILAAP, and the stress-testing section", "Public legal minima still come from the CRR and Commission Delegated Regulation (EU) 2015/61. A stress framework that only reproduces the LCR weights at a 30 calendar day point is not the internal test the Guide describes."],
    ],
  },
  {
    id: "scenario",
    kicker: "02  Liquidity stress scenario",
    label: "Liquidity scenario",
    question: "How would a 20% increase in wholesale deposit outflows affect the bank's liquidity position?",
    trace: [
      ["Analysing query", "A shock to wholesale outflows, with a ratio to recompute."],
      ["Identified task", "Liquidity scenario analysis."],
      ["Searching regulatory knowledge base", "LCR formula, the 75 percent inflow cap, and the role of the 30-day ratio."],
      ["Retrieved relevant LCR requirements", "CRR / Commission Delegated Regulation (EU) 2015/61 · BCBS 238 · ECB ILAAP Guide."],
      ["Calling liquidity scenario tool", "Wholesale deposit outflows are €7.5bn of the €12.0bn gross outflow. The tool applies +20% to that slice only."],
      ["Recalculating stressed net cash outflow", "20% of €7.5bn is €1.5bn. Gross outflows become €13.5bn. Net cash outflow moves from €9.0bn to €10.5bn."],
      ["Risk reviewer checking result", "Independent recalculation matches 133.3 percent and 114.3 percent."],
      ["Generating evidence-grounded response", "Released. The ratio stays above 100 percent. That is not a statement about every internal stress."],
    ],
    paragraphs: [
      "Wholesale deposit outflows are €7.5bn inside gross outflows of €12.0bn. A 20 percent increase on that slice, not on the whole outflow stock, adds €1.5bn. Other outflows stay at €4.5bn. High-quality liquid assets stay at €12.0bn, and the liquidity coverage ratio moves from 133.3 percent to 114.3 percent.",
      "Baseline inflows recognised after the 75 percent cap are €3.0bn, so net cash outflow is €9.0bn. After the shock, gross outflows are €13.5bn, recognised inflows are still €3.0bn, and net cash outflow is €10.5bn. [1]",
      "Both results are at or above the regulatory minimum of 100 percent. [2] The narrower buffer is not evidence that the bank is comfortable under all stress scenarios. The ECB Guide still expects internal tests beyond the 30-day LCR window. [3]",
    ],
    sources: [
      ["LCR net cash outflows", "The formula and the 75 percent inflow cap", "The liquidity coverage ratio is HQLA divided by net cash outflow. The inflow cap is 75 percent of total expected cash outflows. Inflows above that cap are excluded."],
      ["Liquidity coverage ratio — framework", "The binding 100 percent minimum", "The minimum LCR is 100 percent. An LCR below 100 percent means the buffer does not cover modelled net outflows and is a breach of the regulatory minimum."],
      ["ECB Guide to the ILAAP", "Stress testing beyond the 30-day ratio", "The ECB Guide expects liquidity stress testing under idiosyncratic, market-wide, and combined scenarios, across several time horizons, including horizons longer than the 30-day LCR window."],
    ],
    calculation: {
      base: [["HQLA", "€12.0bn"], ["Wholesale deposit outflows", "€7.5bn"], ["Other outflows", "€4.5bn"], ["Gross outflows", "€12.0bn"], ["Inflows recognised", "€3.0bn"], ["Net cash outflow", "€9.0bn"], ["LCR", "133.3%"]],
      stress: [["Wholesale deposit outflows", "€7.5bn"], ["Scenario shock", "+20%"], ["Additional outflow", "€1.5bn"], ["Gross outflows", "€13.5bn"], ["Inflows recognised", "€3.0bn"], ["Net cash outflow", "€10.5bn"], ["LCR", "114.3%"]],
    },
  },
  {
    id: "review",
    kicker: "03  Independent risk review",
    label: "Risk review",
    question: "Review this liquidity assessment and identify unsupported regulatory claims.",
    quote: "The bank has an LCR of 108%, therefore its liquidity position remains comfortable under all stress scenarios.",
    context: "Supplied figures: HQLA €10.8bn and net cash outflow €10.0bn.",
    trace: [
      ["Analysing query", "A finished assessment, to be challenged rather than rewritten from scratch."],
      ["Identified task", "Independent risk review."],
      ["Claim extraction", "Three claims: the ratio, the word comfortable, and coverage of all stress scenarios."],
      ["Evidence retrieval", "LCR definition and minimum, plus ECB expectations on internal stress and risk appetite."],
      ["Quantitative validation", "€10.8bn / €10.0bn = 108.0 percent. The figure matches."],
      ["Regulatory verification", "Comfortable is not a regulatory category. All stress scenarios is not supported by the retrieved passages."],
      ["Risk reviewer", "Do not release the sentence as written."],
      ["Final assessment", "Keep the 108.0 percent. Remove the comfort judgement and the universal stress claim."],
    ],
    claims: [
      ["ok", "Claim 1 · LCR of 108%", "Supported by the supplied figures. €10.8bn of HQLA divided by €10.0bn of net cash outflow is 108.0 percent."],
      ["warn", "Claim 2 · “comfortable”", "Not a category in the LCR standard. The ECB Guide expects an internal risk appetite and limits. A buffer above 100 percent does not, by itself, mean comfortable. [2]"],
      ["bad", "Claim 3 · “under all stress scenarios”", "Unsupported. The retrieved ECB material expects several scenarios and horizons, including horizons longer than 30 days. One reported LCR does not evidence all of them. [3]"],
    ],
    paragraphs: [
      "Do not release the assessment as written. The ratio can stand. The conclusion drawn from it cannot.",
      "The 108.0 percent figure matches the supplied inputs, and it is above the 100 percent minimum. [1] Nothing retrieved defines “comfortable”, and nothing retrieved turns one LCR into evidence for every stress scenario.",
    ],
    sources: [
      ["LCR net cash outflows", "The ratio", "The liquidity coverage ratio is HQLA divided by net cash outflow. On the supplied inputs that quotient is 108.0 percent."],
      ["ECB Guide to the ILAAP", "Liquidity risk appetite and internal limits", "The ECB expects the management body to set a liquidity risk appetite that is specific, approved, and translated into limits. A limit framework that only restates the 100 percent LCR minimum does not meet the intention of an internal appetite."],
      ["ECB Guide to the ILAAP", "Stress testing beyond the 30-day ratio", "The ECB Guide expects liquidity stress testing under idiosyncratic, market-wide, and combined scenarios, across several time horizons, including horizons longer than the 30-day LCR window."],
    ],
  },
];

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let runToken = 0;

const prompts = document.getElementById("prompts");
const thread = document.getElementById("thread");
const trace = document.getElementById("trace");
const caption = document.getElementById("trace-caption");

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function withCites(text) {
  return escapeHtml(text).replace(/\[(\d+)\]/g, '<button type="button" class="cite-mark" data-n="$1">$1</button>');
}

function wait(ms) {
  if (reduced) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function show(name) {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-on", view.id === `view-${name}`);
  });
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.classList.toggle("is-on", link.dataset.nav === name);
  });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

document.querySelectorAll("[data-nav]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    show(link.dataset.nav);
  });
});

const promptButtons = new Map();
CASES.forEach((item) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = item.label;
  button.addEventListener("click", () => play(item, button));
  promptButtons.set(item.id, button);
  prompts.appendChild(button);
});

document.querySelectorAll("[data-case]").forEach((card) => {
  card.addEventListener("click", () => {
    const item = CASES.find((entry) => entry.id === card.dataset.case);
    const button = item && promptButtons.get(item.id);
    if (!item || !button) return;
    show("cases");
    window.scrollTo(0, 0);
    play(item, button);
  });
});

async function play(item, button) {
  const token = ++runToken;
  prompts.querySelectorAll("button").forEach((el) => el.classList.toggle("is-on", el === button));
  caption.textContent = item.kicker;
  trace.innerHTML = "";
  thread.innerHTML = `<article class="bubble user"><p>${escapeHtml(item.question)}</p>${item.quote ? `<p class="quote">${escapeHtml(item.quote)}</p>` : ""}</article>`;
  for (let index = 0; index < item.trace.length; index += 1) {
    if (token !== runToken) return;
    const step = document.createElement("li");
    step.className = "wait";
    step.innerHTML = `<i></i><strong>${escapeHtml(item.trace[index][0])}</strong><p>${escapeHtml(item.trace[index][1])}</p>`;
    trace.appendChild(step);
    step.scrollIntoView({ block: "nearest" });
    await wait(index === 0 ? 220 : 380);
    if (token !== runToken) return;
    step.classList.remove("wait");
    step.classList.add("is-on");
  }
  if (token !== runToken) return;
  thread.insertAdjacentHTML("beforeend", renderResult(item));
  const result = thread.lastElementChild;
  result.querySelectorAll(".cite-mark").forEach((mark) => {
    mark.addEventListener("click", () => openPanel(result, "sources", mark.dataset.n));
  });
  result.querySelectorAll("[data-panel]").forEach((control) => {
    control.addEventListener("click", () => openPanel(result, control.dataset.panel));
  });
  result.scrollIntoView({ block: "nearest" });
}

function renderResult(item) {
  const claims = (item.claims || []).map(([tone, title, body]) => `
    <article class="claim ${tone}"><i>${tone === "ok" ? "✓" : tone === "warn" ? "!" : "×"}</i><div><b>${escapeHtml(title)}</b><p>${withCites(body)}</p></div></article>
  `).join("");
  const paragraphs = item.paragraphs.map((text) => `<p>${withCites(text)}</p>`).join("");
  const sources = item.sources.map(([title, heading, excerpt], index) => `
    <article class="cite-card" id="source-${index + 1}">
      <header><span>${index + 1}</span><span>${escapeHtml(title)}</span></header>
      <p><strong>${escapeHtml(heading)}</strong></p>
      <p>${escapeHtml(excerpt)}</p>
    </article>
  `).join("");
  const calculation = item.calculation ? `
    <div class="calc-grid">
      <div><h3>Baseline</h3><dl>${rows(item.calculation.base)}</dl></div>
      <div><h3>Stress scenario</h3><dl>${rows(item.calculation.stress)}</dl></div>
    </div>` : "";
  const reasoning = item.trace.map(([title, detail]) => `<li><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></li>`).join("");
  const toggles = [
    `<button type="button" data-panel="sources">Sources (${item.sources.length})</button>`,
    calculation ? `<button type="button" data-panel="calculation">View calculation</button>` : "",
    `<button type="button" data-panel="reasoning">View agent record</button>`,
  ].join("");
  return `
    <article class="bubble desk">
      ${item.context ? `<p class="quiet">${escapeHtml(item.context)}</p>` : ""}
      ${claims}
      ${paragraphs}
      <div class="drawers">${toggles}</div>
      <div class="panel" data-sheet="sources"><div class="citations">${sources}</div></div>
      <div class="panel" data-sheet="calculation">${calculation}</div>
      <div class="panel" data-sheet="reasoning"><ol class="reason">${reasoning}</ol></div>
    </article>`;
}

function rows(pairs) {
  return pairs.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("");
}

function openPanel(result, name, sourceNumber) {
  result.querySelectorAll("[data-panel]").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.panel === name);
  });
  result.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("is-on", panel.dataset.sheet === name);
  });
  if (sourceNumber) {
    const card = result.querySelector(`#source-${sourceNumber}`);
    result.querySelectorAll(".cite-card").forEach((el) => el.classList.remove("is-hot"));
    if (card) {
      card.classList.add("is-hot");
      card.scrollIntoView({ block: "nearest" });
    }
  }
}

function bindArchitecture() {
  const title = document.getElementById("stage-title");
  const body = document.getElementById("stage-body");
  document.querySelectorAll(".node").forEach((node) => {
    const showStage = () => {
      document.querySelectorAll(".node").forEach((el) => el.classList.toggle("is-hot", el === node));
      const [heading, copy] = STAGES[node.dataset.stage];
      title.textContent = heading;
      body.textContent = copy;
    };
    node.addEventListener("mouseenter", showStage);
    node.addEventListener("focus", showStage);
    node.addEventListener("click", showStage);
  });
}

function renderEval() {
  document.getElementById("metric-grid").innerHTML = EVAL.cards.map(([label, value, copy]) => `
    <article class="metric"><span class="kicker">${escapeHtml(label)}</span><b>${escapeHtml(value)}</b><p>${escapeHtml(copy)}</p></article>
  `).join("");
  const keyOf = (label) => label.toLowerCase().includes("agentic") ? "agentic" : label.toLowerCase().includes("hybrid") ? "hybrid" : label.toLowerCase().includes("basic") ? "basic" : "closed";
  document.getElementById("chart").innerHTML = EVAL.series.map(([name, rows]) => `
    <div class="series"><span>${escapeHtml(name)}</span><div class="bars">${rows.map(([label, value]) => `
      <div class="bar-row ${keyOf(label)}"><span>${escapeHtml(label)}</span><div class="bar"><i style="width:${value}%"></i></div><span>${value.toFixed(1)}%</span></div>
    `).join("")}</div></div>
  `).join("");
  document.getElementById("chart-note").textContent = "Hybrid retrieval did not beat keyword search on Recall@5: 81.7% versus 87.5%. On this small, terminology-heavy regulatory corpus, lexical retrieval remained particularly effective. Hybrid retrieval introduced additional semantic matches that did not always correspond to the gold passage. We tested it rather than assuming it was better.";
  document.getElementById("eval-footnote").textContent = `${EVAL.note} ${EVAL.refusal}`;
}

bindArchitecture();
renderEval();
show((location.hash || "#overview").slice(1).replace("demo", "cases"));
