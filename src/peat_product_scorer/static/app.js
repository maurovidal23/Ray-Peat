const predefinedSearches = [
  { label: "Milk", query: "leche" },
  { label: "Yoghurt", query: "yogur" },
  { label: "Cheese", query: "queso" },
  { label: "Juice", query: "zumo" },
  { label: "Gelatin", query: "gelatina" },
  { label: "Butter", query: "mantequilla" },
  { label: "Olive oil", query: "aceite oliva" },
  { label: "Chocolate", query: "chocolate" },
];

const examples = [
  {
    name: "Eroski whole milk",
    source: "Eroski",
    url: "https://supermercado.eroski.es/es/productdetail/18672295-leche-entera-del-pais-vasco-eroski-brik-1-litro/",
  },
];

const EXPLANATIONS = {
  "nutrition-profile": {
    label: "Nutrition profile",
    text: "Compares sugars, protein, fat, salt and related nutrient values with the Ray Peat-inspired thresholds.",
  },
  "ingredient-profile": {
    label: "Ingredient profile",
    text: "Applies ingredient rules such as dairy, fruit, gelatin, seed oils, soy, gums, phosphates and fortified iron.",
  },
  "processing-profile": {
    label: "Processing profile",
    text: "Scores how heavily the product is processed, using ingredient count and processing markers in the ingredient list.",
  },
  "mineral-fat": {
    label: "Mineral and fat quality",
    text: "Weighs calcium and phosphorus balance plus the quality and context of the product's fat profile.",
  },
  "evidence-quality": {
    label: "Evidence quality",
    text: "Measures how complete and trustworthy the ingredient and nutrition evidence is before the product can be scored.",
  },
  weight: {
    label: "Weight",
    text: "The share of the overall score contributed by this component. Weights add up to 100% across all components.",
  },
  band: {
    label: "Band",
    text: "The plain-language range for the final score, from strong fit through reasonable, mixed, weak and avoid.",
  },
  confidence: {
    label: "Confidence",
    text: "How much structured evidence supports the result. Lower confidence means more of the product data was missing.",
  },
};

const EXPLANATION_ALIASES = {
  "nutrition-profile": "nutrition-profile",
  "ingredient-profile": "ingredient-profile",
  "processing-profile": "processing-profile",
  "mineral-fat-quality-profile": "mineral-fat",
  "mineral-and-fat-quality": "mineral-fat",
  "mineral-fat": "mineral-fat",
  "evidence-quality": "evidence-quality",
  weight: "weight",
  band: "band",
  confidence: "confidence",
};

const els = {
  serviceStatus: document.querySelector("#serviceStatus"),
  viewEyebrow: document.querySelector("#viewEyebrow"),
  libraryViewButton: document.querySelector("#libraryViewButton"),
  evaluatorViewButton: document.querySelector("#evaluatorViewButton"),
  bestProductsViewButton: document.querySelector("#bestProductsViewButton"),
  libraryView: document.querySelector("#libraryView"),
  evaluatorView: document.querySelector("#evaluatorView"),
  bestProductsView: document.querySelector("#bestProductsView"),
  articleSearch: document.querySelector("#articleSearch"),
  articleLanguage: document.querySelector("#articleLanguage"),
  articleCount: document.querySelector("#articleCount"),
  englishCount: document.querySelector("#englishCount"),
  spanishCount: document.querySelector("#spanishCount"),
  articleList: document.querySelector("#articleList"),
  articleReader: document.querySelector("#articleReader"),
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
  evaluatorTitle: document.querySelector("#evaluatorTitle"),
  scoreGauge: document.querySelector("#scoreGauge"),
  scoreValue: document.querySelector("#scoreValue"),
  scoreBand: document.querySelector("#scoreBand"),
  productName: document.querySelector("#productName"),
  scoreComment: document.querySelector("#scoreComment"),
  scoreError: document.querySelector("#scoreError"),
  productSource: document.querySelector("#productSource"),
  productBrand: document.querySelector("#productBrand"),
  scrapedAt: document.querySelector("#scrapedAt"),
  productCategory: document.querySelector("#productCategory"),
  scoreConfidence: document.querySelector("#scoreConfidence"),
  componentCount: document.querySelector("#componentCount"),
  componentList: document.querySelector("#componentList"),
  warningList: document.querySelector("#warningList"),
  reasonCount: document.querySelector("#reasonCount"),
  reasonsList: document.querySelector("#reasonsList"),
  nutritionCount: document.querySelector("#nutritionCount"),
  nutritionList: document.querySelector("#nutritionList"),
  ingredientsText: document.querySelector("#ingredientsText"),
  sourceLink: document.querySelector("#sourceLink"),
  presetSearches: document.querySelector("#presetSearches"),
  bestProductsForm: document.querySelector("#bestProductsForm"),
  bestProductsQuery: document.querySelector("#bestProductsQuery"),
  bestProductsProvider: document.querySelector("#bestProductsProvider"),
  bestProductsLimit: document.querySelector("#bestProductsLimit"),
  bestProductsButton: document.querySelector("#bestProductsButton"),
  bestProductsMessage: document.querySelector("#bestProductsMessage"),
  bestProductsList: document.querySelector("#bestProductsList"),
};

