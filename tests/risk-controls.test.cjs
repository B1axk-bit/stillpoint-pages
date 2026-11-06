const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const admin = fs.readFileSync(path.join(__dirname, '../admin/index.html'), 'utf8');
const front = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));
const adminHelpers = ['riskControlView', 'riskControlHTML'].map(name =>
  admin.match(new RegExp('function ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n\\}'))[0]).join('\n');
const esc = `const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));`;
const adminApi = vm.runInNewContext(`${esc}\n${adminHelpers}\n({riskControlView,riskControlHTML});`);
const frontHelpers = front.slice(front.indexOf('  function riskControlView(dr){'), front.indexOf('  function sgn('));
const frontApi = vm.runInNewContext(`function h(tag, props, ...children){return {tag,props,children};}\n${frontHelpers}\n({riskControlView,riskControlNode});`);
const flatten = value => typeof value === 'object' && value ? (Array.isArray(value) ? value.map(flatten).join('') : flatten(value.children)) : (value ?? '');
function fixture(){
  return {tier:2, legacy:{tier:1,raw:1}, control:{version:'v1.4.0', evaluated_at:'2026-11-06T14:30:00+08:00', market_date:'2026-11-05', minimum_tier:2, status:'active',
    next_review_at:'2026-11-07T06:00:00+08:00', reasons:[{id:'theme',label:'本主题承接',tier:2,status:'stress',reason:'融资约束与价格承接受损并存',release_condition:'同主题出现对应缓解证据',next_review_at:'2026-11-07T06:00:00+08:00',source_path:'analysis/evidence/private.json'}],
    downgrade:{allowed:false,clear_periods:0,required_periods:2,blockers:['尚缺本主题缓解证据']},private_holdings:'secret'}};
}
test('old derisk data renders no new control block and retains backward compatibility',()=>{
  assert.equal(adminApi.riskControlHTML({tier:1}), '');
  assert.equal(frontApi.riskControlNode({tier:1}), null);
});
test('public and admin summaries show effective and legacy tier, timing and release requirements',()=>{
  const dr=fixture(), html=adminApi.riskControlHTML(dr), nodeText=flatten(frontApi.riskControlNode(dr));
  for(const text of ['当前生效 2 档','旧规则对照 1 档','暂不降档','改善确认 0 / 2','解除条件','2026-11-05','2026-11-06 14:30 北京时间','2026-11-07 06:00 北京时间','v1.4.0']){
    assert.ok(html.includes(text),text); assert.ok(nodeText.includes(text),text);
  }
});
test('presentation never copies raw private fields, sources or evidence records',()=>{
  const dr=fixture(), html=adminApi.riskControlHTML(dr), nodeText=flatten(frontApi.riskControlNode(dr));
  assert.doesNotMatch(html,/analysis\/evidence|private_holdings|secret/);
  assert.doesNotMatch(nodeText,/analysis\/evidence|private_holdings|secret/);
});
test('both summaries present supplied policy data without recalculating or mutating the tier',()=>{
  const dr=fixture(), before=JSON.stringify(dr);
  assert.deepEqual(clone(adminApi.riskControlView(dr)),clone(frontApi.riskControlView(dr)));
  adminApi.riskControlHTML(dr); frontApi.riskControlNode(dr);
  assert.equal(JSON.stringify(dr),before);
  dr.tier=3;
  assert.match(adminApi.riskControlHTML(dr),/当前生效 3 档/);
});
test('zero confirmations and zero legacy tier remain real zero values',()=>{
  const dr=fixture();dr.legacy.tier=0;
  const v=adminApi.riskControlView(dr);
  assert.equal(v.legacyTier,0);assert.equal(v.clearPeriods,0);
});
test('unresolved review and malformed optional rows remain readable without inventing relief',()=>{
  const dr=fixture();dr.control.status='held_pending_review';dr.control.reasons=[null,'bad'];
  dr.control.downgrade={allowed:false,blockers:['数据待核']};
  assert.match(adminApi.riskControlHTML(dr),/待核复检，暂维持/);
  assert.match(adminApi.riskControlHTML(dr),/暂不降档/);
  assert.doesNotMatch(adminApi.riskControlHTML(dr),/undefined|NaN|改善确认/);
});
test('all text is escaped in admin HTML, while public nodes retain inert text',()=>{
  const dr=fixture();dr.control.reasons[0].reason='<img src=x onerror=alert(1)>';
  assert.doesNotMatch(adminApi.riskControlHTML(dr),/<img /);
  assert.match(adminApi.riskControlHTML(dr),/&lt;img/);
  assert.equal(frontApi.riskControlNode(dr).tag,'section');
});
test('rules page labels active risk policy separately from retained legacy rules',()=>{
  const renderRules=admin.match(/function renderRules\([^)]*\) \{[\s\S]*?\n\}/)[0];
  const data={points:{},strength:[],changelog:[],version:'v1.3.2',derisk:{rules:['旧条件'],tier2:'原比例二',tier3:'原比例三',status:'旧约定'},riskControlRubric:{version:'v1.4.0',rules:['新降档条件'],status:'已批准'}};
  const render=fixture=>vm.runInNewContext(`${esc}\nconst DATA=${JSON.stringify(fixture)};const node={innerHTML:''};const $=()=>node;const ptsTag=()=>'';${renderRules}\nrenderRules();node.innerHTML;`);
  const current=render(data);
  assert.match(current,/当前风险衔接规则 · v1\.4\.0/);assert.match(current,/新降档条件/);assert.match(current,/旧规则对照/);assert.match(current,/计分 v1\.3\.2/);
  delete data.riskControlRubric;
  const legacy=render(data);assert.match(legacy,/>减仓档</);assert.doesNotMatch(legacy,/当前风险衔接规则|旧规则对照/);
});
