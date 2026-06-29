const examples = [
  {
    name: "Mercadona sunflower oil",
    source: "Mercadona",
    url: "https://tienda.mercadona.es/product/4040/aceite-girasol-refinado-02o-hacendado-botella",
  },
  {
    name: "DIA whole milk",
    source: "DIA",
    url: "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6",
  },
  {
    name: "Alcampo whole milk",
    source: "Alcampo",
    url: "https://www.compraonline.alcampo.es/products/auchan-leche-entera-de-vaca-6-x-1-l-producto-alcampo/54178",
  },
  {
    name: "Consum high oleic oil",
    source: "Consum",
    url: "https://tienda.consum.es/es/p/aceite-de-girasol-alto-oleico/7299873",
  },
  {
    name: "Eroski whole milk",
    source: "Eroski",
    url: "https://supermercado.eroski.es/es/productdetail/18672295-leche-entera-del-pais-vasco-eroski-brik-1-litro/",
  },
];

const els = {
  serviceStatus: document.querySelector("#serviceStatus"),
  libraryViewButton: document.querySelector("#libraryViewButton"),
  evaluatorViewButton: document.querySelector("#evaluatorViewButton"),
  libraryView: document.querySelector("#libraryView"),
  evaluatorView: document.querySelector("#evaluatorView"),
  articleSearch: document.querySelector("#articleSearch"),
  articleLanguage: document.querySelector("#articleLanguage"),
  articleCount: document.querySelector("#articleCount"),
  englishCount: document.querySelector("#englishCount"),
  spanishCount: document.querySelector("#spanishCount"),
  articleList: document.querySelector("#articleList"),
  connectorCount: document.querySelector("#connectorCount"),
  examplesList: document.querySelector("#examplesList"),
  scoreForm: document.querySelector("#scoreForm"),
  scoreButton: document.querySelector("#scoreButton"),
  message: document.querySelector("#message"),
  urlMode: document.querySelector("#urlMode"),
  jsonMode: document.querySelector("#jsonMode"),
  urlGroup: document.querySelector("#urlGroup"),
  jsonGroup: document.querySelector("#jsonGroup"),
  productUrl: document.querySelector("#productUrl"),
  productJson: document.querySelector("#productJson"),
  emptyState: document.querySelector("#emptyState"),
  resultView: document.querySelector("#resultView"),
  scoreGauge: document.querySelector("#scoreGauge"),
  scoreValue: document.querySelector("#scoreValue"),
  scoreBand: document.querySelector("#scoreBand"),
  productName: document.querySelector("#productName"),
  scoreComment: document.querySelector("#scoreComment"),
  productSource: document.querySelector("#productSource"),
  productBrand: document.querySelector("#productBrand"),
  scrapedAt: document.querySelector("#scrapedAt"),
  reasonCount: document.querySelector("#reasonCount"),
  reasonsList: document.querySelector("#reasonsList"),
  nutritionCount: document.querySelector("#nutritionCount"),
  nutritionList: document.querySelector("#nutritionList"),
  ingredientsText: document.querySelector("#ingredientsText"),
  sourceLink: document.querySelector("#sourceLink"),
};

let mode = "url";
let currentView = "library";
let articles = [];

function setView(nextView) {
  currentView = nextView;
  els.libraryView.classList.toggle("hidden", currentView !== "library");
  els.evaluatorView.classList.toggle("hidden", currentView !== "evaluator");
  els.libraryViewButton.classList.toggle("active", currentView === "library");
  els.evaluatorViewButton.classList.toggle("active", currentView === "evaluator");
}

function setMode(nextMode) {
  mode = nextMode;
  els.urlMode.classList.toggle("active", mode === "url");
  els.jsonMode.classList.toggle("active", mode === "json");
  els.urlGroup.classList.toggle("hidden", mode !== "url");
  els.jsonGroup.classList.toggle("hidden", mode !== "json");
  setMessage("");
}

function setMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.classList.toggle("error", isError);
}

function setLoading(isLoading) {
  els.scoreButton.disabled = isLoading;
  els.scoreButton.textContent = isLoading ? "Scoring..." : "Score product";
}

function renderExamples() {
  els.examplesList.innerHTML = "";
  examples.forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-button";
    button.innerHTML = `<strong>${example.name}</strong><span>${example.source}</span>`;
    button.addEventListener("click", () => {
      setView("evaluator");
      setMode("url");
      els.productUrl.value = example.url;
      els.productUrl.focus();
    });
    els.examplesList.appendChild(button);
  });
}

async function loadConnectors() {
  try {
    const response = await fetch("/api/connectors");
    const data = await response.json();
    const verified = data.connectors.filter((connector) => connector.status === "verified").length;
    els.connectorCount.textContent = `${verified} verified`;
    els.serviceStatus.textContent = "Service online";
    els.serviceStatus.classList.add("ok");
  } catch (error) {
    els.connectorCount.textContent = `${examples.length} examples`;
    els.serviceStatus.textContent = "Service unavailable";
  }
}

async function loadArticles() {
  try {
    const response = await fetch("/api/articles");
    const data = await response.json();
    articles = data.articles || [];
    updateArticleSummary();
    renderArticles();
  } catch (error) {
    els.articleList.innerHTML = `<p class="message error">Article library could not be loaded.</p>`;
  }
}

function updateArticleSummary() {
  els.articleCount.textContent = articles.length;
  els.englishCount.textContent = articles.filter((article) => article.language === "en").length;
  els.spanishCount.textContent = articles.filter((article) => article.language === "es").length;
}