let mode = "url";
let currentView = initialView();
let articles = [];
let selectedArticleId = articleIdFromLocation();
let selectedLanguage = new URLSearchParams(window.location.search).get("lang") || null;

function initialView() {
  const params = new URLSearchParams(window.location.search);
  if (window.location.pathname.startsWith("/products") || params.get("view") === "best") return "best";
  if (window.location.pathname.startsWith("/evaluator")) return "evaluator";
  return "library";
}

function articleIdFromLocation() {
  const match = window.location.pathname.match(/^\/articles\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function setView(nextView) {
  currentView = nextView;
  document.body.dataset.view = nextView;
  els.libraryView.classList.toggle("hidden", currentView !== "library");
  els.evaluatorView.classList.toggle("hidden", currentView !== "evaluator");
  els.bestProductsView.classList.toggle("hidden", currentView !== "best");
  els.libraryViewButton.classList.toggle("active", currentView === "library");
  els.evaluatorViewButton.classList.toggle("active", currentView === "evaluator");
  els.bestProductsViewButton.classList.toggle("active", currentView === "best");
  updateHeroForView(currentView);
}

function updateHeroForView(view) {
  if (view === "best") {
    els.viewEyebrow.textContent = "Product browser";
    els.evaluatorTitle.textContent = "Best products.";
    document.title = "Best Products / Ray Peat Product Evaluator";
    return;
  }
  if (view === "evaluator") {
    els.viewEyebrow.textContent = "Product scoring";
    els.evaluatorTitle.textContent = "Product evaluator.";
    document.title = "Ray Peat Product Evaluator";
    return;
  }
  els.viewEyebrow.textContent = "Article archive";
  els.evaluatorTitle.textContent = "Ray Peat papers.";
}

function articleUrl(articleId, language = selectedLanguage) {
  if (!articleId || articleId === "undefined") return "/articles";
  const params = language ? `?lang=${encodeURIComponent(language)}` : "";
  return `/articles/${encodeURIComponent(articleId)}${params}`;
}

function navigateArticle(articleId, language = selectedLanguage) {
  if (!articleId || articleId === "undefined") return;
  selectedArticleId = articleId;
  selectedLanguage = language;
  history.pushState({ articleId, language }, "", articleUrl(articleId, language));
  renderArticles();
  renderArticleDetail(articleId, language);
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

function scoreErrorMessage(message) {
  const detail = String(message || "");
  if (/evidence incomplete/i.test(detail)) {
    return "This product page did not include enough ingredient and nutrition data to score. Try another product.";
  }
  if (/product extraction failed/i.test(detail)) {
    return "This product page could not be read, so it was not scored. Try another URL.";
  }
  if (/supermarket request failed/i.test(detail)) {
    return "The supermarket did not return this product page. Try another product or URL.";
  }
  return detail || "The product could not be scored.";
}

function setLoading(isLoading) {
  els.scoreButton.disabled = isLoading;
  els.scoreButton.textContent = isLoading ? "Scoring..." : "Score product";
}

function textElement(tagName, text, className = "") {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text === null || text === undefined ? "" : String(text);
  return element;
}

function renderInlineMessage(container, text, isError = false) {
  const message = textElement("p", text, `message${isError ? " error" : ""}`);
  container.replaceChildren(message);
}

function renderEmptyState(container, heading, detail) {
  const emptyState = document.createElement("div");
  emptyState.className = "empty-state best-empty";
  emptyState.append(textElement("h2", heading), textElement("p", detail));
  container.replaceChildren(emptyState);
}

function safeText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text || fallback;
}

function safeNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function explanationKey(value) {
  const normalized = safeText(value)
    .toLowerCase()
    .replace(/_/g, "-")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
  return EXPLANATION_ALIASES[normalized] || normalized;
}

function explanationFor(value) {
  return EXPLANATIONS[explanationKey(value)] || null;
}

function formatWeight(value) {
  const number = safeNumber(value);
  if (number === null) return "Unknown weight";
  return `${formatNumber(Number((number * 100).toFixed(1)))}% weight`;
}

function formatWeightMultiplier(value) {
  const number = safeNumber(value);
  return number === null ? "?" : formatNumber(number);
}

function formatConfidence(value) {
  const number = safeNumber(value);
  return number === null ? "Unknown confidence" : `${formatNumber(number)}/100 confidence`;
}

function formatComponentScore(value) {
  const number = safeNumber(value);
  return number === null ? "-" : formatNumber(number);
}

let explanationPopover = null;
let activeExplanationTrigger = null;

function ensureExplanationPopover() {
  if (explanationPopover) return explanationPopover;
  explanationPopover = document.createElement("div");
  explanationPopover.id = "explanationPopover";
  explanationPopover.className = "explanation-popover";
  explanationPopover.setAttribute("role", "tooltip");
  explanationPopover.setAttribute("aria-hidden", "true");
  explanationPopover.hidden = true;
  document.body.appendChild(explanationPopover);
  return explanationPopover;
}

function renderExplanationContent(entry) {
  const popover = ensureExplanationPopover();
  popover.replaceChildren(
    textElement("strong", entry.label, "explanation-popover-title"),
    textElement("p", entry.text, "explanation-popover-text"),
  );
  return popover;
}

function positionExplanationPopover(trigger) {
  const popover = ensureExplanationPopover();
  const rect = trigger.getBoundingClientRect();
  const margin = 12;
  const gap = 8;
  const popoverRect = popover.getBoundingClientRect();
  let left = rect.left + rect.width / 2 - popoverRect.width / 2;
  let top = rect.bottom + gap;
  left = Math.max(margin, Math.min(left, window.innerWidth - popoverRect.width - margin));
  if (top + popoverRect.height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - popoverRect.height - gap);
  }
  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
}

function openExplanation(trigger) {
  if (!trigger || !trigger.dataset) return;
  const entry = explanationFor(trigger.dataset.explain);
  if (!entry) return;
  if (activeExplanationTrigger && activeExplanationTrigger !== trigger) {
    activeExplanationTrigger.removeAttribute("aria-describedby");
  }
  const popover = renderExplanationContent(entry);
  activeExplanationTrigger = trigger;
  trigger.setAttribute("aria-describedby", popover.id);
  popover.hidden = false;
  popover.setAttribute("aria-hidden", "false");
  positionExplanationPopover(trigger);
}

function closeExplanation(trigger = null) {
  if (trigger && activeExplanationTrigger !== trigger) return;
  if (activeExplanationTrigger) {
    activeExplanationTrigger.removeAttribute("aria-describedby");
  }
  activeExplanationTrigger = null;
  if (!explanationPopover) return;
  explanationPopover.hidden = true;
  explanationPopover.setAttribute("aria-hidden", "true");
}

function explanationTriggerFromEvent(event) {
  const target = event.target;
  if (!target || typeof target.closest !== "function") return null;
  if (target.closest(".component-breakdown")) return null;
  return target.closest("[data-explain]");
}

function bindExplanationEvents() {
  document.addEventListener("mouseover", (event) => {
    const trigger = explanationTriggerFromEvent(event);
    if (trigger && trigger !== activeExplanationTrigger) openExplanation(trigger);
  });
  document.addEventListener("mouseout", (event) => {
    const trigger = explanationTriggerFromEvent(event);
    if (!trigger) return;
    const next = event.relatedTarget;
    if (next && typeof trigger.contains === "function" && trigger.contains(next)) return;
    closeExplanation(trigger);
  });
  document.addEventListener("focusin", (event) => {
    const trigger = explanationTriggerFromEvent(event);
    if (trigger) openExplanation(trigger);
  });
  document.addEventListener("focusout", (event) => {
    const trigger = explanationTriggerFromEvent(event);
    if (trigger) closeExplanation(trigger);
  });
  document.addEventListener("click", (event) => {
    const trigger = explanationTriggerFromEvent(event);
    if (!trigger) return;
    // Focus/hover may precede a touch-generated click; opening is idempotent.
    openExplanation(trigger);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeExplanation();
  });
  document.addEventListener("mouseleave", () => closeExplanation());
  window.addEventListener("resize", () => {
    if (activeExplanationTrigger) positionExplanationPopover(activeExplanationTrigger);
  });
  window.addEventListener(
    "scroll",
    () => {
      if (activeExplanationTrigger) positionExplanationPopover(activeExplanationTrigger);
    },
    { passive: true },
  );
}

function contributionsFor(component) {
  const raw = component?.contributions;
  if (!Array.isArray(raw) || raw.length === 0) return [];
  const valid = raw.every(
    (entry) => entry && typeof entry === "object" && !Array.isArray(entry),
  );
  return valid ? raw : [];
}

let breakdownSequence = 0;

function buildContributionBreakdown(component) {
  const contributions = contributionsFor(component);
  if (!contributions.length) return null;

  breakdownSequence += 1;
  const panelId = `component-breakdown-${breakdownSequence}`;
  const section = document.createElement("section");
  section.className = "component-breakdown";

  const toggle = textElement("button", "Show scoring arithmetic", "breakdown-toggle");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", panelId);

  const panel = document.createElement("div");
  panel.id = panelId;
  panel.className = "breakdown-panel";
  panel.hidden = true;

  panel.appendChild(
    textElement(
      "p",
      `Base score: ${formatComponentScore(component?.base_score)}`,
      "breakdown-base",
    ),
  );

  contributions.forEach((contribution) => {
    const row = document.createElement("div");
    row.className = "breakdown-entry";
    const delta = safeNumber(contribution?.delta);
    const deltaText = delta === null ? "±0" : formatDelta(delta);
    const deltaClass = delta === null || delta >= 0 ? "positive" : "negative";
    const detail = document.createElement("div");
    detail.append(
      textElement("strong", safeText(contribution?.label, "Adjustment")),
      textElement("p", safeText(contribution?.detail, "No detail provided.")),
    );
    row.append(textElement("span", deltaText, `delta ${deltaClass}`), detail);
    panel.appendChild(row);
  });

  const score = safeNumber(component?.score);
  const weight = safeNumber(component?.weight);
  const weightedEffect =
    score === null || weight === null ? "?" : formatNumber(Number((score * weight).toFixed(2)));
  panel.appendChild(
    textElement(
      "p",
      `Weighted effect: ${formatComponentScore(component?.score)} × ${formatWeightMultiplier(component?.weight)} = ${weightedEffect}`,
      "breakdown-effect",
    ),
  );

  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    panel.hidden = expanded;
    toggle.textContent = expanded ? "Show scoring arithmetic" : "Hide scoring arithmetic";
  });

  section.append(toggle, panel);
  return section;
}

