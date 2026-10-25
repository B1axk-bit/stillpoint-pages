'use strict';

// Runs the shipped inline script. All HTTP is an in-memory GitHub Contents API;
// no token, network request, or real decisions file is used.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { TextEncoder, TextDecoder } = require('node:util');

const html = fs.readFileSync(path.join(__dirname, '..', 'admin', 'index.html'), 'utf8');
const inline = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const startup = /if \(STORE === "claude"\) \{ start\(\); connectClaude\(\); \}\s*else \{[\s\S]*?\}\s*$/;
assert.match(inline, startup, 'test harness must remove only the automatic bootstrap');
const source = inline.replace(startup, '');
const clone = value => JSON.parse(JSON.stringify(value));
const response = (status, value, extra = {}) => ({
  status, ok: status >= 200 && status < 300,
  json: async () => clone(value), text: async () => String(value), ...extra,
});
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};
const doc = (id, action = 'confirm') => ({ action, evidence: `证据 ${id}`, note: '', nested: { value: id } });
const candidate = id => ({
  id, evidence: `证据 ${id}`, source: '测试公告', date: '2026-10-25', theme: '测试主题',
  status: '待确认', why: [], suggest: { class: '噪声', toward: '', strength: '', layer: '', cluster: '' },
});

function harness({ initial = {}, remote = initial, hook } = {}) {
  const nodes = new Map();
  const documentListeners = new Map();
  const windowListeners = new Map();
  const fields = [];
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      innerHTML: '', textContent: '', value: '', disabled: false, dataset: {}, listeners: new Map(),
      classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
      addEventListener(type, callback) { this.listeners.set(type, callback); },
      setAttribute() {}, getAttribute() { return null; },
      querySelector: child => node(`${selector} ${child}`), querySelectorAll: () => [],
      insertAdjacentHTML(_position, value) { this.innerHTML += value; },
    });
    return nodes.get(selector);
  }
  const server = { remote: clone(remote), sha: 'remote-0', revision: 0, requests: [] };
  const context = vm.createContext({
    TextEncoder, TextDecoder, URL, console,
    btoa: value => Buffer.from(value, 'binary').toString('base64'),
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    matchMedia: () => ({ matches: false }), location: { reload() {} },
    window: { addEventListener(type, callback) { windowListeners.set(type, callback); } },
    addEventListener(type, callback) { windowListeners.set(type, callback); },
    document: {
      documentElement: node('html'),
      getElementById: id => node(`#${id}`), querySelector: node,
      querySelectorAll: selector => selector === '#a-fields [data-f]' ? fields : [],
      addEventListener(type, callback) { documentListeners.set(type, callback); },
    },
    fetch: async (url, options = {}) => {
      assert.match(url, /^https:\/\/api\.github\.com\/repos\/B1axk-bit\/stillpoint-data\/(?:contents\/confidence\/decisions\.json(?:\?ref=main)?|actions\/workflows\/snapshot\.yml\/dispatches)$/,
        'unexpected network target is blocked');
      const request = { method: options.method || 'GET', url, body: options.body ? JSON.parse(options.body) : null };
      if (request.method === 'PUT') request.document = JSON.parse(Buffer.from(request.body.content, 'base64').toString('utf8'));
      server.requests.push(request);
      const override = hook && await hook(request, server);
      if (override) return override;
      if (request.method === 'POST') return response(204, {});
      if (request.method === 'GET') return response(200, {
        encoding: 'base64', content: Buffer.from(JSON.stringify(server.remote)).toString('base64'), sha: server.sha,
      });
      if (request.body.sha !== server.sha) return response(409, { message: 'sha mismatch' });
      server.remote = clone(request.document);
      server.sha = `remote-${++server.revision}`;
      return response(200, { content: { sha: server.sha } });
    },
  });
  vm.runInContext(source, context, { filename: 'admin/index.html' });
  const run = code => vm.runInContext(code, context);
  context.__initial = clone(initial);
  context.__remote = clone(remote);
  run(`DATA = {generated:'2026-10-25',version:'test',lamps:[],candidates:[],points:{},themes:[{theme:'测试',cell:'H1',score:70,band:'测试',since:'2026-10-25',alerts:[]}]};
    STORE='github'; canWrite=true; ghSaved=__initial; decisions={...ghSaved}; ghSha=JSON.stringify(__initial) === JSON.stringify(__remote) ? 'remote-0' : 'local-stale';`);
  function write(id, data) {
    context.__writeId = id; context.__writeData = data;
    return run('ghWrite(__writeId, __writeData)');
  }
  function record(id) {
    context.__candidate = candidate(id);
    run('DATA.candidates.push(__candidate)');
    return run('record(__candidate, "confirm", __candidate.suggest)');
  }
  function click(dataset, cardId) {
    const card = cardId ? { dataset: { id: cardId } } : null;
    const button = { dataset, classList: { contains() { return false; } }, closest: selector => selector === '.cand' ? card : null };
    const event = { target: { closest: selector => selector === 'button' ? button : null }, preventDefault() {} };
    return documentListeners.get('click')(event);
  }
  return {
    run, write, record, click, node, fields, server, windowListeners,
    state: () => JSON.parse(run('JSON.stringify({decisions,saved:ghSaved,states:Object.fromEntries([...ghSaves].map(([id,s])=>[id,{state:s.state,data:s.data}]))})')),
    drain: () => run('ghQueue'),
    add: () => node('#a-save').listeners.get('click')(),
    puts: () => server.requests.filter(request => request.method === 'PUT'),
  };
}

