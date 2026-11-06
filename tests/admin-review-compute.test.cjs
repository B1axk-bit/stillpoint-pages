'use strict';

// Exercise the shipped controller against an isolated GitHub fixture. No token,
// live decision, Actions run or real repository mutation is used by these tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {TextEncoder, TextDecoder} = require('node:util');
const {createHash, webcrypto} = require('node:crypto');
const inline = fs.readFileSync(path.join(__dirname,'../admin/index.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const source=inline.replace(/if \(STORE === "claude"\) \{ start\(\); connectClaude\(\); \}\s*else \{[\s\S]*?\}\s*$/, '');
const clone = x => JSON.parse(JSON.stringify(x));
const hash = text => createHash('sha256').update(text).digest('hex');
const blob = text => createHash('sha1').update(`blob ${Buffer.byteLength(text)}\0${text}`).digest('hex');
const response=(status,value)=>({status,ok:status>=200&&status<300,json:async()=>clone(value),text:async()=>String(value)});
function deferred() {let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
const decision=(id,note='')=>({cid:id,action:'confirm',date:'2026-11-05',theme:'美股 AI',class:'幅度',toward:'支持',strength:'M',layer:'融资',cluster:'融资压力',evidence:`证据${id}`,note,at:'2026-11-06T01:00:00Z',source:'公告'});
function latest(score=70,tier=1) {return {snapshot:'snapshot_test.json',run_at:'2026-11-06 09:50',version:'v1.3.2',lamps:[],themes:[{theme:'美股 AI',cell:'H1',score,band:'测试',since:'2026-10-15',alerts:[],items:[],fading:[],derisk:{tier,raw:tier,name:'测试',action:'测试',why:[]}}],points:{}};}

function harness({initial={},hook}={}) {
  const nodes=new Map(),windowListeners=new Map(),documentListeners=new Map(),timers=new Map();let timerId=0;
  function node(selector) {
    if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',value:'',disabled:false,dataset:{},listeners:new Map(),
      classList:{add(){},remove(){},contains(){return false;},toggle(){}},addEventListener(t,f){this.listeners.set(t,f);},
      setAttribute(){},getAttribute(){return null;},querySelector:s=>node(selector+' '+s),querySelectorAll:()=>[],insertAdjacentHTML(_p,v){this.innerHTML+=v;}});
    return nodes.get(selector);
  }
  const server={decisions:clone(initial),files:new Map(),requests:[],receipt:null};
  function putJSON(p,v){server.files.set(p,JSON.stringify(v)+'\n');}
  function updateDecisionFile(){putJSON('confidence/decisions.json',server.decisions);}
  updateDecisionFile();putJSON('confidence/latest.json',latest());putJSON('confidence/candidates.json',{candidates:[],generated:'old'});
  server.files.set('confidence/reviewed.csv','id,date,action,changed,ledger,class,machine_class,evidence,reviewed_at\n');
  server.files.set('confidence/ledger.csv','date,theme,class,toward,strength,layer,cluster,evidence,source\n');
  putJSON('confidence/rubric.json',{strength:[],changelog:[]});
  const context=vm.createContext({TextEncoder,TextDecoder,URL,console,crypto:webcrypto,
    btoa:x=>Buffer.from(x,'binary').toString('base64'),atob:x=>Buffer.from(x,'base64').toString('binary'),
    setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},matchMedia:()=>({matches:false}),location:{reload(){}},
    window:{addEventListener:(t,f)=>windowListeners.set(t,f)},
    document:{visibilityState:'visible',documentElement:node('html'),getElementById:id=>node('#'+id),querySelector:node,querySelectorAll:()=>[],addEventListener:(t,f)=>documentListeners.set(t,f)},
    fetch:async(url,opt={})=>{
      assert.ok(url.startsWith('https://api.github.com/repos/B1axk-bit/stillpoint-data/'));
      const route=url.split('/stillpoint-data/')[1].split('?')[0],method=opt.method||'GET';
      const req={route,method,body:opt.body?JSON.parse(opt.body):null};server.requests.push(req);
      const override=hook&&await hook(req,server);if(override)return override;
      if(method==='POST'){assert.match(route,/actions\/workflows\/(review|snapshot)\.yml\/dispatches/);return response(204,{});}
      const name=decodeURIComponent(route.replace(/^contents\//,''));
      if(method==='PUT'){
        assert.equal(name,'confidence/decisions.json');
        if(req.body.sha!==blob(server.files.get(name)))return response(409,{});
        server.decisions=JSON.parse(Buffer.from(req.body.content,'base64').toString('utf8'));updateDecisionFile();
        return response(200,{content:{sha:blob(server.files.get(name))}});
      }
      assert.equal(method,'GET');
      const text=server.files.get(name);if(text===undefined)return response(404,{});
      return response(200,{sha:blob(text),encoding:'base64',content:Buffer.from(text).toString('base64')});
    }});
  vm.runInContext(source,context,{filename:'admin/index.html'});const run=x=>vm.runInContext(x,context);
  context.__data=latest();context.__initial=clone(initial);context.__sha=blob(server.files.get('confidence/decisions.json'));
  run("DATA={...__data,candidates:[],synced:[]};STORE='github';canWrite=true;ghToken='fixture';ghSaved=__initial;decisions={...ghSaved};ghSha=__sha;");
  function publish({items,removed,status='completed',score=82,tier=2,error,sourceSha}={}) {
    putJSON('confidence/latest.json',latest(score,tier));putJSON('confidence/candidates.json',{candidates:[],generated:'fresh'});
    const reviewed=Object.entries(server.decisions).map(([id,d])=>`${id},${d.date},${d.action},0,${['噪声','他题'].includes(d.class)?0:1},${d.class},幅度,${d.evidence},2026-11-06 10:00`);
    server.files.set('confidence/reviewed.csv','id,date,action,changed,ledger,class,machine_class,evidence,reviewed_at\n'+reviewed.join('\n')+'\n');
    const r={schema_version:1,status,generated_at:'2026-11-06T02:00:00Z',source:{decisions_blob_sha:sourceSha||blob(server.files.get('confidence/decisions.json')),run_id:'42',run_url:'https://github.com/B1axk-bit/stillpoint-data/actions/runs/42'},
      items:items||Object.fromEntries(Object.entries(server.decisions).map(([id,d])=>[id,{decision:clone(d),status:'applied',ledger:true}])),removed:removed||{},error,
      computed:{snapshot:'snapshot_test.json',run_at:'2026-11-06 09:50',computed_at:'2026-11-06T02:00:00Z',score_rule_version:'v1.3.2',risk_control_version:'v1.4.0',themes:[{theme:'美股 AI',score,tier,legacy_tier:tier}]},outputs:{}};
    for(const [k,f]of Object.entries({latest:'confidence/latest.json',candidates:'confidence/candidates.json',reviewed:'confidence/reviewed.csv',ledger:'confidence/ledger.csv'}))r.outputs[k+'_sha256']=hash(server.files.get(f));
    server.receipt=r;putJSON('confidence/review-sync.json',r);return r;
  }
  return {run,node,server,timers,windowListeners,documentListeners,publish,putJSON,
    write:(id,d)=>{context.__id=id;context.__doc=d;return run('ghWrite(__id,__doc)');},
    check:()=>run('ghCheckComputation(true)'),
    settle:async()=>{for(let i=0;i<200&&run('ghComputeChecking');i++)await new Promise(r=>setImmediate(r));assert.equal(run('ghComputeChecking'),false,'read-only progress check settles');},
    stage:id=>JSON.parse(run(`JSON.stringify(ghDecisionStage(${JSON.stringify(id)}))`)),
    state:()=>JSON.parse(run('JSON.stringify({decisions,ghSaved,ghComputation,score:DATA.themes[0].score,tier:DATA.themes[0].derisk.tier,ghToken,canWrite,ops:[...ghSaves.values()]})'))};
}

test('saving only shows waiting; exact receipt and all outputs are required before score and risk refresh',async()=>{
  const h=harness();await h.write('A',decision('A'));
  assert.match(h.stage('A').text,/待入账重算/);assert.equal(h.state().score,70);
  assert.equal(h.server.requests.some(r=>r.method==='POST'),false,'automatic compute requires no Actions dispatch');
  h.publish();await h.check();
  assert.match(h.stage('A').text,/已入账.*已重算/);assert.equal(h.state().score,82);assert.equal(h.state().tier,2);
  assert.equal(h.state().ghComputation.verified,true);
});

test('an older receipt for the same id never marks a newer decision computed',async()=>{
  const old=decision('A','旧'),h=harness({initial:{A:old}});h.publish();await h.write('A',decision('A','新'));
  await h.check();assert.match(h.stage('A').text,/待入账重算|本次计算回执待核/);assert.notEqual(h.stage('A').state,'synced');
});

test('a mixed latest generation keeps old score and cannot claim successful computation',async()=>{
  const h=harness({initial:{A:decision('A')}});h.publish();h.putJSON('confidence/latest.json',latest(99,3));await h.check();
  assert.equal(h.state().score,70);assert.equal(h.state().ghComputation.verified,false);assert.match(h.state().ghComputation.error,/尚未对齐/);
});

test('receipt replacement during reads is rejected instead of applying a partial publication',async()=>{
  let seen=0;const h=harness({initial:{A:decision('A')},hook:req=>{
    if(req.route==='contents/confidence/review-sync.json'&&++seen===2)h.putJSON('confidence/review-sync.json',{...h.server.receipt,generated_at:'2026-11-06T02:01:00Z'});
  }});h.publish();await h.check();assert.equal(h.state().score,70);assert.match(h.state().ghComputation.error,/新一轮/);
});

test('a new queued save during a calculation read is preserved and prevents stale DATA replacement',async()=>{
  const blocked=deferred(),started=deferred();let held=false;
  const h=harness({initial:{A:decision('A')},hook:async req=>{
    if(req.route==='contents/confidence/latest.json'&&!held){held=true;started.resolve();await blocked.promise;}
  }});h.publish();const checking=h.check();await started.promise;await h.write('B',decision('B'));blocked.resolve();await checking;
  assert.equal(h.state().decisions.B.evidence,'证据B');assert.equal(h.state().score,70);assert.equal(h.state().ops.find(x=>x.id==='B').state,'saved');
});

test('an optimistic write while receipt metadata is pending is not rolled back by remote decisions',async()=>{
  const blocked=deferred(),started=deferred();let held=false;
  const h=harness({initial:{A:decision('A')},hook:async req=>{
    if(req.route==='contents/confidence/review-sync.json'&&!held){held=true;started.resolve();await blocked.promise;}
  }});h.publish();const checking=h.check();await started.promise;await h.write('B',decision('B'));blocked.resolve();await checking;
  assert.equal(h.state().decisions.B.evidence,'证据B');assert.equal(h.state().ghSaved.B.evidence,'证据B');
});

test('refresh or focus resumes calculation for already saved decisions without resubmitting them',async()=>{
  const h=harness({initial:{A:decision('A')}});h.publish();await h.run('ghLoad(false)');assert.ok(h.timers.size);
  h.windowListeners.get('focus')();await h.settle();
  await h.check();assert.match(h.stage('A').text,/已入账/);assert.equal(h.server.requests.filter(r=>r.method!=='GET').length,0);
});

test('failed server computation and retry HTTP204 do not display an applied score',async()=>{
  const d=decision('A'),h=harness({initial:{A:d}});h.publish({status:'failed',error:'模拟计算失败',items:{A:{decision:d,status:'failed',ledger:false,error:'模拟计算失败'}}});
  await h.check();assert.match(h.stage('A').text,/计算失败/);assert.equal(h.state().score,70);
  await h.run('ghRetryComputation()');assert.match(h.state().ghComputation.error,/已受理.*尚未确认/);assert.equal(h.state().score,70);
  h.publish();await h.check();assert.match(h.stage('A').text,/已入账.*重算/);
});

test('invalid fields and immutable old ledger changes get an actionable terminal state',async()=>{
  const d=decision('A'),h=harness({initial:{A:d}});h.publish({status:'partial',items:{A:{decision:d,status:'needs_review',ledger:true,error:'原记录已入账，请追加订正'}}});await h.check();
  assert.match(h.stage('A').text,/追加订正/);assert.equal(h.stage('A').state,'failed');assert.equal(h.state().ghComputation.verified,true);
});

test('pre-processing cancellation is only confirmed against the current decisions blob',async()=>{
  const h=harness({initial:{A:decision('A')}});await h.write('A',null);
  h.publish({items:{},removed:{A:{status:'cancelled'}},sourceSha:'a'.repeat(40)});await h.check();assert.match(h.stage('A').text,/待入账/);
  h.publish({items:{},removed:{A:{status:'cancelled'}}});await h.check();assert.match(h.stage('A').text,/已撤销/);
});

test('read errors keep authentication and saved decisions intact',async()=>{
  const h=harness({initial:{A:decision('A')},hook:req=>req.route==='contents/confidence/review-sync.json'?response(503,{}):undefined});await h.check();
  assert.equal(h.state().ghToken,'fixture');assert.equal(h.state().canWrite,true);assert.equal(h.state().decisions.A.evidence,'证据A');assert.match(h.state().ghComputation.error,/503/);
});

test('automatic polling is bounded and focus can start a fresh check',async()=>{
  const h=harness({initial:{A:decision('A')}});h.run('ghComputeAttempts=GH_COMPUTE_DELAYS.length;ghWatchComputation()');
  assert.equal(h.state().ghComputation.status,'paused');assert.equal(h.timers.size,0);
  h.publish();h.windowListeners.get('focus')();await h.settle();assert.match(h.stage('A').text,/已入账/);
});

test('receipt snapshot mismatch is rejected even if its raw output hashes match',async()=>{
  const h=harness({initial:{A:decision('A')}});const r=h.publish();h.putJSON('confidence/review-sync.json',{...r,computed:{...r.computed,snapshot:'other.json'}});await h.check();assert.equal(h.state().score,70);assert.match(h.state().ghComputation.error,/快照或版本/);
});

test('malformed calculated data cannot leave an exact decision marked applied',async()=>{
  const h=harness({initial:{A:decision('A')}}),r=h.publish();
  h.putJSON('confidence/latest.json',{...latest(82,2),themes:null});r.outputs.latest_sha256=hash(h.server.files.get('confidence/latest.json'));h.putJSON('confidence/review-sync.json',r);
  await h.check();assert.equal(h.state().score,70);assert.equal(h.state().ghComputation.verified,false);assert.notEqual(h.stage('A').state,'synced');
});

test('receipt risk or theme score metadata must agree with the actual output',async()=>{
  const h=harness({initial:{A:decision('A')}}),r=h.publish();
  r.computed.themes[0].tier=3;h.putJSON('confidence/review-sync.json',r);await h.check();
  assert.equal(h.state().score,70);assert.match(h.state().ghComputation.error,/主题分数或风险档/);
});

test('a completed non-ledger decision is processed without pretending it entered the ledger',async()=>{
  const d={...decision('A'),class:'噪声'},h=harness({initial:{A:d}});
  h.publish({items:{A:{decision:d,status:'not_ledger',ledger:false}}});await h.check();
  assert.match(h.stage('A').text,/已处理.*已重算/);assert.doesNotMatch(h.stage('A').text,/已入账/);
});

test('completed computation keeps a new-evidence mainline research review pending',async()=>{
  const h=harness({initial:{A:decision('A')}}),r=h.publish(),L=latest(82,2);
  L.themes[0].research_review={asof:'2026-11-06 09:50',review_complete:true,has_new_ledger_evidence:true};
  h.putJSON('confidence/latest.json',L);r.outputs.latest_sha256=hash(h.server.files.get('confidence/latest.json'));h.putJSON('confidence/review-sync.json',r);await h.check();
  assert.match(h.stage('A').text,/已入账.*重算/);assert.match(h.node('#gh-compute-status').innerHTML,/主线研究待复检/);
  assert.equal(h.run('DATA.themes[0].research_review.asof'),'2026-11-06 09:50');
});

test('initial page load rejects a mixed output generation before displaying a new score',async()=>{
  const h=harness({initial:{A:decision('A')}});h.publish();h.putJSON('confidence/latest.json',latest(99,3));
  await h.run('ghLoad(false)');assert.equal(h.state().score,70);assert.match(h.node('#login').innerHTML,/尚未对齐/);
});

test('after refresh a historical removal still exposes the required correction instead of all-complete',async()=>{
  const h=harness();h.publish({status:'partial',removed:{A:{status:'needs_review',error:'旧账本已经处理，请追加订正'}}});
  await h.check();assert.match(h.node('#gh-compute-status').innerHTML,/需要补齐或追加订正/);assert.match(h.node('#gh-compute-status').innerHTML,/旧账本已经处理/);
});

test('an impossible applied-without-ledger receipt is rejected rather than claiming completion',async()=>{
  const d=decision('A'),h=harness({initial:{A:d}});h.publish({items:{A:{decision:d,status:'applied',ledger:false}}});
  await h.check();assert.notEqual(h.stage('A').state,'synced');assert.match(h.state().ghComputation.error,/记录状态不符/);assert.equal(h.state().score,70);
});
