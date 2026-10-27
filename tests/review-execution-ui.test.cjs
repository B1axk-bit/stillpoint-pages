const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const admin = fs.readFileSync(path.join(__dirname, '../admin/index.html'), 'utf8');
const front = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const helpers = ['reviewEvidenceGroups', 'reviewEvidenceHTML', 'executionBoundaryHTML'].map(name =>
  admin.match(new RegExp('function '+name+'\\([^)]*\\) \\{[\\s\\S]*?\\n\\}'))[0]).join('\n');
const api = vm.runInNewContext(`const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));\n${helpers}\n({reviewEvidenceGroups,reviewEvidenceHTML,executionBoundaryHTML});`);
const clone = value => JSON.parse(JSON.stringify(value));
const item = (toward, layer, date, evidence, cls = '新独立') => ({toward,layer,date,evidence,class:cls});
const theme = () => ({jumps:['H3','失效','H3'],items:[
  item('H3','订单','2026-10-21','甲'), item('H3','融资','2026-10-22','乙'),
  item('H3','订单','2026-10-21','丙'),item('H3','部署','2026-10-23','幅度不是新独立','幅度'),
  item('支持','订单','2026-10-24','支持当前主线'),item('H2','利率','2026-10-24','未触发方向'),
  item('失效','分化','2026-10-20','丁'),item('失效','融资','2026-10-22','戊')
]});

test('groups explain only already-triggered directions and count unique layers/dates', () => {
  const groups=clone(api.reviewEvidenceGroups(theme()));
  assert.deepEqual(groups.map(g=>g.target),['H3','失效']);
  assert.deepEqual(groups.map(g=>[g.layers.length,g.dates.length]),[[2,2],[2,2]]);
  assert.equal(groups[0].rows.length,3);
  assert.deepEqual(groups[0].dates,['2026-10-21','2026-10-22']);
});
test('UI does not create a new jump from evidence when the calculation supplied none', () => {
  const data=theme();data.jumps=[];
  assert.equal(api.reviewEvidenceGroups(data).length,0);
  assert.equal(api.reviewEvidenceHTML(data),'');
});
test('server-filtered current-window evidence takes precedence over historical ledger items', () => {
  const data=theme();data.jump_evidence=[item('H3','部署','2026-10-23','本期窗口')];
  const groups=clone(api.reviewEvidenceGroups(data));
  assert.deepEqual(groups[0].rows.map(r=>r.evidence),['本期窗口']);
  assert.equal(groups[1].rows.length,0);
});
test('grouping does not mutate ledger items or trigger directions', () => {
  const data=theme(),before=JSON.stringify(data);api.reviewEvidenceGroups(data);api.reviewEvidenceHTML(data);
  assert.equal(JSON.stringify(data),before);
});
test('missing layer/date is not filled into a manufactured two-layer trigger', () => {
  const groups=clone(api.reviewEvidenceGroups({jumps:['H3'],items:[item('H3','','','未注明')]}));
  assert.equal(groups[0].layers.length,0);assert.equal(groups[0].dates.length,0);
});
test('all ledger strings are escaped in the read-only disclosure', () => {
  const html=api.reviewEvidenceHTML({jumps:['H3'],items:[item('H3','<script>','2026-10-21','<img src=x onerror=alert(1)>')]});
  assert.doesNotMatch(html,/<img|<script>/);assert.match(html,/&lt;img/);
  assert.match(html,/尚未自动判失效/);assert.match(html,/不在前端重新计算/);
});
test('execution explanation covers scope, calibration, missing execution and no daily recursion', () => {
  const html=api.executionBoundaryHTML();
  for(const term of ['风控预案','尚未完成效果验证','不等同高胜率卖单','不是全部资产','尚无本档个人执行记录','不得每天对余仓重复减1/3'])assert.ok(html.includes(term),term);
});
test('public disclosure has aggregate metadata and explanatory copy, with no raw ledger evidence', () => {
  const D=JSON.parse(front.match(/<script[^>]*id="page-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
  assert.ok(Number.isFinite(D.mainline.score));
  assert.ok(Array.isArray(D.mainline.review.groups));
  for (const group of D.mainline.review.groups) {
    assert.equal(new Set(group.layers).size,group.layers.length);
    assert.equal(new Set(group.dates).size,group.dates.length);
  }
  const added=JSON.stringify({review:D.mainline.review,execution:D.execution});
  assert.doesNotMatch(added,/"evidence"|"shares"|"holdings"|"buy_price"/);
  assert.match(added,/不得每天对余仓重复减1\/3/);
});