test('continuous confirmation writes one operation per PUT and reports pending then saved', async () => {
  const hold = deferred();
  let puts = 0;
  const h = harness({ hook: async request => { if (request.method === 'PUT' && ++puts === 1) await hold.promise; } });
  const a = h.record('A'), b = h.record('B');
  assert.equal(h.state().states.A.state, 'pending');
  assert.equal(h.state().states.B.state, 'pending');
  hold.resolve();
  assert.deepEqual(await Promise.all([a, b]), [true, true]);
  assert.deepEqual(Object.keys(h.puts()[0].document), ['A']);
  assert.deepEqual(Object.keys(h.server.remote).sort(), ['A', 'B']);
  assert.equal(h.state().states.A.state, 'saved');
  assert.equal(h.state().states.B.state, 'saved');
});

test('regression: queued A/B survive a 409 rebase and preserve remote C', async () => {
  const h = harness({ remote: { C: doc('C') }, hook: (request, server) => {
    if (server.requests.length === 1) return response(409, {});
  } });
  const a = h.record('A'), b = h.record('B');
  const results = await Promise.all([a, b]);
  assert.deepEqual(Object.keys(h.server.remote).sort(), ['A', 'B', 'C']);
  assert.deepEqual(results, [true, true]);
  assert.deepEqual(h.server.remote.C, doc('C'));
  assert.deepEqual(Object.keys(h.puts()[1].document).sort(), ['A', 'C']);
  assert.deepEqual(Object.keys(h.state().decisions).sort(), ['A', 'B', 'C']);
});

test('confirm then real undo click stays deleted through a conflict', async () => {
  let first = true;
  const h = harness({ remote: { C: doc('C') }, hook: request => {
    if (request.method === 'PUT' && first) { first = false; return response(409, {}); }
  } });
  const a = h.record('A');
  h.click({ act: 'undo' }, 'A');
  assert.equal(h.state().decisions.A, undefined);
  await a; await h.drain();
  assert.deepEqual(h.server.remote, { C: doc('C') });
  assert.equal(h.state().states.A.state, 'saved');
  assert.equal(h.state().states.A.data, null);
});