function renderPresetSearches() {
  els.presetSearches.replaceChildren();
  predefinedSearches.forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-search";
    button.append(textElement("strong", preset.label), textElement("span", preset.query));
    button.addEventListener("click", () => {
      els.bestProductsQuery.value = preset.query;
      submitBestProducts(new Event("submit"));
    });
    els.presetSearches.appendChild(button);
  });
}

function renderExamples() {
  els.examplesList.replaceChildren();
  examples.forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-button";
    button.append(textElement("strong", example.name), textElement("span", example.source));
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
    if (currentView === "library" && !selectedArticleId && articles.length) {
      selectedArticleId = articles[0].id;
      selectedLanguage = articles[0].default_language;
      history.replaceState({ articleId: selectedArticleId, language: selectedLanguage }, "", articleUrl(selectedArticleId, selectedLanguage));
    }
    updateArticleSummary();
    renderArticles();
    if (currentView === "library" && selectedArticleId) {
      await renderArticleDetail(selectedArticleId, selectedLanguage);
    }
  } catch (error) {
    renderInlineMessage(els.articleList, "Article library could not be loaded.", true);
  }
}

function updateArticleSummary() {
  els.articleCount.textContent = articles.length;
  els.englishCount.textContent = articles.filter((article) => article.languages.includes("en")).length;
  els.spanishCount.textContent = articles.filter((article) => article.languages.includes("es")).length;
}

