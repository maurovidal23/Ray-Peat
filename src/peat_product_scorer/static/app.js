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
let selectedArticleId = articleIdFromLocation();
let selectedLanguage = new URLSearchParams(window.location.search).get("lang") || null;

function articleIdFromLocation() {
  const match = window.location.pathname.match(/^\/articles\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function setView(nextView) {
  currentView = nextView;
  els.libraryView.classList.toggle("hidden", currentView !== "library");
  els.evaluatorView.classList.toggle("hidden", currentView !== "evaluator");
  els.libraryViewButton.classList.toggle("active", currentView === "library");
  els.evaluatorViewButton.classList.toggle("active", currentView === "evaluator");
}

function articleUrl(articleId, language = selectedLanguage) {
  const params = language ? `?lang=${encodeURIComponent(language)}` : "";
  return `/articles/${encodeURIComponent(articleId)}${params}`;
}

function navigateArticle(articleId, language = selectedLanguage) {
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
    const partial = data.connectors.filter((connector) => connector.status === "partial").length;
    els.connectorCount.textContent = partial ? `${verified} verified, ${partial} partial` : `${verified} verified`;
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
    if (!selectedArticleId && articles.length) {
      selectedArticleId = articles[0].id;
      selectedLanguage = articles[0].default_language;
      history.replaceState({ articleId: selectedArticleId, language: selectedLanguage }, "", articleUrl(selectedArticleId, selectedLanguage));
    }
    updateArticleSummary();
    renderArticles();
    if (selectedArticleId) {
      await renderArticleDetail(selectedArticleId, selectedLanguage);
    }
  } catch (error) {
    els.articleList.innerHTML = `<p class="message error">Article library could not be loaded.</p>`;
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
  els.articleList.innerHTML = "";
  if (!filtered.length) {
    els.articleList.innerHTML = `<p class="message">No articles match this search.</p>`;
    return;
  }

  filtered.forEach((article) => {
    const link = document.createElement("a");
    const targetLanguage = article.languages.includes(selectedLanguage) ? selectedLanguage : article.default_language;
    link.href = articleUrl(article.id, targetLanguage);
    link.className = "article-row";
    link.classList.toggle("active", article.id === selectedArticleId);
    link.innerHTML = `
      <span class="article-row-meta">${languageBadges(article.languages)} / ${formatWordCount(article.word_count)}</span>
      <strong>${article.title}</strong>
      <span>${article.excerpt}</span>
    `;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigateArticle(article.id, targetLanguage);
    });
    els.articleList.appendChild(link);
  });
}

async function renderArticleDetail(articleId, language) {
  els.articleReader.innerHTML = `<p class="message">Loading article...</p>`;
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
    meta.innerHTML = `<span>${languageLabel(article.selected_language)}</span><span>${formatWordCount(article.word_count)}</span><span>${article.source_pdf}</span>`;

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

    els.articleReader.innerHTML = "";
    els.articleReader.append(header, body);
    els.articleReader.scrollTop = 0;
    renderArticles();
  } catch (error) {
    els.articleReader.innerHTML = `<p class="message error">${error.message}</p>`;
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
      setMessage("Use a complete supermarket URL, for example https://www.dia.es/.../p/608P6.", true);
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
    let data = await parseJsonResponse(response);
    if (!response.ok) {
      if (mode === "url" && isDiaProductUrl(payload.url)) {
        data = await scoreDiaUrlInBrowser(payload.url);
      } else {
        throw new Error(data.detail || "The product could not be scored.");
      }
    }
    renderResult(data);
    setMessage("Score ready.");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setLoading(false);
  }
}

function isDiaProductUrl(value) {
  try {
    const url = new URL(value);
    return url.hostname.endsWith("dia.es") && url.pathname.includes("/p/");
  } catch (error) {
    return false;
  }
}

async function scoreDiaUrlInBrowser(productUrl) {
  const url = new URL(productUrl);
  const productId = diaProductIdFromPath(url.pathname);
  if (!productId) throw new Error("DIA product URL could not be read.");

  const apiUrl = new URL(`https://www.dia.es/api/v1/pdp-back/${encodeURIComponent(productId)}`);
  apiUrl.searchParams.set("path", url.pathname);
  const diaResponse = await fetch(apiUrl.toString(), { headers: { Accept: "application/json" } });
  const diaData = await parseJsonResponse(diaResponse);
  if (!diaResponse.ok || !diaData.product) {
    throw new Error("DIA product data could not be loaded.");
  }

  const scoreResponse = await fetch("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product: productPayloadFromDia(diaData.product, productUrl) }),
  });
  const scoreData = await parseJsonResponse(scoreResponse);
  if (!scoreResponse.ok) {
    throw new Error(scoreData.detail || "The DIA product could not be scored.");
  }
  return scoreData;
}

function diaProductIdFromPath(pathname) {
  const match = pathname.match(/\/p\/([^/?#]+)/);
  return match ? match[1] : null;
}

function productPayloadFromDia(product, productUrl) {
  const title = product.primary_info?.title || product.sku_id || "Unknown DIA product";
  return {
    name: title,
    source: "DIA",
    url: productUrl,
    brand: diaBrandFromTitle(title),
    description: product.product_info?.product || product.product_info?.subtitle || null,
    ingredients: stripHtml(product.ingredients?.text || ""),
    nutrition: diaNutritionPayload(product.nutritional_info || {}),
  };
}

function diaNutritionPayload(nutritionalInfo) {
  const values = nutritionalInfo.nutritional_values || {};
  const nutrition = {};
  if (values.energy_value !== undefined && values.energy_value !== null) {
    nutrition["Valor energetico"] = values.energy_value;
  }
  (values.values || []).forEach((item) => {
    if (item.title) nutrition[item.title] = item.value_per_100_g ?? item.value;
    (item.items || []).forEach((child) => {
      if (child.title) nutrition[child.title] = child.value_per_100_g ?? child.value;
    });
  });
  ((nutritionalInfo.vitamins || {}).values || []).forEach((item) => {
    if (item.title) nutrition[item.title] = item.value_per_100_g ?? item.value;
  });
  return nutrition;
}

function stripHtml(value) {
  const element = document.createElement("div");
  element.innerHTML = value;
  return element.textContent.replace(/\s+/g, " ").replace(/^ingredientes\s*:?\s*/i, "").trim();
}

function diaBrandFromTitle(title) {
  const known = ["Dia Lactea", "Dia L?ctea", "Dia", "Central Lechera Asturiana", "Pascual", "Puleva", "Alpro"];
  const normalized = title.toLowerCase();
  return known.find((brand) => normalized.includes(brand.toLowerCase())) || null;
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
    row.innerHTML = `<span class="delta ${deltaClass}">${formatDelta(reason.delta)}</span><div><strong>${reason.label}</strong><p>${reason.detail}</p></div>`;
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
window.addEventListener("popstate", () => {
  selectedArticleId = articleIdFromLocation() || selectedArticleId;
  selectedLanguage = new URLSearchParams(window.location.search).get("lang") || selectedLanguage;
  renderArticles();
  if (selectedArticleId) renderArticleDetail(selectedArticleId, selectedLanguage);
});

renderExamples();
loadConnectors();
loadArticles();