test('undo replays its tombstone after its own conflict and preserves remote edits', async () => {
  const initial = { A: doc('A'), C: doc('C') };
  const h = harness({ initial, hook: (request, server) => {
    if (server.requests.length === 1) {
      server.remote.C.note = '另一设备修改';
      server.remote.D = doc('D');
      server.sha = 'remote-changed';
      return response(409, {});
    }
  } });
  assert.equal(await h.write('A', null), true);
  assert.equal(h.server.remote.A, undefined);
  assert.equal(h.server.remote.C.note, '另一设备修改');
  assert.deepEqual(h.server.remote.D, doc('D'));
});

test('same id confirm → undo → confirm obeys queue order; old completion cannot mark newer op saved', async () => {
  const first = deferred(), second = deferred(), secondStarted = deferred();
  let count = 0;
  const h = harness({ hook: async request => {
    if (request.method !== 'PUT') return;
    if (++count === 1) await first.promise;
    else if (count === 2) { secondStarted.resolve(); await second.promise; }
  } });
  const a = h.write('A', doc('A'));
  const undo = h.write('A', null);
  const newer = doc('A'); newer.note = '最后确认';
  const again = h.write('A', newer);
  first.resolve();
  assert.equal(await a, true);
  await secondStarted.promise;
  assert.equal(h.state().states.A.state, 'pending');
  assert.equal(h.state().decisions.A.note, '最后确认');
  second.resolve();
  assert.deepEqual(await Promise.all([undo, again]), [true, true]);
  assert.equal(h.server.remote.A.note, '最后确认');
  assert.equal(h.puts()[1].document.A, undefined);
});

for (const status of [409, 422]) {
  test(`${status} conflict re-read and retry preserve unrelated records`, async () => {
    let conflicts = 0;
    const h = harness({ hook: (request, server) => {
      if (request.method === 'PUT' && conflicts++ < 2) {
        server.remote[`remote-${conflicts}`] = doc(`remote-${conflicts}`);
        server.sha = `external-${conflicts}`;
        return response(status, {});
      }
    } });
    assert.equal(await h.write('A', doc('A')), true);
    assert.equal(h.puts().length, 3);
    assert.deepEqual(Object.keys(h.server.remote).sort(), ['A', 'remote-1', 'remote-2']);
  });
}

test('conflict exhaustion reports failed, retains local intent, and explicit retry succeeds', async () => {
  let fail = true;
  const h = harness({ remote: { C: doc('C') }, hook: request => request.method === 'PUT' && fail ? response(409, {}) : undefined });
  assert.equal(await h.write('A', doc('A')), false);
  assert.equal(h.puts().length, 3);
  assert.equal(h.state().states.A.state, 'failed');
  assert.deepEqual(h.state().decisions.A, doc('A'));
  assert.equal(h.server.remote.A, undefined);
  fail = false;
  h.click({ retrySave: 'A' });
  await h.drain();
  assert.equal(h.state().states.A.state, 'saved');
  assert.deepEqual(Object.keys(h.server.remote).sort(), ['A', 'C']);
});

for (const status of [403, 500]) {
  test(`HTTP ${status} failure is not silently included in subsequent successful B`, async () => {
    let first = true;
    const h = harness({ hook: request => {
      if (request.method === 'PUT' && first) { first = false; return response(status, {}); }
    } });
    const a = h.write('A', doc('A')), b = h.write('B', doc('B'));
    assert.deepEqual(await Promise.all([a, b]), [false, true]);
    assert.deepEqual(h.server.remote, { B: doc('B') });
    assert.equal(h.state().states.A.state, 'failed');
    assert.equal(h.state().states.B.state, 'saved');
    assert.deepEqual(h.state().decisions.A, doc('A'));
  });
}