function filteredArticles() {
  const query = els.articleSearch.value.trim().toLowerCase();
  const language = els.articleLanguage.value;
  return articles.filter((article) => {
    const matchesQuery = !query || `${article.title} ${article.excerpt}`.toLowerCase().includes(query);
    const matchesLanguage = language === "all" || article.languages.includes(language);
    return matchesQuery && matchesLanguage;
  });
}

function renderArticles() {
  const filtered = filteredArticles();
  els.articleList.replaceChildren();
  if (!filtered.length) {
    renderInlineMessage(els.articleList, "No articles match this search.");
    return;
  }

  filtered.forEach((article) => {
    const link = document.createElement("a");
    const targetLanguage = article.languages.includes(selectedLanguage) ? selectedLanguage : article.default_language;
    link.href = articleUrl(article.id, targetLanguage);
    link.className = "article-row";
    link.classList.toggle("active", article.id === selectedArticleId);
    link.append(
      textElement("span", `${languageBadges(article.languages)} / ${formatWordCount(article.word_count)}`, "article-row-meta"),
      textElement("strong", article.title),
      textElement("span", article.excerpt),
    );
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigateArticle(article.id, targetLanguage);
    });
    els.articleList.appendChild(link);
  });
}

async function renderArticleDetail(articleId, language) {
  renderInlineMessage(els.articleReader, "Loading article...");
  try {
    const params = language ? `?lang=${encodeURIComponent(language)}` : "";
    const response = await fetch(`/api/articles/${encodeURIComponent(articleId)}${params}`);
    const article = await response.json();
    if (!response.ok) {
      throw new Error(article.detail || "Article not found.");
    }
    selectedLanguage = article.selected_language;
    document.title = `${article.title} / Ray Peat Library`;

    const header = document.createElement("header");
    header.className = "reader-header";

    const meta = document.createElement("div");
    meta.className = "reader-meta";
    meta.append(
      textElement("span", languageLabel(article.selected_language)),
      textElement("span", formatWordCount(article.word_count)),
      textElement("span", article.source_pdf),
    );

    const title = document.createElement("h2");
    title.textContent = article.title;

    const controls = document.createElement("div");
    controls.className = "reader-controls";
    const languageSelect = document.createElement("select");
    languageSelect.setAttribute("aria-label", "Article language");
    article.languages.forEach((lang) => {
      const option = document.createElement("option");
      option.value = lang;
      option.textContent = languageLabel(lang);
      option.selected = lang === article.selected_language;
      languageSelect.appendChild(option);
    });
    languageSelect.addEventListener("change", () => navigateArticle(article.id, languageSelect.value));
    controls.append(languageSelect);

    header.append(meta, title, controls);

    const body = document.createElement("div");
    body.className = "article-body";
    article.paragraphs.forEach((paragraph) => {
      if (paragraph === "REFERENCES") {
        const heading = document.createElement("h3");
        heading.textContent = "References";
        body.appendChild(heading);
        return;
      }
      const p = document.createElement("p");
      p.textContent = paragraph;
      body.appendChild(p);
    });

    els.articleReader.replaceChildren(header, body);
    els.articleReader.scrollTop = 0;
    renderArticles();
  } catch (error) {
    renderInlineMessage(els.articleReader, error.message, true);
  }
}

