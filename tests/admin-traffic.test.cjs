'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../admin/index.html'), 'utf8');
const start = html.indexOf('const TRAFFIC_DAY_MS');
const end = html.indexOf('function loginView', start);
assert.ok(start >= 0 && end > start);
const source = html.slice(start, end);
const now = Date.parse('2026-11-03T18:00:00Z');
const report = {
  schema_version: 1,
  timezone: 'Asia/Shanghai',
  collected_from: '2026-11-01T08:00:00+08:00',
  generated_at: '2026-11-03T17:00:00Z',
  days: [
    {date: '2026-11-02', pageviews: 0, visitors: 0, partial: false},
    {date: '2026-11-04', pageviews: 10, visitors: 3, partial: true},
  ],
};

function harness({locked = false, token = 'fixture', file = async () => ({text: null})} = {}) {
  const refresh = {disabled: false};
  const status = {textContent: ''};
  const content = {innerHTML: ''};
  const calls = [];
  const context = {
    Date: class extends Date { static now() { return now; } },
    STORE: 'github', ghToken: token,
    $: selector => ({
      '#traffic-refresh': refresh, '#traffic-status': status, '#traffic-content': content,
      '#app': {classList: {contains: name => name === 'locked' && locked}},
    })[selector],
    md: date => date.slice(5).replace('-', '/'),
    ghFile: async (...args) => { calls.push(args); return file(); },
  };
  const api = vm.runInNewContext(source + '\n({parseTrafficReport, trafficHTML});', context);
  return {api, refresh, status, content, calls};
}

test('recent trend separates real zero, missing dates and the current partial Beijing day', () => {
  const {api} = harness();
  const markup = api.trafficHTML(api.parseTrafficReport(JSON.stringify(report)));
  assert.match(markup, /今天[\s\S]+2026-11-04 · 当日数据未满[\s\S]+<dd>10<\/dd>[\s\S]+<dd>3<\/dd>/);
  assert.match(markup, /最近一个完整日[\s\S]+2026-11-02[\s\S]+<dd>0<\/dd>/);
  assert.match(markup, /2026-11-03[^\n]+\n\s+<td>—<\/td><td>—<\/td>/);
  assert.equal((markup.match(/<time datetime/g) || []).length, 14);
  assert.match(markup, /width:100%/);
  assert.match(markup, /width:30%/);
});

test('malformed, duplicate and out-of-coverage rows fail instead of being graphed', () => {
  const {api} = harness();
  for (const patch of [
    {timezone: 'UTC'},
    {generated_at: '2026-10-31T12:00:00Z'},
    {days: [report.days[0], report.days[0]]},
    {days: [{...report.days[0], date: '2026-11-31'}]},
    {days: [{...report.days[0], date: '2026-11-05'}]},
    {days: [{...report.days[0], pageviews: null}]},
    {days: [{...report.days[0], visitors: 1}]},
  ]) assert.throws(() => api.parseTrafficReport(JSON.stringify({...report, ...patch})));
});

test('statistics reads require an unlocked GitHub connection and stay lazy', async () => {
  assert.match(html, /if \(tab === "traffic" && !trafficLoaded\) loadTraffic\(\)/);
  const locked = harness({locked: true});
  await locked.refresh.onclick();
  assert.equal(locked.calls.length, 0);
  assert.match(locked.status.textContent, /请在已连接/);
  const connected = harness();
  assert.equal(connected.calls.length, 0);
  await connected.refresh.onclick();
  assert.deepEqual(connected.calls, [['private/site-traffic.json', true]]);
  assert.match(connected.status.textContent, /尚未接入/);
  assert.equal(connected.content.innerHTML, '');
  assert.equal(connected.refresh.disabled, false);
});

test('refresh failures preserve the last report and explain its age', async () => {
  let fail = false;
  const h = harness({file: async () => {
    if (fail) throw new Error('HTTP 503');
    return {text: JSON.stringify(report)};
  }});
  await h.refresh.onclick();
  assert.match(h.status.textContent, /报表生成 2026-11-04 01:00/);
  const last = h.content.innerHTML;
  fail = true;
  await h.refresh.onclick();
  assert.equal(h.content.innerHTML, last);
  assert.match(h.status.textContent, /暂时无法读取.*上次读取的报表/);
  assert.equal(h.refresh.disabled, false);
});