for (const failure of ['PUT rejection', 'conflict GET rejection', 'malformed remote JSON', 'PUT success JSON rejection']) {
  test(`${failure} marks failure without poisoning the later queue`, async () => {
    let failed = false;
    const h = harness({ remote: { C: doc('C') }, hook: (request, server) => {
      if (failed) return;
      if (failure === 'PUT rejection' && request.method === 'PUT') { failed = true; throw new Error('offline'); }
      if (failure === 'PUT success JSON rejection' && request.method === 'PUT') {
        failed = true;
        return response(200, {}, { json: async () => { throw new Error('bad response'); } });
      }
      if (request.method === 'PUT') return response(409, {});
      if (request.method === 'GET') {
        failed = true;
        if (failure === 'conflict GET rejection') throw new Error('read offline');
        return response(200, { encoding: 'base64', content: Buffer.from('{bad JSON').toString('base64'), sha: server.sha });
      }
    } });
    const a = h.write('A', doc('A')), b = h.write('B', doc('B'));
    assert.deepEqual(await Promise.all([a, b]), [false, true]);
    assert.deepEqual(h.server.remote, { B: doc('B'), C: doc('C') });
    assert.equal(h.state().states.A.state, 'failed');
    assert.equal(h.state().states.B.state, 'saved');
  });
}

test('queued payload is a deep snapshot independent of caller or optimistic view mutations', async () => {
  const hold = deferred();
  let count = 0;
  const h = harness({ hook: async request => { if (request.method === 'PUT' && ++count === 1) await hold.promise; } });
  const blocker = h.write('blocker', doc('blocker'));
  const original = doc('A');
  const a = h.write('A', original);
  original.evidence = '调用方后来改动'; original.nested.value = 'mutated';
  h.run('decisions.injected = {action:"confirm"}');
  hold.resolve();
  assert.deepEqual(await Promise.all([blocker, a]), [true, true]);
  assert.deepEqual(h.server.remote.A, doc('A'));
  assert.equal(h.server.remote.injected, undefined);
});

test('failed manual add keeps input and does not claim that saving succeeded', async () => {
  const h = harness({ hook: request => request.method === 'PUT' ? response(403, {}) : undefined });
  h.node('#a-ev').value = '手工证据';
  h.node('#a-src').value = '公告';
  h.node('#a-date').value = '2026-10-25';
  h.fields.push({ dataset: { f: 'class' }, value: '噪声' });
  await h.add();
  assert.equal(h.node('#a-ev').value, '手工证据');
  assert.equal(h.node('#a-src').value, '公告');
  assert.doesNotMatch(h.node('#a-msg').textContent, /记下了|保存成功|已保存/);
  assert.match(h.node('#a-msg').textContent, /保留|失败|没存|未确认/);
  assert.deepEqual(h.server.remote, {});
  assert.equal(Object.values(h.state().states)[0].state, 'failed');
});

test('a failed manual deletion remains retryable after its card disappears', async () => {
  const initial = { own: { ...doc('own', 'add'), date: '2026-10-25', source: '公告', class: '噪声' }, C: doc('C') };
  let fail = true;
  const h = harness({ initial, hook: request => request.method === 'PUT' && fail ? response(500, {}) : undefined });
  h.click({ act: 'undo' }, 'own');
  await h.drain();
  assert.equal(h.state().decisions.own, undefined);
  assert.equal(h.state().states.own.state, 'failed');
  const page = [...['#tools', '#gh-save-status', '#groups'].map(selector => h.node(selector).innerHTML)].join(' ');
  assert.match(page, /data-retry-save="own"/, 'retry remains outside the removed manual card');
  fail = false;
  h.click({ retrySave: 'own' });
  await h.drain();
  assert.deepEqual(h.server.remote, { C: doc('C') });
});

test('a conflict rebase also preserves another device’s deletion', async () => {
  const h = harness({ initial: { removed: doc('removed'), C: doc('C') }, remote: { C: doc('C') } });
  assert.equal(await h.write('A', doc('A')), true);
  assert.deepEqual(h.server.remote, { A: doc('A'), C: doc('C') });
});

