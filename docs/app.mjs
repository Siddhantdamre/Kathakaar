import { analyzeDraft, summarizeAnalysis } from "./engine.mjs";

const EXAMPLE = {
  draft:
    "Hampi served as the capital of the Vijayanagara Empire in the fourteenth century. "
    + "The archaeological area contains more than 1,600 surviving remains. "
    + "The Stone Chariot was built in 1565 inside the Vittala Temple complex. "
    + "It is the largest temple complex in Asia.",
  sources: [
    {
      title: "Hampi archaeological area note",
      url: "https://whc.unesco.org/en/list/241/",
      text:
        "Hampi served as the capital of the Vijayanagara Empire from the fourteenth century. "
        + "The archaeological area contains more than 1,600 surviving remains, including forts, "
        + "riverside features, temples, shrines, halls, and gateways.",
    },
    {
      title: "Vittala Temple monument note",
      url: "https://asi.nic.in/",
      text:
        "The Stone Chariot stands inside the Vittala Temple complex. "
        + "The monument is a shrine designed in the form of a ceremonial chariot and is one "
        + "of the best-known structures at Hampi.",
    },
  ],
};

const form = document.querySelector("#analysis-form");
const sourceList = document.querySelector("#source-list");
const template = document.querySelector("#source-template");
const emptyState = document.querySelector("#empty-state");
const resultsShell = document.querySelector("#results-shell");
let currentAnalysis = null;

function updateSourceNumbers() {
  [...sourceList.querySelectorAll(".source-card")].forEach((card, index) => {
    card.querySelector(".source-number").textContent = `Source ${index + 1}`;
    card.querySelector(".remove-source").disabled = sourceList.children.length === 1;
  });
}

function addSource(source = {}) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector(".source-card");
  card.querySelector(".source-title").value = source.title ?? "";
  card.querySelector(".source-url").value = source.url ?? "";
  card.querySelector(".source-text").value = source.text ?? "";
  card.querySelector(".remove-source").addEventListener("click", () => {
    card.remove();
    updateSourceNumbers();
  });
  sourceList.append(fragment);
  updateSourceNumbers();
}

function collectSources() {
  return [...sourceList.querySelectorAll(".source-card")].map((card) => ({
    title: card.querySelector(".source-title").value,
    url: card.querySelector(".source-url").value,
    text: card.querySelector(".source-text").value,
  }));
}

function loadExample() {
  document.querySelector("#draft").value = EXAMPLE.draft;
  sourceList.replaceChildren();
  EXAMPLE.sources.forEach(addSource);
  document.querySelector("#draft").focus();
}

function statusLabel(status) {
  if (status === "supported") return "Supported";
  if (status === "review") return "Review";
  return "Unsupported";
}

function buildTokenList(claim) {
  const tokens = [
    ...claim.unsupportedNumbers.map((value) => `number/date: ${value}`),
    ...claim.unsupportedEntities.map((value) => `entity: ${value}`),
    ...claim.unsupportedTerms.slice(0, 6).map((value) => `term: ${value}`),
  ];
  if (tokens.length === 0) return null;
  const list = document.createElement("div");
  list.className = "token-list";
  for (const value of tokens) {
    const token = document.createElement("span");
    token.className = "token";
    token.textContent = value;
    list.append(token);
  }
  return list;
}

function claimElement(claim, index) {
  const article = document.createElement("article");
  article.className = `claim ${claim.status}`;
  const rail = document.createElement("div");
  rail.className = "claim-rail";
  const body = document.createElement("div");
  body.className = "claim-main";

  const top = document.createElement("div");
  top.className = "claim-top";
  const text = document.createElement("p");
  text.className = "claim-text";
  text.textContent = `${index + 1}. ${claim.claim}`;
  const status = document.createElement("span");
  status.className = "claim-status";
  status.textContent = `${statusLabel(claim.status)} ${Math.round(claim.score * 100)}%`;
  top.append(text, status);

  const reason = document.createElement("p");
  reason.className = "claim-reason";
  reason.textContent = claim.reason;
  body.append(top, reason);

  if (claim.evidence) {
    const evidence = document.createElement("div");
    evidence.className = "evidence";
    const evidenceLabel = document.createElement("div");
    evidenceLabel.className = "evidence-label";
    const title = document.createElement("span");
    title.textContent = "Best evidence";
    evidenceLabel.append(title);
    if (claim.sourceUrl) {
      const link = document.createElement("a");
      link.href = claim.sourceUrl;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = claim.sourceTitle;
      evidenceLabel.append(link);
    } else {
      const source = document.createElement("span");
      source.textContent = claim.sourceTitle;
      evidenceLabel.append(source);
    }
    const quote = document.createElement("blockquote");
    quote.textContent = claim.evidence;
    evidence.append(evidenceLabel, quote);
    body.append(evidence);
  }

  const tokenList = buildTokenList(claim);
  if (tokenList) body.append(tokenList);
  article.append(rail, body);
  return article;
}

function render(analysis) {
  currentAnalysis = analysis;
  emptyState.classList.add("hidden");
  resultsShell.classList.remove("hidden");
  document.querySelector("#audit-subtitle").textContent =
    `${analysis.claimCount} claims checked against ${analysis.sourceCount} source(s)`;

  const gate = document.querySelector("#publish-gate");
  const passed = analysis.publishGate === "pass";
  gate.textContent = passed ? "Publish gate passed" : "Hold publish";
  gate.classList.toggle("pass", passed);

  document.querySelector("#metric-grounded").textContent =
    `${Math.round(analysis.groundingScore * 100)}%`;
  document.querySelector("#metric-supported").textContent = analysis.supportedCount;
  document.querySelector("#metric-review").textContent = analysis.reviewCount;
  document.querySelector("#metric-unsupported").textContent = analysis.unsupportedCount;
  document.querySelector("#coverage-fill").style.width =
    `${Math.round(analysis.groundingScore * 100)}%`;
  document.querySelector("#claims").replaceChildren(
    ...analysis.claims.map(claimElement),
  );
  resultsShell.scrollIntoView({ behavior: "smooth", block: "start" });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    render(analyzeDraft(document.querySelector("#draft").value, collectSources()));
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "Could not analyze the draft.");
  }
});

document.querySelector("#add-source").addEventListener("click", () => addSource());
document.querySelector("#example-button").addEventListener("click", loadExample);
document.querySelector("#reset-button").addEventListener("click", () => {
  form.reset();
  sourceList.replaceChildren();
  addSource();
  currentAnalysis = null;
  resultsShell.classList.add("hidden");
  emptyState.classList.remove("hidden");
});

document.querySelector("#copy-button").addEventListener("click", async () => {
  if (!currentAnalysis) return;
  const details = currentAnalysis.claims.map(
    (claim, index) =>
      `${index + 1}. [${statusLabel(claim.status)}] ${claim.claim}\n`
      + `   ${claim.reason}\n`
      + `   Evidence: ${claim.evidence || "None"}`,
  ).join("\n\n");
  await navigator.clipboard.writeText(`${summarizeAnalysis(currentAnalysis)}\n\n${details}`);
  const button = document.querySelector("#copy-button");
  const original = button.textContent;
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = original; }, 1200);
});

document.querySelector("#download-button").addEventListener("click", () => {
  if (!currentAnalysis) return;
  const blob = new Blob([JSON.stringify(currentAnalysis, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "kathakaar-claim-audit.json";
  anchor.click();
  URL.revokeObjectURL(url);
});

document.querySelector("#print-button").addEventListener("click", () => window.print());

addSource();
