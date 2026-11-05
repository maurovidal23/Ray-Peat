// Dependency-free DOM test double: executes production handlers, not browser layout.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

class Element {
  constructor() {
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.textContent = '';
    this.hidden = false;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name), remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, on) => on ? classes.add(name) : classes.delete(name),
    };
    this.style = { setProperty: (key, value) => { this.style[key] = value; },
      removeProperty: (key) => { delete this.style[key]; } };
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(type, handler) { this.listeners[type] = handler; }
  closest(selector) { return selector === '[data-explain]' ? this : null; }
  getBoundingClientRect() { return { left: 30, top: 30, bottom: 50, width: 100, height: 20 }; }
}

function setup() {
  const nodes = new Map();
  const document = new Element();
  document.body = new Element();
  document.createElement = () => new Element();
  document.querySelector = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, new Element());
    return nodes.get(selector);
  };
  const window = { location: { pathname: '/evaluator', search: '' },
    innerWidth: 1000, innerHeight: 800, addEventListener() {} };
  const context = vm.createContext({ document, window, URL, URLSearchParams });
  const source = fs.readFileSync(path.join(__dirname, '../src/peat_product_scorer/static/app.js'), 'utf8');
  // Omit page bootstrap/network loads, retaining every production function.
  vm.runInContext(source.slice(0, source.indexOf('els.libraryViewButton.addEventListener')), context);
  return { context, document, node: (id) => document.querySelector('#' + id),
    run: (code) => vm.runInContext(code, context) };
}

test('hover/focus followed by tap keeps explanation open; Escape and blur close it', () => {
  const { document, run } = setup();
  run('bindExplanationEvents()');
  const trigger = new Element();
  trigger.dataset.explain = 'nutrition-profile';
  for (const type of ['mouseover', 'focusin', 'click']) document.listeners[type]({ target: trigger });
  const popover = document.body.children[0];
  assert.equal(popover.hidden, false);
  assert.equal(trigger.getAttribute('aria-describedby'), 'explanationPopover');
  document.listeners.keydown({ key: 'Escape' });
  assert.equal(popover.hidden, true);
  document.listeners.click({ target: trigger });
  document.listeners.focusout({ target: trigger });
  assert.equal(popover.hidden, true);
});

test('breakdown toggles hidden and ARIA together; absent/malformed contributions have no section', () => {
  const { run } = setup();
  for (const contributions of ['undefined', '[]', '[null]', '"invalid"']) {
    assert.equal(run(`buildContributionBreakdown({ contributions: ${contributions} })`), null);
  }
  const section = run('buildContributionBreakdown({base_score: 50, score: 60, weight: .2, contributions: [{label: "Bonus", delta: 10, detail: "Evidence"}]})');
  const [toggle, panel] = section.children;
  assert.equal(panel.hidden, true);
  assert.equal(panel.children[0].textContent, 'Base score: 50');
  assert.match(panel.children[2].textContent, /= 12$/);
  for (const expanded of [true, false]) {
    toggle.listeners.click({ stopPropagation() {} });
    assert.equal(panel.hidden, !expanded);
    assert.equal(toggle.getAttribute('aria-expanded'), String(expanded));
  }
});

for (const scenario of ['422', '502', 'fallback-failure', 'null']) {
  test(`submission ${scenario} clears stale score and displays provider error`, async () => {
    const { context, node, run } = setup();
    const detail = 'Provider evidence incomplete <img src=x onerror=alert(1)>';
    node('productUrl').value = scenario === 'fallback-failure' ? 'https://example.com/product' : 'https://example.com/product';
    node('scoreValue').textContent = '88';
    node('componentList').append(new Element());
    let calls = 0;
    context.fetch = async () => {
      calls++;
      if (scenario === 'fallback-failure' && calls === 2) throw new Error(detail);
      return { ok: scenario === 'null', status: Number(scenario) || 422,
        text: async () => JSON.stringify(scenario === 'null' ? { score: null, error: detail } : { detail }) };
    };
    await run('submitScore({preventDefault() {}})');
    assert.equal(node('scoreComment').textContent, 'Insufficient evidence to score');
    assert.equal(node('scoreError').textContent, detail);
    assert.equal(node('scoreValue').textContent, '');
    assert.equal(node('scoreGauge').classList.contains('hidden'), true);
    assert.equal(node('componentList').children.length, 0);
    assert.equal(node('resultView').classList.contains('hidden'), false);
    assert.equal(node('scoreButton').disabled, false);
    run('renderResult({score: 72, product: {name: "Next product"}})');
    assert.equal(node('scoreGauge').classList.contains('hidden'), false);
    assert.equal(node('scoreValue').textContent, 72);
    assert.equal(node('scoreError').classList.contains('hidden'), true);
  });
}

