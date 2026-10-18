import test from 'node:test';
import assert from 'node:assert/strict';
const {yardAssistantApi,assistantModel,advisoryIsStale,assistantConnectionState}=await import('../src/yard-assistant-api.ts');
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
const model={configured:true,model:'claude-test',source:'render_environment',server_available:true};
const draft={id:'job-1',requestId:'request-1',runId:'run-1',inputRevision:3,port:'la',containerId:'SIMU1',issue:'customs',status:'running',stale:false};

test('assistant reads never start a paid request; explicit generation carries both scopes and exact retry identity',async()=>{
 const original=globalThis.fetch,calls=[];
 globalThis.fetch=async(url,init={})=>{
  calls.push([url,init]);
  if(url==='/api/console/session')return response({token:'console-capability',model});
  if(url==='/api/yard/session')return response({workspaceId:'workspace'});
  if(url.includes('/advisories?'))return response({job:null});
  return response(draft);
 };
 try{
  assert.deepEqual(await assistantModel(),model);
  assert.equal(await yardAssistantApi.latest('la','SIMU1','customs'),null);
  assert.ok(!calls.some(([u,i])=>u.endsWith('/advisories')&&i.method==='POST'));
  const body={containerId:'SIMU1',issue:'customs',question:'What should be verified?'};
  for(let i=0;i<2;i++)await yardAssistantApi.generate('la',body,'"run-1:3"','request-1');
  const writes=calls.filter(([u,i])=>u.endsWith('/advisories')&&i.method==='POST');
  assert.equal(writes.length,2);
  for(const[,init]of writes){
   assert.equal(init.headers.get('X-Console-Token'),'console-capability');
   assert.equal(init.headers.get('X-Yard-Request'),'1');
   assert.equal(init.headers.get('If-Match'),'"run-1:3"');
   assert.equal(init.headers.get('Idempotency-Key'),'request-1');
   assert.equal(init.credentials,'same-origin');
   assert.deepEqual(JSON.parse(init.body),body);
   assert.ok(!init.body.includes('api_key'));
  }
 }finally{globalThis.fetch=original;}
});

test('an ambiguous assistant submission never retries automatically and keeps the provider destination on the server',async()=>{
 const original=globalThis.fetch;let calls=0;
 globalThis.fetch=async(url)=>{assert.ok(url.startsWith('/api/yard/'));calls++;throw new TypeError('timeout');};
 try{await assert.rejects(yardAssistantApi.generate('la',{containerId:'SIMU1',issue:'weight',question:''},'"run-1:3"','request-2'),e=>e.status===0);assert.equal(calls,1);}finally{globalThis.fetch=original;}
});

test('saved draft reads reject wrong container, issue, port or job identity',async()=>{
 const original=globalThis.fetch;
 try{
  for(const change of [{containerId:'SIMU2'},{issue:'power'},{port:'rotterdam'}]){
   globalThis.fetch=async()=>response({job:{...draft,...change}});
   await assert.rejects(yardAssistantApi.latest('la','SIMU1','customs'),e=>e.status===502);
  }
  globalThis.fetch=async()=>response({...draft,id:'different-job'});
  await assert.rejects(yardAssistantApi.job('la','job-1'),e=>e.status===502);
 }finally{globalThis.fetch=original;}
});

test('advisory freshness includes run identity, revision and explicit server invalidation',()=>{
 assert.equal(advisoryIsStale(draft,'run-1',3),false);
 assert.equal(advisoryIsStale(draft,'run-1',4),true);
 assert.equal(advisoryIsStale(draft,'new-run',3),true);
 assert.equal(advisoryIsStale({...draft,stale:true},'run-1',3),true);
});

test('connection readiness honors expiry instead of leaving a misleading ready state',()=>{
 const now=Date.parse('2026-10-18T01:00:00Z');
 assert.equal(assistantConnectionState(null,now),'checking');
 assert.equal(assistantConnectionState({...model,key_expires_at:'2026-10-18T01:15:00Z'},now),'ready');
 assert.equal(assistantConnectionState({...model,key_expires_at:'2026-10-18T01:00:00Z'},now),'expired');
 assert.equal(assistantConnectionState({...model,key_expires_at:'invalid'},now),'expired');
 assert.equal(assistantConnectionState({...model,configured:false},now),'team_required');
 assert.equal(assistantConnectionState({...model,configured:false,server_available:false},now),'unavailable');
});