for (const failure of ['GET HTTP 500', 'raw GET HTTP 500', 'non-object remote document', 'success missing SHA']) {
  test(`${failure} cannot produce a false success or poison the queue`, async () => {
    let injected = false;
    let raw = false;
    const h = harness({ remote: { C: doc('C') }, hook: (request, server) => {
      if (injected) return;
      if (failure === 'success missing SHA' && request.method === 'PUT') {
        injected = true;
        return response(200, { content: {} });
      }
      if (request.method === 'PUT') return response(409, {});
      if (failure === 'raw GET HTTP 500' && !raw) {
        raw = true;
        return response(200, { encoding: 'none', sha: server.sha });
      }
      injected = true;
      if (failure.includes('HTTP')) return response(500, 'error body must never become decisions');
      return response(200, { encoding: 'base64', content: Buffer.from('null').toString('base64'), sha: server.sha });
    } });
    const a = h.write('A', doc('A')), b = h.write('B', doc('B'));
    assert.deepEqual(await Promise.all([a, b]), [false, true]);
    assert.equal(h.state().states.A.state, 'failed');
    assert.deepEqual(h.server.remote, { B: doc('B'), C: doc('C') });
  });
}

test('successful manual add clears the form only after the PUT is acknowledged', async () => {
  const hold = deferred();
  const h = harness({ hook: async request => { if (request.method === 'PUT') await hold.promise; } });
  h.node('#a-ev').value = '手记成功'; h.node('#a-src').value = '公告'; h.node('#a-date').value = '2026-10-25';
  h.fields.push({ dataset: { f: 'class' }, value: '噪声' });
  const saving = h.add();
  assert.equal(h.node('#a-ev').value, '手记成功');
  assert.equal(Object.values(h.state().states)[0].state, 'pending');
  assert.equal(h.node('#a-save').disabled, true, 'disable the submit button while its operation is pending');
  hold.resolve(); await saving;
  assert.equal(h.node('#a-save').disabled, false);
  assert.equal(h.node('#a-ev').value, '');
  assert.equal(h.node('#a-src').value, '');
  assert.match(h.node('#a-msg').textContent, /保存成功|已保存|记下了/);
  assert.equal(Object.values(h.server.remote)[0].evidence, '手记成功');
});

test('unload warns while pending or failed and stops warning after successful retry', async () => {
  const hold = deferred();
  let fail = true;
  const h = harness({ hook: async request => {
    if (request.method !== 'PUT') return;
    await hold.promise;
    if (fail) return response(500, {});
  } });
  const unload = h.windowListeners.get('beforeunload');
  assert.equal(typeof unload, 'function');
  const prevented = () => {
    let warned = false;
    unload({ preventDefault() { warned = true; }, returnValue: undefined });
    return warned;
  };
  assert.equal(prevented(), false);
  const saving = h.write('A', doc('A'));
  assert.equal(prevented(), true);
  hold.resolve(); await saving;
  assert.equal(prevented(), true);
  fail = false; h.click({ retrySave: 'A' }); await h.drain();
  assert.equal(prevented(), false);
});

test('manual add completion preserves text entered while the request was pending', async () => {
  const hold = deferred();
  const h = harness({ hook: async request => { if (request.method === 'PUT') await hold.promise; } });
  h.node('#a-ev').value = '第一条证据'; h.node('#a-src').value = '第一份公告';
  h.fields.push({ dataset: { f: 'class' }, value: '噪声' });
  const saving = h.add();
  assert.equal(h.node('#a-save').disabled, true);
  h.node('#a-ev').value = '正在编辑第二条'; h.node('#a-src').value = '第二份公告';
  hold.resolve(); await saving;
  assert.equal(h.node('#a-save').disabled, false);
  assert.equal(h.node('#a-ev').value, '正在编辑第二条');
  assert.equal(h.node('#a-src').value, '第二份公告');
  assert.equal(Object.values(h.server.remote)[0].evidence, '第一条证据');
});

