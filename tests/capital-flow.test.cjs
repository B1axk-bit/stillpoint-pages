const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const helpers = html.match(/\/\* capital flow helpers \*\/([\s\S]*?)\/\* end capital flow helpers \*\//)[1];
function node(tag, attrs, ...children) {
  return {tag, attrs:attrs || {}, children:children.flat(Infinity).filter(x=>x != null),
    appendChild(child){ this.children.push(child); return child; },
    setAttribute(key, value){ this.attrs[key] = value; },
    set textContent(value){ this.children = [String(value)]; }};
}
const api = vm.runInNewContext(helpers + '\n({model:capitalFlowModel, render:renderCapitalFlow});', {
  h:node, document:{createElementNS:(_, tag)=>node(tag)}, MINUS:'−',
  num:(v,d)=>v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}),
  sgn:(v,d)=>v===0?v.toFixed(d):(v>0?'+':'−')+Math.abs(v).toFixed(d)
});
const days = ['2026-10-27','2026-10-28','2026-10-29','2026-10-30','2026-11-02'];
const make = overrides => Object.assign({
  scope_id:'eastmoney_sh_sz', unit:'亿元', status:'ok', date:'2026-11-02', value:0,
  history:days.map((date,i)=>({date,main_net_yi:[-4,2,-8,3,0][i]})), sum5_yi:-7,
  current:{date:'2026-11-02',unit:'亿元',inflow_yi:12,outflow_yi:12,net_yi:0}
}, overrides);
function walk(root){ const all=[]; (function visit(n){if(!n||typeof n!=='object')return;all.push(n);n.children.forEach(visit);})(root);return all; }
function text(n){return typeof n==='object'?n.children.map(text).join(' '):String(n);}

test('an observed zero remains a reading and plots at the neutral zero line',()=>{
  const m=api.model(make()); assert.equal(m.value,0); assert.equal(m.current.inflow_yi,12);
  const nodes=walk(api.render(make()));
  const bars=nodes.filter(n=>n.attrs.class==='cf-bar'); assert.equal(bars.length,5);
  assert.equal(bars[4].attrs.fill,'var(--muted)'); assert.equal(bars[4].attrs.y,105);
  assert.ok(nodes.some(n=>n.tag==='b'&&n.children.includes('0.00')));
});
test('gross amounts from another date cannot be shown beside the latest net value',()=>{
  const f=make({value:5,current:{date:'2026-10-30',unit:'亿元',inflow_yi:15,outflow_yi:10,net_yi:5}});
  const m=api.model(f);assert.equal(m.value,5);assert.equal(m.current,null);
  const stats=walk(api.render(f)).filter(n=>n.attrs.class==='cf-stat');
  assert.match(text(stats[0]),/—/);assert.match(text(stats[1]),/—/);
  assert.match(text(stats[2]),/\+5\.00/);
});
test('a mismatched gross difference is hidden rather than promoted to valid cash flow',()=>{
  const m=api.model(make({current:{date:'2026-11-02',unit:'亿元',inflow_yi:20,outflow_yi:12,net_yi:0}}));
  assert.equal(m.current,null);
});
test('historical net amounts never become invented historical gross flow amounts',()=>{
  const f=make({status:'partial',current:null});const root=api.render(f);
  assert.match(text(root),/未取得同日合格/);
  const headers=walk(root).filter(n=>n.tag==='th').map(text);
  assert.deepEqual(headers,['交易日','主力净额','超大单','大单','中单','小单']);
  assert.doesNotMatch(headers.join(''),/流入|流出/);
});
test('unsupported units or a different provider scope cannot be labelled as this series',()=>{
  for(const bad of [{unit:'元'},{scope_id:'wind_all_a'}]){
    const m=api.model(make(bad));assert.equal(m.value,null);assert.equal(m.rows.length,0);assert.equal(m.status,'failed');
  }
});
test('the chart uses red for inflows, green for outflows and supplies dated accessible bars',()=>{
  const bars=walk(api.render(make())).filter(n=>n.attrs.class==='cf-bar');
  assert.equal(bars[0].attrs.fill,'var(--neg)');assert.equal(bars[1].attrs.fill,'var(--pos)');
  assert.match(bars[0].attrs['aria-label'],/2026-10-27.*4\.00亿元/);
  assert.equal(bars[0].attrs.tabindex,'0');assert.equal(bars[0].attrs.y,105);
  assert.ok(bars[1].attrs.y<105);
});
test('missing, duplicate and invalid-date rows do not become zero bars or extra trading days',()=>{
  const history=make().history.concat([{date:'2026-11-02',main_net_yi:999},{date:'2026-11-03',main_net_yi:5},
    {date:'2026-02-30',main_net_yi:3},{date:'2026-10-26',main_net_yi:null}]);
  assert.equal(api.model(make({history})).rows.length,5);
});
test('fewer than five qualified days leaves the five-day total missing',()=>{
  assert.equal(api.model(make({history:make().history.slice(-4),sum5_yi:99})).sum5,null);
});
test('a carried series keeps its real observation day and warns without resetting it to the retrieval day',()=>{
  const f=make({status:'carried',retrieved_at:'2026-11-03T04:00:00+08:00'});
  const body=text(api.render(f));assert.match(body,/截至 2026-11-02.*沿用旧日/);assert.match(body,/本次读取未完成/);
});
test('empty provisional containers do not invent a pending intraday reading',()=>{
  for(const provisional of [null,[],{}]) assert.equal(api.model(make({provisional})).provisional,false);
  assert.equal(api.model(make({provisional:{date:'2026-11-03',status:'intraday'}})).provisional,true);
});
test('known gaps cannot be filled by an earlier day to manufacture a five-day total',()=>{
  const f=make({status:'partial',history_complete:false,sum5_yi:-7,sum5_count:0});
  assert.equal(api.model(f).sum5,null);
  assert.match(text(api.render(f)),/已核记录（历史有缺口）/);
});
