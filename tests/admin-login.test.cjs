'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../admin/index.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const candidatePath = 'contents/confidence/candidates.json';
const candidateSha = 'a'.repeat(40);
const repositoryApi = 'https://api.github.com/repos/B1axk-bit/stillpoint-data/';
const fixtureToken = 'mock-admin-test-token';
const fixtures = {
  'confidence/latest.json': {
    run_at: '2026-11-04T16:00:00+08:00', version: 'test', lamps: [],
    themes: [{theme: '测试', cell: 'H1', score: 70, since: '2026-10-15', alerts: [], items: [], fading: []}],
  },
  'confidence/rubric.json': {strength: [], changelog: []},
};

const jsonResponse = (value, status = 200) => new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}});
const loginAlert = h => h.node('#login').innerHTML.match(/<div class="alert">([^<]*)<\/div>/)?.[1] || '';

function harness({candidateData = {candidates: []}, candidateStatus = 200} = {}) {
  const requests = [];
  const nodes = new Map();
  const storage = new Map();
  function node(selector) {
    if (!nodes.has(selector)) {
      const classes = new Set();
      nodes.set(selector, {
        innerHTML: '', textContent: '', value: '',
        classList: {add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value)},
        addEventListener() {},
      });
    }
    return nodes.get(selector);
  }
  const context = vm.createContext({
    URL, TextEncoder, TextDecoder, AbortController, AbortSignal, setTimeout, clearTimeout,
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
    document: {
      querySelector: node, getElementById: id => node('#' + id),
      addEventListener() {}, querySelectorAll: () => [],
    },
    window: {addEventListener() {}},
    fetch: async (url, options = {}) => {
      assert.ok(url.startsWith(repositoryApi), 'fixture only accepts the private repository API');
      assert.equal(options.method || 'GET', 'GET', 'login is read-only');
      const route = url.slice(repositoryApi.length).split('?')[0];
      requests.push({route, accept: options.headers.Accept, cache: options.cache});
      assert.equal(options.headers.Authorization, 'Bearer ' + fixtureToken);
      if (route === candidatePath) {
        if (candidateStatus !== 200) return jsonResponse({}, candidateStatus);
        return jsonResponse({sha: candidateSha, encoding: 'none', content: '', size: 1_500_000});
      }
      if (route === 'git/blobs/' + candidateSha) return jsonResponse(candidateData);
      const fixture = fixtures[route.replace(/^contents\//, '')];
      if (!fixture) return jsonResponse({}, 404);
      const content = Buffer.from(JSON.stringify(fixture)).toString('base64');
      return jsonResponse({sha: 'b'.repeat(40), encoding: 'base64', content});
    },
  });
  vm.runInContext(source, context, {filename: 'admin/index.html'});
  const run = code => vm.runInContext(code, context);
  assert.equal(node('#app').classList.contains('locked'), true);
  return {
    node, run, requests, storage,
    login: () => run(`ghToken = '${fixtureToken}'; ghLoad(true)`),
  };
}

test('large candidate files use distinct, uncached metadata and raw blob URLs and then render the dashboard', async () => {
  const h = harness();
  await h.login();
  assert.equal(h.node('#app').classList.contains('locked'), false);
  assert.match(h.node('#summary').innerHTML, /共 0 条候选/);
  assert.equal(h.storage.get('stillpoint-admin-token'), fixtureToken);
  const metadata = h.requests.filter(r => r.route === candidatePath);
  assert.equal(metadata.length, 1, 'the metadata URL is never reused for the raw download');
  assert.equal(metadata[0].accept, 'application/vnd.github.object+json');
  assert.equal(metadata[0].cache, 'no-store');
  const raw = h.requests.find(r => r.route === 'git/blobs/' + candidateSha);
  assert.match(raw.accept, /\.raw/);
  assert.equal(raw.cache, 'no-store');
});

test('the dashboard renders both text and structured news summaries from the private candidate feed', async () => {
  const common = {date: '2026-11-11', status: '待确认', source: '测试公告', why: [], suggest: {class: '噪声'}};
  const h = harness({candidateData: {candidates: [
    {...common, id: 'text', evidence: '已核验的中文标题', original_title: 'Original headline',
      original_url: 'https://example.com/article', brief: '经营现金流 < 设备采购支出'},
    {...common, id: 'structured', evidence: '结构化记录',
      brief: {zh: '结构化摘要标题', who: '测试公司', what: '发布季报', figure: '19.75 亿美元', impact: '核对现金覆盖'}},
    {...common, id: 'pending', evidence: '仅有标题', brief: '  '},
  ]}});
  await h.login();
  const rendered = h.node('#groups').innerHTML;
  assert.match(rendered, /已核验的中文标题[\s\S]*?<dt>中文摘要<\/dt><dd>经营现金流 &lt; 设备采购支出<\/dd>[\s\S]*?https:\/\/example\.com\/article/);
  assert.match(rendered, /结构化摘要标题[\s\S]*?<dt>数字<\/dt><dd>19\.75 亿美元<\/dd>/);
  assert.match(rendered, /仅有标题[\s\S]*?还没整理，每天同步时补上/);
});

test('a cached metadata-shaped candidate response reports invalid data while staying locked', async () => {
  const h = harness({candidateData: {sha: candidateSha, encoding: 'none', content: ''}});
  await h.login();
  assert.equal(h.node('#app').classList.contains('locked'), true);
  assert.match(loginAlert(h), /候选.*(?:缺少|格式|结构)/);
  assert.doesNotMatch(loginAlert(h), /reading &#39;filter&#39;|Bad credentials|HTTP 401/);
  assert.equal(h.storage.has('stillpoint-admin-token'), false);
  assert.equal(h.node('#summary').innerHTML, '');
});

test('a rendering failure remains locked and is distinguished from an HTTP authentication failure', async () => {
  const render = harness();
  render.run('renderHead = () => { throw new Error("simulated render failure") };');
  await render.login();
  assert.equal(render.node('#app').classList.contains('locked'), true);
  assert.match(loginAlert(render), /渲染|显示失败|页面生成|数据未能加载/);
  assert.doesNotMatch(loginAlert(render), /未接受此令牌|HTTP 401/);
  assert.equal(render.storage.has('stillpoint-admin-token'), false);

  const denied = harness({candidateStatus: 401});
  await denied.login();
  assert.equal(denied.node('#app').classList.contains('locked'), true);
  assert.match(loginAlert(denied), /令牌.*有效/);
  assert.match(loginAlert(denied), /HTTP 401/);
  assert.doesNotMatch(loginAlert(denied), /渲染|显示失败|页面生成|数据未能加载/);
});