function languageBadges(languages) {
  return languages.map(languageLabel).join(" + ");
}

function formatWordCount(value) {
  if (!value) return "0 words";
  return `${value.toLocaleString()} words`;
}

function languageLabel(language) {
  if (language === "es") return "Spanish";
  if (language === "en") return "English";
  return "Other";
}

function normalizeProductUrl(value) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function isLikelyProductUrl(value) {
  try {
    const url = new URL(value);
    return Boolean(url.hostname && url.hostname.includes("."));
  } catch (error) {
    return false;
  }
}

async function submitScore(event) {
  event.preventDefault();
  setMessage("");

  let payload;
  if (mode === "url") {
    const url = normalizeProductUrl(els.productUrl.value);
    if (!url) {
      setMessage("Add a product URL first.", true);
      return;
    }
    if (!isLikelyProductUrl(url)) {
      setMessage("Use a complete supermarket URL, for example https://supermercado.eroski.es/.../productdetail/...", true);
      return;
    }
    els.productUrl.value = url;
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
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(data.detail || "The product could not be scored.");
    }
    renderResult(data);
    setMessage("Score ready.");
  } catch (error) {
    // HTTP guardrail failures have no score payload. Replace any previous result,
    // preserving the provider detail as plain text.
    renderResult({ score: null, error: error.message, product: payload.product || {} });
    setMessage(scoreErrorMessage(error.message), true);
  } finally {
    setLoading(false);
  }
}

async function parseJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    return { detail: response.ok ? "The server returned an invalid response." : "The scoring service returned a server error." };
  }
}

function hasScoreValue(value) {
  return safeNumber(value) !== null;
}

function renderResult(result) {
  const product = result.product || {};
  els.emptyState.classList.add("hidden");
  els.resultView.classList.remove("hidden");
  els.scoreError.classList.add("hidden");
  els.scoreError.textContent = "";

  if (!hasScoreValue(result.score)) {
    els.scoreComment.textContent = "Insufficient evidence to score";
    renderInsufficientEvidence(result, product);
    return;
  }

  els.scoreGauge.classList.remove("hidden");
  els.scoreGauge.style.setProperty("--score", result.score);
  els.scoreGauge.style.setProperty("--score-color", scoreColor(result.score));
  els.scoreValue.textContent = result.score;
  els.scoreBand.textContent = safeText(result.band, "Unknown band");
  els.scoreBand.className = `band ${bandClass(safeText(result.band, "mixed"))}`;
  els.productName.textContent = displayProductName(product, null);
  els.scoreComment.textContent = safeText(result.comment, "");
  els.productSource.textContent = product.source || "-";
  els.productBrand.textContent = product.brand || "-";
  els.scrapedAt.textContent = formatDate(product.scraped_at);
  els.productCategory.textContent = result.category?.label || "-";
  els.scoreConfidence.textContent =
    result.confidence === undefined || result.confidence === null
      ? "-"
      : `${formatComponentScore(result.confidence)}/100`;

  renderComponents(result.components || [], result.warnings || []);
  renderReasons(result.reasons || []);
  renderNutrition(product.nutrition_per_100g || {});
  renderIngredients(product);
}

function renderInsufficientEvidence(result, product) {
  const providerError =
    result.error ||
    result.detail ||
    result.provider_error ||
    result.message ||
    "The provider did not return enough ingredient and nutrition evidence.";

  els.scoreGauge.classList.add("hidden");
  els.scoreGauge.style.removeProperty("--score");
  els.scoreGauge.style.removeProperty("--score-color");
  els.scoreValue.textContent = "";
  els.scoreBand.textContent = "No score";
  els.scoreBand.className = "band unscored";
  els.productName.textContent = displayProductName(product, null);
  els.scoreComment.textContent = "Insufficient evidence to score";
  els.scoreError.textContent = safeText(providerError, "The provider did not return a score.");
  els.scoreError.classList.remove("hidden");
  els.productSource.textContent = product.source || "-";
  els.productBrand.textContent = product.brand || "-";
  els.scrapedAt.textContent = formatDate(product.scraped_at);
  els.productCategory.textContent = result.category?.label || "-";
  els.scoreConfidence.textContent = "-";

  els.componentCount.textContent = "0 components";
  els.componentList.replaceChildren();
  els.warningList.replaceChildren();
  els.reasonCount.textContent = "0 rules";
  els.reasonsList.replaceChildren();
  els.nutritionCount.textContent = "0 values";
  els.nutritionList.replaceChildren();
  els.ingredientsText.textContent = "No ingredients found.";
  els.sourceLink.removeAttribute("href");
  els.sourceLink.classList.add("hidden");
}