test('successful manual retry removes failure details and leaves no stale failure message', async () => {
  let fail = true;
  const h = harness({ hook: request => request.method === 'PUT' && fail ? response(500, {}) : undefined });
  h.node('#a-ev').value = '重试的手记'; h.node('#a-src').value = '公告';
  h.fields.push({ dataset: { f: 'class' }, value: '噪声' });
  await h.add();
  assert.equal(h.node('#a-save').disabled, false);
  const id = Object.keys(h.state().states)[0];
  assert.equal(h.state().states[id].state, 'failed');
  assert.match(h.node('#gh-save-status').innerHTML, /HTTP 500/);
  fail = false; h.click({ retrySave: id }); await h.drain();
  assert.equal(h.state().states[id].state, 'saved');
  assert.doesNotMatch(h.node('#gh-save-status').innerHTML, /HTTP 500|data-retry-save/);
  assert.doesNotMatch(h.node('#banner').textContent, /保存失败|结果未确认/);
  assert.doesNotMatch(h.node('#a-msg').textContent, /保存失败|没存上|未确认/);
});

test('bulk confirms are queued before a later manual rejection, so latest user action wins', async () => {
  const hold = deferred();
  let first = true;
  const h = harness({ hook: async request => {
    if (request.method === 'PUT' && first) { first = false; await hold.promise; }
  } });
  h.run(`DATA.candidates = ${JSON.stringify([candidate('A'), candidate('B')])}`);
  h.click({ bulk: 'noise' });
  h.run(`record(DATA.candidates[1], 'reject', DATA.candidates[1].suggest)`);
  hold.resolve(); await h.drain(); await h.drain();
  assert.equal(h.server.remote.A.action, 'confirm');
  assert.equal(h.server.remote.B.action, 'reject');
});

test('immediate update waits for both the original queue and newly queued operations', async () => {
  const first = deferred(), second = deferred();
  let count = 0;
  const h = harness({ hook: async request => {
    if (request.method !== 'PUT') return;
    if (++count === 1) await first.promise; else await second.promise;
  } });
  const a = h.record('A');
  const running = h.run('ghRun()');
  const b = h.record('B');
  assert.equal(h.node('#gh-run').disabled, true);
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 0);
  first.resolve(); await a;
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 0);
  second.resolve(); await b; await running;
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 1);
  assert.deepEqual(Object.keys(h.server.remote).sort(), ['A','B']);
  assert.equal(h.node('#gh-run').disabled, false);
  assert.match(h.node('#gh-msg').textContent, /已受理/);
});

test('failed save prevents immediate update until explicitly retried', async () => {
  let fail = true;
  const h = harness({ hook: request => request.method === 'PUT' && fail ? response(500,{}) : undefined });
  await h.write('A', doc('A'));
  await h.run('ghRun()');
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 0);
  assert.match(h.node('#gh-msg').textContent, /未保存/);
  assert.equal(h.node('#gh-run').disabled, false);
  fail = false; h.click({retrySave:'A'}); await h.drain();
  await h.run('ghRun()');
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 1);
});

test('repeated update clicks dispatch once while a request is in flight', async () => {
  const hold = deferred();
  const h = harness({ hook: async request => { if (request.method === 'POST') await hold.promise; } });
  const running = h.run('ghRun()');
  await h.run('ghRun()');
  hold.resolve(); await running;
  assert.equal(h.server.requests.filter(r => r.method === 'POST').length, 1);
  assert.equal(h.node('#gh-run').disabled, false);
});

for (const outcome of ['network', 403, 500]) {
  test(`update ${outcome} failure leaves a clear message and unlocks the button`, async () => {
    const h = harness({ hook: request => {
      if (request.method !== 'POST') return;
      if (outcome === 'network') throw new Error('offline');
      return response(outcome, {});
    } });
    await h.run('ghRun()');
    assert.equal(h.node('#gh-run').disabled, false);
    assert.doesNotMatch(h.node('#gh-msg').textContent, /已受理|已经开始/);
    assert.match(h.node('#gh-msg').textContent, /未确认|权限|HTTP/);
  });
}
