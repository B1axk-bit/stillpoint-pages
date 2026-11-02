const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const match = html.match(/\/\* responsive axis helpers \*\/([\s\S]*?)\/\* end responsive axis helpers \*\//);
assert.ok(match, 'the maintained responsive axis helpers must be available');
const api = vm.runInNewContext(match[1] + '\n({select:selectAxisLabels,fit:fitAxisLabels});');
const plain = value => JSON.parse(JSON.stringify(value));
function separated(rects, indices, gap=7){
  const ordered=indices.map(i=>rects[i]).sort((a,b)=>a.left-b.left);
  for(let i=1;i<ordered.length;i++) assert.ok(ordered[i].left-ordered[i-1].right>=gap-1e-9,
    `labels collide: ${JSON.stringify(ordered[i-1])} / ${JSON.stringify(ordered[i])}`);
}
function axis(ticks,width=170,formatter=v=>v>0?'+'+v:String(v)){
  const instance={width,labels:[]};
  instance.getBoundingClientRect=()=>({left:0,right:instance.width,width:instance.width});
  instance.querySelectorAll=selector=>{assert.match(selector,/em/);return instance.labels;};
  instance.labels=ticks.map((value,index)=>({
    index, hidden:false, textContent:formatter(value), dataset:{axisValue:String(value)},measurements:0,
    getAttribute(name){return name==='data-axis-value'?this.dataset.axisValue:null;},
    getBoundingClientRect(){
      this.measurements++;
      const labelWidth=this.textContent.length*6.3;
      const point=index/(ticks.length-1)*instance.width;
      const left=index===0?point:index===ticks.length-1?point-labelWidth:point-labelWidth/2;
      return this.hidden?{left:0,right:0,width:0,height:0}:{left,right:left+labelWidth,width:labelWidth,height:12};
    }
  }));
  return instance;
}
const ticks=Array.from({length:14},(_,i)=>-20+i*2);
function boxes(a){return a.labels.map(label=>({...label.getBoundingClientRect(),zero:label.dataset.axisValue==='0'}));}

test('the dense fourteen-tick A-share axis keeps legible spaced labels and its zero reference',()=>{
  const a=axis(ticks);const rects=boxes(a);const kept=plain(api.select(rects));
  assert.ok(kept.length<ticks.length,'crowded source ticks must be thinned');
  assert.ok(kept.includes(0));assert.ok(kept.includes(10));assert.ok(kept.includes(13));
  assert.deepEqual(kept,[...kept].sort((a,b)=>a-b));
  separated(rects,kept);
});

test('a centered interior label extending past the boundary cannot steal the domain minimum priority',()=>{
  const a=axis(ticks,110);const rects=boxes(a);
  assert.ok(rects[1].left<rects[0].left,'the first interior label extends left of the true minimum');
  const kept=plain(api.select(rects));
  assert.ok(kept.includes(0),'retain the supplied domain minimum rather than the leftmost text box');
  assert.ok(kept.includes(10));assert.ok(kept.includes(13));
  separated(rects,kept);
});

test('minimum, zero and maximum labels are all retained when their real widths fit',()=>{
  const rects=[{left:0,right:22},{left:44,right:50,zero:true},{left:80,right:100}];
  assert.deepEqual(plain(api.select(rects)),[0,1,2]);
});

test('zero near a boundary wins over a conflicting endpoint instead of forcing overlap',()=>{
  const rects=[{left:0,right:25},{left:46,right:52,zero:true},{left:50,right:75}];
  const kept=plain(api.select(rects));
  assert.ok(kept.includes(1));assert.ok(!kept.includes(2));
  separated(rects,kept);
});

test('even an extremely narrow axis can keep a safe zero reference without compulsory endpoints',()=>{
  const rects=[{left:0,right:20},{left:10,right:16,zero:true},{left:12,right:32}];
  assert.deepEqual(plain(api.select(rects)),[1]);
});

test('long locale-formatted numeric labels are fitted by their boxes rather than by tick count',()=>{
  const rects=[{left:0,right:38},{left:28,right:66},{left:56,right:94},{left:84,right:122},{left:112,right:150}];
  const kept=plain(api.select(rects));
  assert.ok(kept.length<rects.length);assert.ok(kept.includes(0));assert.ok(kept.includes(4));
  separated(rects,kept);
});

test('the selection respects a caller-supplied minimum gap',()=>{
  const rects=[{left:0,right:10},{left:18,right:28},{left:36,right:46}];
  const kept=plain(api.select(rects,10));separated(rects,kept,10);
  assert.equal(kept.length,2);
});

test('empty, nonfinite and zero-width boxes do not become phantom tick labels',()=>{
  assert.deepEqual(plain(api.select([])),[]);
  const rects=[{left:0,right:0},{left:NaN,right:10},{left:4,right:Infinity},{left:20,right:15},{left:30,right:38,zero:true}];
  assert.deepEqual(plain(api.select(rects)),[4]);
});

test('selecting labels leaves the source values and rectangle descriptions intact',()=>{
  const rects=[{left:0,right:20},{left:15,right:23,zero:true},{left:24,right:45}];
  const before=JSON.stringify(rects);api.select(rects);assert.equal(JSON.stringify(rects),before);
});

test('fitting restores labels after a narrow chart becomes wider',()=>{
  const a=axis(ticks,110);const before=a.labels.map(e=>({value:e.dataset.axisValue,text:e.textContent}));
  api.fit(a);
  const narrow=a.labels.filter(e=>!e.hidden).map(e=>e.index);
  assert.ok(narrow.length<ticks.length);assert.ok(narrow.includes(10));
  a.width=600;api.fit(a);
  const wide=a.labels.filter(e=>!e.hidden).map(e=>e.index);
  assert.equal(wide.length,ticks.length,'previously hidden labels must be measured and restored');
  assert.ok(wide.length>narrow.length);
  assert.deepEqual(a.labels.map(e=>({value:e.dataset.axisValue,text:e.textContent})),before);
});

test('a hidden zero-width ancestor is deferred and fitted once it becomes visible',()=>{
  const a=axis(ticks,0);a.labels.forEach(e=>{e.hidden=true;});
  api.fit(a);
  assert.ok(a.labels.every(e=>!e.hidden),'zero width must not permanently discard any ticks');
  assert.ok(a.labels.every(e=>e.measurements===0),'defer unusable geometry');
  a.width=170;api.fit(a);
  const shown=a.labels.filter(e=>!e.hidden).map(e=>e.index);
  assert.ok(shown.length<ticks.length);assert.ok(shown.includes(10));
});

test('the shared numeric metadata identifies zero even when a formatter uses another label',()=>{
  const a=axis([-1,0,1],25,v=>v===0?'balance':String(v));
  api.fit(a);assert.equal(a.labels[1].hidden,false);
});

test('the manually rendered macro axis can identify a plain zero without metadata',()=>{
  const a=axis([-1,-0.5,0,0.5,1],60);a.labels.forEach(e=>{delete e.dataset.axisValue;});
  api.fit(a);assert.equal(a.labels[2].hidden,false);
  assert.ok(a.labels.some(e=>e.hidden));
});