function bandClass(band) {
  const value = safeText(band, "").toLowerCase();
  if (value.includes("strong")) return "strong";
  if (value.includes("reasonable")) return "reasonable";
  if (value.includes("weak")) return "weak";
  if (value.includes("avoid")) return "avoid";
  return "mixed";
}

function renderComponents(components, warnings) {
  els.componentCount.textContent = `${components.length} components`;
  els.componentList.replaceChildren();
  components.forEach((component) => {
    const row = document.createElement("div");
    row.className = "component-row";
    row.dataset.explain = explanationKey(component?.id || component?.label);
    row.tabIndex = 0;

    const summary = document.createElement("div");
    summary.className = "component-summary";
    const weight = textElement("span", formatWeight(component?.weight), "component-definition");
    weight.dataset.explain = "weight";
    weight.tabIndex = 0;
    const confidence = textElement(
      "span",
      formatConfidence(component?.confidence),
      "component-definition",
    );
    confidence.dataset.explain = "confidence";
    confidence.tabIndex = 0;
    summary.append(
      textElement("strong", safeText(component?.label, "Unknown component")),
      weight,
      confidence,
    );

    const meter = document.createElement("meter");
    meter.min = 0;
    meter.max = 100;
    meter.value = Math.max(0, Math.min(100, safeNumber(component?.score) ?? 0));
    row.append(summary, meter, textElement("b", formatComponentScore(component?.score)));

    if (contributionsFor(component).length) {
      const breakdown = buildContributionBreakdown(component);
      if (breakdown) row.appendChild(breakdown);
    }

    els.componentList.appendChild(row);
  });

  els.warningList.replaceChildren();
  warnings.forEach((warning) => {
    const row = document.createElement("p");
    row.textContent = warning;
    els.warningList.appendChild(row);
  });
}

function renderReasons(reasons) {
  els.reasonCount.textContent = `${reasons.length} rules`;
  els.reasonsList.replaceChildren();
  if (!reasons.length) {
    renderInlineMessage(els.reasonsList, "No rule matched this product.");
    return;
  }

  reasons.forEach((reason) => {
    const row = document.createElement("div");
    const deltaClass = reason.delta >= 0 ? "positive" : "negative";
    row.className = "reason-row";
    const detail = document.createElement("div");
    detail.append(textElement("strong", reason.label), textElement("p", reason.detail));
    row.append(textElement("span", formatDelta(reason.delta), `delta ${deltaClass}`), detail);
    els.reasonsList.appendChild(row);
  });
}

function renderNutrition(nutrition) {
  const entries = Object.entries(nutrition);
  els.nutritionCount.textContent = `${entries.length} values`;
  els.nutritionList.replaceChildren();
  if (!entries.length) {
    renderInlineMessage(els.nutritionList, "No structured nutrition values found.");
    return;
  }

  entries.forEach(([key, value]) => {
    const chip = document.createElement("div");
    chip.className = "nutrition-chip";
    chip.append(textElement("span", formatLabel(key)), textElement("strong", formatNumber(value)));
    els.nutritionList.appendChild(chip);
  });
}

function renderIngredients(product) {
  const ingredients = product.ingredients || [];
  els.ingredientsText.textContent = ingredients.length ? ingredients.join(", ") : "No ingredients found.";
  if (isHttpUrl(product.url)) {
    els.sourceLink.href = product.url;
    els.sourceLink.classList.remove("hidden");
  } else {
    els.sourceLink.removeAttribute("href");
    els.sourceLink.classList.add("hidden");
  }
}

function isHttpUrl(value) {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function formatDelta(delta) {
  const number = safeNumber(delta);
  if (number === null) return "±0";
  return number > 0 ? `+${formatNumber(number)}` : formatNumber(number);
}

function scoreColor(score) {
  const normalizedScore = Math.max(0, Math.min(100, Number(score) || 0));
  const hue = Math.round((normalizedScore / 100) * 120);
  return `hsl(${hue}, 58%, 38%)`;
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

function setBestProductsLoading(isLoading) {
  els.bestProductsButton.disabled = isLoading;
  els.bestProductsButton.textContent = isLoading ? "Searching..." : "Find best";
}

function setBestProductsMessage(text, isError = false) {
  els.bestProductsMessage.textContent = text;
  els.bestProductsMessage.classList.toggle("error", isError);
}

function providerStatusSummary(providerStatus, selectedProvider) {
  if (!Array.isArray(providerStatus) || !providerStatus.length) return "";
  const selectedKey = String(selectedProvider || "all").toLowerCase();
  const relevant = providerStatus.filter((status) => {
    if (!status || !status.provider) return false;
    return selectedKey === "all" || String(status.provider).toLowerCase() === selectedKey;
  });
  const problems = relevant.filter((status) => (
    status.outcome !== "ok" || !(Number(status.products) > 0)
  ));
  if (!problems.length) return "";
  return problems
    .map((status) => {
      const provider = safeText(status.provider, "Provider");
      const outcome = safeText(status.outcome, "unknown");
      const cause = status.cause ? ` (${safeText(status.cause, "")})` : "";
      return `${provider}: ${outcome}${cause}`;
    })
    .join("; ");
}


async function loadSearchProviders() {
  try {
    const response = await fetch("/api/search-providers");
    const data = await response.json();
    renderSearchProviders(data.providers || []);
  } catch (error) {
    renderSearchProviders(["all"]);
  }
}

function renderSearchProviders(providers) {
  const selected = els.bestProductsProvider.value || "all";
  els.bestProductsProvider.replaceChildren();
  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider;
    option.textContent = provider === "all" ? "All providers" : provider;
    option.selected = provider === selected;
    els.bestProductsProvider.appendChild(option);
  });
}

