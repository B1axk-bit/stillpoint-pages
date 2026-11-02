const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const match = html.match(/\/\* agenda helpers \*\/([\s\S]*?)\/\* end agenda helpers \*\//);
assert.ok(match, 'the maintained agenda helpers must be available to exercise');
function node(tag, attrs, ...children) {
  return {tag, attrs:attrs || {}, children:children.flat(Infinity).filter(x=>x != null && x !== false),
    appendChild(child){ this.children.push(child); return child; },
    setAttribute(key, value){ this.attrs[key] = value; },
    set textContent(value){ this.children = [String(value)]; }};
}
const api = vm.runInNewContext(match[1] + '\n({date:agendaDateKey, model:agendaModel, render:renderAgenda});', {
  h:node, Date, Intl, document:{createElement:tag=>node(tag)}
});
const now = new Date('2026-11-02T08:00:00Z');
const make = overrides => Object.assign({
  start:'2026-10-19', end:'2026-11-13', events:[], reviews:[]
}, overrides);
const event = (d,label,extra={}) => Object.assign({d,label,time:d + ' 23:00北京 · 待核验'},extra);
const plain = value => JSON.parse(JSON.stringify(value));
function walk(root){ const all=[]; (function visit(n){if(!n||typeof n!=='object')return;all.push(n);n.children.forEach(visit);})(root);return all; }
function text(n){return n && typeof n==='object'?n.children.map(text).join(' '):String(n ?? '');}
function allGroups(m){return [...m.upcoming,...m.past,...m.later];}

test('the calendar changes at Beijing midnight rather than the device local midnight',()=>{
  assert.equal(api.date(new Date('2026-11-02T15:59:59.999Z')),'2026-11-02');
  assert.equal(api.date(new Date('2026-11-02T16:00:00.000Z')),'2026-11-03');
  assert.equal(api.date(new Date('2026-11-03T07:59:59-08:00')),'2026-11-03');
});

test('Beijing date rollover handles month, leap day and year boundaries',()=>{
  assert.equal(api.date(new Date('2026-10-31T16:00:00Z')),'2026-11-01');
  assert.equal(api.date(new Date('2028-02-28T16:00:00Z')),'2028-02-29');
  assert.equal(api.date(new Date('2028-02-29T16:00:00Z')),'2028-03-01');
  assert.equal(api.date(new Date('2026-12-31T16:00:00Z')),'2027-01-01');
});

test('the visible fourteen-day window advances beyond the old frozen source bounds',()=>{
  const a=make({events:[event('2026-11-02','今日'),event('2026-11-15','末日'),event('2026-11-16','稍后')]});
  const first=api.model(a,now);
  assert.equal(first.today,'2026-11-02');assert.equal(first.end,'2026-11-15');
  assert.deepEqual(plain(first.upcoming.map(g=>g.date)),['2026-11-02','2026-11-15']);
  assert.deepEqual(plain(first.later.map(g=>g.date)),['2026-11-16']);
  const advanced=api.model(a,new Date('2026-11-02T16:00:00Z'));
  assert.equal(advanced.today,'2026-11-03');assert.equal(advanced.end,'2026-11-16');
  assert.deepEqual(plain(advanced.past.map(g=>g.date)),['2026-11-02']);
  assert.deepEqual(plain(advanced.upcoming.map(g=>g.date)),['2026-11-15','2026-11-16']);
});

test('the rolling window crosses a year without manufacturing event dates',()=>{
  const a=make({events:[event('2026-12-31','跨年日程'),event('2027-01-13','窗口末日'),event('2027-01-14','后续')]});
  const m=api.model(a,new Date('2026-12-31T16:00:00Z'));
  assert.equal(m.today,'2027-01-01');assert.equal(m.end,'2027-01-14');
  assert.deepEqual(plain(m.past.map(g=>g.date)),['2026-12-31']);
  assert.deepEqual(plain(m.upcoming.map(g=>g.date)),['2027-01-13','2027-01-14']);
});

test('dense same-day events share a chronological group and keep complete time and status labels',()=>{
  const events=[
    event('2026-11-05','BOJ 9月会议纪要',{row:1,time:'11/5 07:50北京 · 非10月会议'}),
    event('2026-11-04','微软债预计交割',{row:2,key:true,time:'公告预计11/4 · 待实际交割核验'}),
    event('2026-11-04','日本货币基础',{row:0,time:'11/4 07:50北京'}),
    event('2026-11-03','美国JOLTS',{row:0,key:true,time:'11/3 23:00北京'})
  ];
  const a=make({events});const m=api.model(a,now);
  assert.deepEqual(plain(m.upcoming.map(g=>g.date)),['2026-11-03','2026-11-04','2026-11-05']);
  assert.equal(m.upcoming[1].events.length,2);
  const body=text(api.render(a,now));
  for(const e of events){assert.ok(body.includes(e.label),e.label);assert.ok(body.includes(e.time),e.time);}
});

test('a conference already in progress stays current while retaining its original range',()=>{
  const original=event('2026-11-01','两日会议',{d2:'2026-11-02',time:'11/1–2 · 待核',key:true});
  const a=make({events:[original,event('2026-10-27','已结束会议',{d2:'2026-10-28',time:'10/27–28 · 已公布'})]});
  const m=api.model(a,now);
  assert.equal(m.upcoming.length,1);assert.equal(m.upcoming[0].date,'2026-11-02');
  assert.equal(m.upcoming[0].events[0].d,'2026-11-01');assert.equal(m.upcoming[0].events[0].d2,'2026-11-02');
  assert.equal(m.past[0].date,'2026-10-27');
  assert.equal(m.next.date,'2026-11-02');assert.equal(m.next.label,'两日会议');
  assert.equal(a.events[0].d,original.d);
});

test('same-date review entries merge their case numbers without duplicating or dropping cases',()=>{
  const m=api.model(make({reviews:[{d:'2026-11-03',cases:[18,2]},{d:'2026-11-03',cases:[2,3,18]}]}),now);
  assert.equal(m.upcoming.length,1);
  assert.deepEqual(plain(m.upcoming[0].reviews).sort((a,b)=>a-b),[2,3,18]);
});

test('past source records and their verification status are retained without being rewritten',()=>{
  const a=make({events:[event('2026-10-28','微软财报',{time:'10/28 · 已公布',key:true}),event('2026-11-03','未来数据')],reviews:[{d:'2026-11-01',cases:[18]}]});
  const before=JSON.stringify(a);const m=api.model(a,now);const body=text(api.render(a,now));
  assert.deepEqual(plain(m.past.map(g=>g.date)),['2026-10-28','2026-11-01']);
  assert.equal(m.past[0].events[0].time,'10/28 · 已公布');
  assert.ok(body.includes('微软财报'));assert.ok(body.includes('10/28 · 已公布'));
  assert.doesNotMatch(body,/案例18.*(?:未完成|已完成)/);
  assert.equal(JSON.stringify(a),before);
});

test('records beyond the visible window remain available for the later schedule and next checkpoint',()=>{
  const a=make({events:[event('2026-12-02','远期数据',{key:true})],reviews:[{d:'2026-11-20',cases:[18]}]});
  const m=api.model(a,now);
  assert.equal(m.upcoming.length,0);
  assert.deepEqual(plain(m.later.map(g=>g.date)),['2026-11-20','2026-12-02']);
  assert.equal(m.futureEvents[0].d,'2026-12-02');
  assert.equal(m.next.date,'2026-11-20');assert.equal(m.next.kind,'review');
  assert.ok(text(api.render(a,now)).includes('远期数据'));
});

test('the next checkpoint uses future key events instead of the first historical key event',()=>{
  const a=make({events:[event('2026-10-27','旧FOMC',{key:true}),event('2026-11-03','普通事件'),event('2026-11-05','下一重要事件',{key:true})]});
  const m=api.model(a,now);
  assert.equal(m.next.date,'2026-11-05');assert.equal(m.next.label,'下一重要事件');
  assert.equal(m.next.kind,'event');assert.equal(m.futureEvents.length,2);
});

test('a review earlier than the selected key event becomes the next checkpoint',()=>{
  const a=make({events:[event('2026-11-05','重要事件',{key:true})],reviews:[{d:'2026-11-03',cases:[18]}]});
  const m=api.model(a,now);
  assert.equal(m.next.date,'2026-11-03');assert.equal(m.next.kind,'review');
  assert.equal(typeof m.next.label,'string');assert.equal(typeof m.next.time,'string');
});

test('without a future key event the earliest future event is selected in date order',()=>{
  const a=make({events:[event('2026-11-08','较晚'),event('2026-11-03','最早'),event('2026-10-29','已过去')]});
  const m=api.model(a,now);assert.equal(m.next.date,'2026-11-03');assert.equal(m.next.label,'最早');
});

test('missing or impossible dates cannot roll over into fabricated dated groups',()=>{
  const a=make({events:[event('2026-02-30','错误日'),event('2026-13-01','错误月'),event('2026-11-2','格式不齐'),event('','缺日期'),event('2026-11-03','合法日')],reviews:[{d:'2026-02-30',cases:[99]},{d:'bad',cases:[100]}]});
  const before=JSON.stringify(a);const m=api.model(a,now);
  assert.deepEqual(plain(allGroups(m).map(g=>g.date)),['2026-11-03']);
  assert.equal(m.futureEvents.length,1);assert.equal(m.next.label,'合法日');
  assert.equal(JSON.stringify(a),before);
});

test('empty and all-past calendars have a null checkpoint without inventing future events',()=>{
  for(const a of [make(),make({events:[event('2026-10-28','过去事件',{key:true})],reviews:[{d:'2026-11-01',cases:[1]}]})]){
    const m=api.model(a,now);
    assert.equal(m.next,null);assert.equal(m.upcoming.length,0);assert.equal(m.later.length,0);
    assert.equal(m.futureEvents.length,0);
    const body=text(api.render(a,now));assert.doesNotMatch(body,/undefined|NaN|Invalid Date/);
  }
});

test('the rendered agenda exposes semantic lists and expandable retained history instead of absolute labels',()=>{
  const a=make({events:[event('2026-10-28','历史'),event('2026-11-03','近期'),event('2026-12-02','后续')],reviews:[{d:'2026-11-03',cases:[18]}]});
  const nodes=walk(api.render(a,now));
  assert.ok(nodes.some(n=>n.tag==='ol'));assert.ok(nodes.some(n=>n.tag==='li'));
  assert.ok(nodes.filter(n=>n.tag==='details').length>=2);assert.ok(nodes.filter(n=>n.tag==='summary').length>=2);
  assert.ok(nodes.some(n=>n.tag==='time' && n.attrs.datetime==='2026-11-03'));
  assert.ok(nodes.every(n=>n.attrs.role!=='img'),'event content must not be hidden behind an image role');
  assert.ok(nodes.every(n=>!String(n.attrs.class || '').split(/\s+/).includes('tl-ev')));
  assert.ok(nodes.every(n=>!/position\s*:\s*absolute|(?:^|;)\s*left\s*:/.test(String(n.attrs.style || ''))));
});

const controllerMatch = html.slice(html.indexOf('/* end agenda helpers */')).match(/\/\* agenda \*\/([\s\S]*?)\/\* log \*\//);
assert.ok(controllerMatch, 'exercise the actual maintained calendar controller');
function controllerFixture(a, initialClock) {
  let clock=Date.parse(initialClock);
  class FakeDate extends Date {
    constructor(...args){super(...(args.length ? args : [clock]));}
    static now(){return clock;}
  }
  const ids={'a-h':node('h2'),'a-sub':node('p'),'agenda-box':node('div')};
  const unrelated=node('section',null,'research and money-flow content unchanged');
  const reads=[],timers=[],documentListeners={},windowListeners={};
  const document={hidden:false,addEventListener(name,callback){documentListeners[name]=callback;}};
  const context=vm.createContext({
    h:node,Date:FakeDate,Intl,D:{agenda:a,edition:{label:'2026-11-02 fixed research edition'}},
    $:id=>{reads.push(id);assert.ok(Object.hasOwn(ids,id),'controller must stay within the agenda: '+id);return ids[id];},
    document,window:{addEventListener(name,callback){windowListeners[name]=callback;}},
    setTimeout(callback,delay){timers.push({callback,delay});return timers.length;}
  });
  vm.runInContext(match[1]+'\n'+controllerMatch[1],context);
  return {context,ids,unrelated,reads,timers,document,documentListeners,windowListeners,
    setClock(value){clock=typeof value==='number'?value:Date.parse(value);},
    root(){return ids['agenda-box'].children.find(child=>child && typeof child==='object');}};
}

test('the actual midnight controller rerenders only the calendar and notifies its header callback',()=>{
  const a=make({head:'日程标题',sub:'原有日期说明',events:[event('2026-11-02','今日事件'),event('2026-11-03','明日事件',{key:true})]});
  const original=JSON.stringify(a);
  const s=controllerFixture(a,'2026-11-02T15:59:59Z');
  const initialRoot=s.root();const notifications=[];
  s.context.onAgendaRefresh=()=>notifications.push(s.context.agendaView.today);
  assert.equal(s.context.agendaView.today,'2026-11-02');
  assert.equal(s.timers[0].delay,1250);
  s.setClock('2026-11-02T16:00:00.250Z');
  s.timers[0].callback();
  assert.equal(s.context.agendaView.today,'2026-11-03');
  assert.equal(s.root().attrs['data-today'],'2026-11-03');
  assert.notEqual(s.root(),initialRoot,'rollover must update the live calendar subtree');
  assert.deepEqual(notifications,['2026-11-03']);
  assert.equal(s.timers.length,2,'the next Beijing rollover remains scheduled');
  assert.equal(s.timers[1].delay,86400000);
  assert.equal(text(s.ids['a-h']),'日程标题');assert.equal(text(s.ids['a-sub']),'原有日期说明');
  assert.equal(text(s.unrelated),'research and money-flow content unchanged');
  assert.equal(JSON.stringify(a),original);
});

test('visibility and pageshow resume the calendar after sleep without rewriting dated source records',()=>{
  const a=make({events:[event('2026-11-02','已发布',{time:'11/2 · 已核'}),event('2026-11-05','后续事件')],reviews:[{d:'2026-11-04',cases:[18]}]});
  const original=JSON.stringify(a);const s=controllerFixture(a,'2026-11-02T08:00:00Z');
  const notifications=[];s.context.onAgendaRefresh=()=>notifications.push(s.context.agendaView.today);
  s.setClock('2026-11-04T08:00:00Z');s.document.hidden=true;
  s.documentListeners.visibilitychange();
  assert.equal(s.context.agendaView.today,'2026-11-02','a hidden page waits for actual resume');
  s.document.hidden=false;s.documentListeners.visibilitychange();
  assert.equal(s.context.agendaView.today,'2026-11-04');
  assert.equal(s.root().attrs['data-today'],'2026-11-04');
  assert.equal(s.context.agendaView.next.date,'2026-11-04');
  s.documentListeners.visibilitychange();
  assert.deepEqual(notifications,['2026-11-04'],'same-day resume does not cause duplicate rerenders');
  s.setClock('2026-11-05T08:00:00Z');s.windowListeners.pageshow();
  assert.equal(s.context.agendaView.today,'2026-11-05');
  s.windowListeners.focus();
  assert.deepEqual(notifications,['2026-11-04','2026-11-05']);
  assert.equal(s.context.agendaView.past.find(g=>g.date==='2026-11-02').events[0].time,'11/2 · 已核');
  assert.equal(JSON.stringify(a),original);
  assert.equal(text(s.unrelated),'research and money-flow content unchanged');
});