test('best-products guardrail card contains provider text but no component chips or numeric score', () => {
  const { run, node } = setup();
  run('renderBestProducts([{score: null, error: "Missing evidence <b>provider</b>", search: {name: "Product"}}])');
  const card = node('bestProductsList').children[0];
  const summary = card.children[1];
  const main = card.children[2];
  assert.equal(summary.children[0].textContent, 'Insufficient evidence to score');
  assert.equal(main.children[2].textContent, 'Insufficient evidence to score');
  assert.equal(main.children[3].textContent, 'Missing evidence <b>provider</b>');
  assert.equal(main.children.length, 4);
});

test('provider status summary is data-driven and tolerates an absent field', () => {
  const { run } = setup();
  assert.equal(run('providerStatusSummary(undefined, "all")'), '');
  assert.equal(run('providerStatusSummary([], "all")'), '');
  assert.equal(
    run('providerStatusSummary([{provider: "Eroski", outcome: "ok", products: 2}], "all")'),
    '',
  );
  assert.equal(
    run('providerStatusSummary([{provider: "Manual", outcome: "blocked", products: 0, cause: "HTTP 403"}], "Manual")'),
    'Manual: blocked (HTTP 403)',
  );
  assert.equal(
    run(`providerStatusSummary([
      {provider: "Eroski", outcome: "ok", products: 2},
      {provider: "Manual", outcome: "blocked", products: 0, cause: "HTTP 403"},
      {provider: "Test", outcome: "empty", products: 0},
    ], "all")`),
    'Manual: blocked (HTTP 403); Test: empty',
  );
});

test('best-products message renders per-provider status when no products are scoreable', async () => {
  const { context, node, run } = setup();
  node('bestProductsQuery').value = 'leche';
  node('bestProductsProvider').value = 'all';
  node('bestProductsLimit').value = '10';
  context.fetch = async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({
      total: 0,
      results: [],
      provider_status: [
        { provider: 'Manual', outcome: 'blocked', products: 0, cause: 'HTTP 403' },
        { provider: 'Eroski', outcome: 'empty', products: 0 },
      ],
    }),
  });
  await run('submitBestProducts({preventDefault() {}})');
  assert.match(node('bestProductsMessage').textContent, /Manual: blocked \(HTTP 403\)/);
  assert.match(node('bestProductsMessage').textContent, /Eroski: empty/);
});

test('best-products message reports partial provider failure while results are shown', async () => {
  const { context, node, run } = setup();
  node('bestProductsQuery').value = 'leche';
  node('bestProductsProvider').value = 'all';
  node('bestProductsLimit').value = '10';
  context.fetch = async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({
      total: 1,
      results: [{ score: { score: 80, band: 'Good', product: { name: 'Leche entera' } }, search: { display_name: 'Leche entera' } }],
      provider_status: [
        { provider: 'Eroski', outcome: 'ok', products: 1 },
        { provider: 'Manual', outcome: 'blocked', products: 0, cause: 'HTTP 403' },
      ],
    }),
  });
  await run('submitBestProducts({preventDefault() {}})');
  assert.equal(node('bestProductsList').children.length, 1);
  assert.match(node('bestProductsMessage').textContent, /Manual: blocked \(HTTP 403\)/);
});