function normalizeBestProductsQuery(query) {
  const cleaned = query.replace(/\s+/g, " ").trim();
  const genericBrowserTerms = new Set([
    "",
    "none",
    "null",
    "undefined",
    "product",
    "products",
    "producto",
    "productos",
    "best product",
    "best products",
  ]);
  return genericBrowserTerms.has(cleaned.toLowerCase()) ? predefinedSearches[0].query : cleaned;
}

async function submitBestProducts(event) {
  event.preventDefault();
  let query = normalizeBestProductsQuery(els.bestProductsQuery.value);
  const maxResults = Number(els.bestProductsLimit.value) || 10;
  const provider = els.bestProductsProvider.value || "all";
  els.bestProductsQuery.value = query;

  setView("best");
  setBestProductsLoading(true);
  setBestProductsMessage("Searching and scoring products...");
  els.bestProductsList.replaceChildren();
  try {
    const response = await fetch("/api/search-score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: query, max_results: maxResults, provider }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(data.detail || "Products could not be searched.");
    const results = data.results || [];
    renderBestProducts(results);
    const total = data.total || results.length;
    const scoredCount = results.filter((item) => hasScoreValue(item.score?.score)).length;
    const providerLabel = provider === "all" ? "all providers" : provider;
    const statusSummary = providerStatusSummary(data.provider_status, provider);
    const statusDetail = statusSummary ? ` Provider status: ${statusSummary}.` : "";
    if (!total && provider === "all") {
      setBestProductsMessage(`No products found for "${query}".${statusDetail} Try a broader search term.`, true);
    } else if (!total) {
      setBestProductsMessage(`No products returned for "${query}" in ${providerLabel}.${statusDetail}`, true);
    } else if (scoredCount < total) {
      const scoredDetail = scoredCount === 0
        ? "None had enough ingredient and nutrition data to score."
        : `${scoredCount} of ${total} had enough evidence to score.`;
      setBestProductsMessage(`${total} products found for "${query}" in ${providerLabel}. ${scoredDetail}${statusDetail}`);
    } else if (statusSummary) {
      setBestProductsMessage(`${total} products scored for "${query}" in ${providerLabel}.${statusDetail}`);
    } else {
      setBestProductsMessage(`${total} products scored for "${query}" in ${providerLabel}.`);
    }
  } catch (error) {
    renderEmptyState(els.bestProductsList, "Products could not be loaded", error.message);
    setBestProductsMessage(error.message, true);
  } finally {
    setBestProductsLoading(false);
  }
}

function unscoredMessage(error) {
  const detail = String(error || "").toLowerCase();
  if (detail.includes("evidence") || detail.includes("missing")) {
    return "This product page did not include enough ingredient and nutrition data to score.";
  }
  return "This product page could not be read, so it was not scored.";
}

function renderBestProducts(results) {
  const scoredResults = results
    .filter((item) => hasScoreValue(item.score?.score))
    .sort((a, b) => (safeNumber(b.score?.score) ?? 0) - (safeNumber(a.score?.score) ?? 0));
  const unscoredResults = results.filter((item) => !hasScoreValue(item.score?.score));
  const orderedResults = [...scoredResults, ...unscoredResults];
  els.bestProductsList.replaceChildren();
  if (!orderedResults.length) {
    renderEmptyState(
      els.bestProductsList,
      "No products found",
      "Try a broader search term or another product category.",
    );
    return;
  }

  orderedResults.forEach((item, index) => {
    const score = item.score;
    const scored = hasScoreValue(score?.score);
    const product = score?.product || {};
    const search = item.search || {};
    const card = document.createElement("article");
    card.className = scored ? "best-product-card" : "best-product-card unscored";

    const scoreSummary = document.createElement("div");
    scoreSummary.className = scored ? "best-score" : "best-score unscored";
    if (scored) {
      scoreSummary.style.setProperty("--score-color", scoreColor(score.score));
      const band = textElement("span", safeText(score.band, "Unknown band"));
      band.dataset.explain = "band";
      band.tabIndex = 0;
      scoreSummary.append(textElement("strong", formatComponentScore(score.score)), band);
    } else {
      scoreSummary.append(textElement("strong", "Insufficient evidence to score"));
    }
    const cardScoringLink = textElement("a", "ⓘ How scoring works", "how-scoring-link how-scoring-link--card");
    cardScoringLink.href = "/";
    scoreSummary.appendChild(cardScoringLink);

    const productMeta = document.createElement("div");
    productMeta.className = "best-product-meta";
    productMeta.append(
      textElement("span", product.source || search.source || "Source"),
      textElement("span", score?.category?.label || search.category || "Unknown"),
    );
    if (scored) {
      const confidence = textElement(
        "span",
        score.confidence === undefined || score.confidence === null
          ? "Unknown confidence"
          : `${formatComponentScore(score.confidence)}/100 confidence`,
      );
      confidence.dataset.explain = "confidence";
      confidence.tabIndex = 0;
      productMeta.append(confidence);
    }

    const productMain = document.createElement("div");
    productMain.className = "best-product-main";
    productMain.append(productMeta, textElement("h2", displayProductName(product, search)));
    if (scored) {
      productMain.append(
        textElement("p", safeText(score.comment, "")),
        componentChips(score.components || []),
      );
    } else {
      const providerError = safeText(
        item.error,
        "The provider did not return enough ingredient and nutrition evidence.",
      );
      productMain.append(
        textElement("p", "Insufficient evidence to score", "unscored-note"),
        textElement("p", providerError, "unscored-detail"),
      );
    }

    card.append(
      textElement("div", scored ? `#${index + 1}` : "-", "rank-badge"),
      scoreSummary,
      productMain,
    );
    const sourceUrl = product.url || search.url;
    if (isHttpUrl(sourceUrl)) {
      const sourceLink = textElement("a", "Open", "source-button");
      sourceLink.href = sourceUrl;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener noreferrer";
      card.append(sourceLink);
    }
    els.bestProductsList.appendChild(card);
  });
}

function displayProductName(product, search) {
  const candidates = [product?.name, search?.display_name, search?.product_id];
  const value = candidates.find((candidate) => {
    if (candidate === null || candidate === undefined) return false;
    const normalized = String(candidate).trim().toLowerCase();
    return normalized && normalized !== "none" && normalized !== "null" && normalized !== "undefined";
  });
  return value ? String(value).trim() : "Unnamed product";
}

function componentChips(components) {
  const block = document.createElement("div");
  block.className = "component-block";
  const heading = document.createElement("div");
  heading.className = "section-heading component-heading";
  const title = textElement("h3", "Algorithm components");
  const scoringLink = textElement("a", "ⓘ How scoring works", "how-scoring-link");
  scoringLink.href = "/";
  heading.append(title, scoringLink);

  const strip = document.createElement("div");
  strip.className = "component-strip";
  components.forEach((component) => {
    const label = safeText(component?.label, "Unknown component");
    const group = document.createElement("div");
    group.className = "component-chip-group";

    const chip = document.createElement("span");
    chip.className = "component-chip";
    chip.dataset.explain = explanationKey(component?.id || label);
    chip.tabIndex = 0;
    chip.title = label;
    chip.append(
      textElement("span", label),
      textElement("strong", formatComponentScore(component?.score)),
      textElement("small", formatWeight(component?.weight)),
      textElement("small", formatConfidence(component?.confidence)),
    );

    const weight = chip.querySelector("small");
    if (weight) {
      weight.dataset.explain = "weight";
      weight.tabIndex = 0;
    }
    const confidence = chip.querySelectorAll("small")[1];
    if (confidence) {
      confidence.dataset.explain = "confidence";
      confidence.tabIndex = 0;
    }

    group.appendChild(chip);
    const breakdown = buildContributionBreakdown(component);
    if (breakdown) group.appendChild(breakdown);
    strip.appendChild(group);
  });

  block.append(heading, strip);
  return block;
}

els.libraryViewButton.addEventListener("click", () => {
  window.location.href = "/articles";
});
els.evaluatorViewButton.addEventListener("click", () => setView("evaluator"));
els.bestProductsViewButton.addEventListener("click", () => setView("best"));
els.articleSearch.addEventListener("input", renderArticles);
els.articleLanguage.addEventListener("change", renderArticles);
els.urlMode.addEventListener("click", () => setMode("url"));
els.jsonMode.addEventListener("click", () => setMode("json"));
els.scoreForm.addEventListener("submit", submitScore);
els.bestProductsForm.addEventListener("submit", submitBestProducts);
window.addEventListener("popstate", () => {
  selectedArticleId = articleIdFromLocation() || selectedArticleId;
  selectedLanguage = new URLSearchParams(window.location.search).get("lang") || selectedLanguage;
  renderArticles();
  if (selectedArticleId) renderArticleDetail(selectedArticleId, selectedLanguage);
});

bindExplanationEvents();
setView(currentView);
renderPresetSearches();
renderExamples();
loadConnectors();
loadSearchProviders();
loadArticles();
