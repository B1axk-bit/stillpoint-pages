const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const block = html.match(/\/\* watch \*\/([\s\S]*?)\/\* paths \*\//)[1];

function render(value, label) {
  function h(tag, attrs, ...children) {
    return {tag, attrs:attrs || {}, children:children.flat(Infinity).filter(x=>x != null),
      appendChild(child) { this.children.push(child); return child; }};
  }
  const nodes = new Map();
  const $ = id => { if (!nodes.has(id)) nodes.set(id, h('div', {id})); return nodes.get(id); };
  vm.runInNewContext(block, {h, $, D:{watch:{head:'观察',sub:'',gauges:[{
    name:'最近会议加息概率',link:'利率',cur:value,curLabel:label,unit:'%',asof:'本次',
    state:'watch',stateLabel:'按来源资格显示',min:0,max:50,ticks:[0,25,50],note:'',src:''
  }]}}, pos:(v,min,max)=>(v-min)/(max-min)*100, plain:String, MINUS:'−',
    ticksRow:()=>h('div',{class:'ticks'})});
  const all=[]; const visit=n=>{ if (!n || typeof n !== 'object') return; all.push(n); n.children.forEach(visit); };
  visit($('gauges'));
  return all;
}
test('a missing meeting distribution keeps its label without inventing a zero-position reading', () => {
  const nodes=render(null,'—');
  assert.equal(nodes.filter(n=>n.attrs.class==='gg-mark').length,0);
  assert.ok(nodes.some(n=>n.attrs.class==='gg-num' && n.children.includes('—')));
});
test('an observed zero remains a real reading at the start of the scale', () => {
  const markers=render(0,'0').filter(n=>n.attrs.class==='gg-mark');
  assert.equal(markers.length,1); assert.equal(markers[0].attrs.style,'left:0%');
});
test('an observed nonzero probability retains its position and tooltip', () => {
  const markers=render(25,'25').filter(n=>n.attrs.class==='gg-mark');
  assert.equal(markers.length,1); assert.equal(markers[0].attrs.style,'left:50%');
  assert.match(markers[0].attrs['data-tip'],/^25%/);
});