function renderArticles() {
  const query = els.articleSearch.value.trim().toLowerCase();
  const language = els.articleLanguage.value;
  const filtered = articles.filter((article) => {
    const matchesQuery = !query || `${article.title} ${article.filename}`.toLowerCase().includes(query);
    const matchesLanguage = language === "all" || article.language === language;
    return matchesQuery && matchesLanguage;
  });

  els.articleList.innerHTML = "";
  if (!filtered.length) {
    els.articleList.innerHTML = `<p class="message">No articles match this search.</p>`;
    return;
  }

  filtered.forEach((article) => {
    const card = document.createElement("article");
    card.className = "article-card";

    const meta = document.createElement("div");
    meta.className = "article-meta";

    const language = document.createElement("span");
    language.className = "band";
    language.textContent = languageLabel(article.language);

    const kind = document.createElement("span");
    kind.textContent = article.kind;

    meta.append(language, kind);

    const title = document.createElement("h2");
    title.textContent = article.title;

    const actions = document.createElement("div");
    actions.className = "article-actions";

    const open = document.createElement("a");
    open.className = "primary-button link-button";
    open.href = article.url;
    open.target = "_blank";
    open.rel = "noreferrer";
    open.textContent = "Open PDF";

    actions.append(open);
    card.append(meta, title, actions);
    els.articleList.appendChild(card);
  });
}

function languageLabel(language) {
  if (language === "es") return "Spanish";
  if (language === "en") return "English";
  return "Other";
}

async function submitScore(event) {
  event.preventDefault();
  setMessage("");

  let payload;
  if (mode === "url") {
    const url = els.productUrl.value.trim();
    if (!url) {
      setMessage("Add a product URL first.", true);
      return;
    }
    payload = { url };
  } else {
    try {
      payload = { product: JSON.parse(els.productJson.value) };
    } catch (error) {
      setMessage("The product JSON is not valid.", true);
      return;
    }
  }

  setLoading(true);
  setMessage("Reading supermarket data...");
  try {
    const response = await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "The product could not be scored.");
    }
    renderResult(data);
    setMessage("Score ready.");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setLoading(false);
  }
}

function renderResult(result) {
  const product = result.product;
  els.emptyState.classList.add("hidden");
  els.resultView.classList.remove("hidden");

  els.scoreGauge.style.setProperty("--score", result.score);
  els.scoreValue.textContent = result.score;
  els.scoreBand.textContent = result.band;
  els.scoreBand.className = `band ${bandClass(result.band)}`;
  els.productName.textContent = product.name;
  els.scoreComment.textContent = result.comment;
  els.productSource.textContent = product.source || "-";
  els.productBrand.textContent = product.brand || "-";
  els.scrapedAt.textContent = formatDate(product.scraped_at);

  renderReasons(result.reasons || []);
  renderNutrition(product.nutrition_per_100g || {});
  renderIngredients(product);
}

function bandClass(band) {
  if (band.includes("strong")) return "strong";
  if (band.includes("reasonable")) return "reasonable";
  if (band.includes("weak")) return "weak";
  if (band.includes("avoid")) return "avoid";
  return "mixed";
}

function renderReasons(reasons) {
  els.reasonCount.textContent = `${reasons.length} rules`;
  els.reasonsList.innerHTML = "";
  if (!reasons.length) {
    els.reasonsList.innerHTML = `<p class="message">No rule matched this product.</p>`;
    return;
  }

  reasons.forEach((reason) => {
    const row = document.createElement("div");
    const deltaClass = reason.delta >= 0 ? "positive" : "negative";
    row.className = "reason-row";
    row.innerHTML = `
      <span class="delta ${deltaClass}">${formatDelta(reason.delta)}</span>
      <div><strong>${reason.label}</strong><p>${reason.detail}</p></div>
    `;
    els.reasonsList.appendChild(row);
  });
}

function renderNutrition(nutrition) {
  const entries = Object.entries(nutrition);
  els.nutritionCount.textContent = `${entries.length} values`;
  els.nutritionList.innerHTML = "";
  if (!entries.length) {
    els.nutritionList.innerHTML = `<p class="message">No structured nutrition values found.</p>`;
    return;
  }

  entries.forEach(([key, value]) => {
    const chip = document.createElement("div");
    chip.className = "nutrition-chip";
    chip.innerHTML = `<span>${formatLabel(key)}</span><strong>${formatNumber(value)}</strong>`;
    els.nutritionList.appendChild(chip);
  });
}

function renderIngredients(product) {
  const ingredients = product.ingredients || [];
  els.ingredientsText.textContent = ingredients.length ? ingredients.join(", ") : "No ingredients found.";
  if (product.url) {
    els.sourceLink.href = product.url;
    els.sourceLink.classList.remove("hidden");
  } else {
    els.sourceLink.classList.add("hidden");
  }
}

function formatDelta(delta) {
  return delta > 0 ? `+${delta}` : `${delta}`;
}

function formatNumber(value) {
  if (typeof value !== "number") return value;
  return Number.isInteger(value) ? value.toString() : value.toFixed(2).replace(/\.00$/, "");
}

function formatLabel(key) {
  return key.replace(/_/g, " ");
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

els.libraryViewButton.addEventListener("click", () => setView("library"));
els.evaluatorViewButton.addEventListener("click", () => setView("evaluator"));
els.articleSearch.addEventListener("input", renderArticles);
els.articleLanguage.addEventListener("change", renderArticles);
els.urlMode.addEventListener("click", () => setMode("url"));
els.jsonMode.addEventListener("click", () => setMode("json"));
els.scoreForm.addEventListener("submit", submitScore);

renderExamples();
loadConnectors();
loadArticles();
