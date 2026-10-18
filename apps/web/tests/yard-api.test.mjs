import test from 'node:test';
import assert from 'node:assert/strict';
let serial=0;
const load=()=>import(`../src/yard-api.ts?test=${++serial}`);
const snap=(revision=1)=>({workspaceId:'workspace-1',runId:'run-1',revision,run:{port:'la'},blocks:[{id:'A01'}],catalog:[{id:'SIMU1'}],database:'sqlite'});
function response(data,status=200){return new Response(data===null?null:JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}})}

test('yard StrictMode bootstrap shares one cookie session request and reads only the non-agent API',async()=>{
 const old=globalThis.fetch,calls=[];
 globalThis.fetch=async(url,init)=>{calls.push([url,init]);return response(url.endsWith('/session')?{workspaceId:'workspace-1'}:snap());};
 try{const{yardApi}=await load();const results=await Promise.all([yardApi.snapshot('la'),yardApi.snapshot('la')]);assert.equal(results.length,2);assert.equal(calls.filter(([u])=>u.endsWith('/session')).length,1);assert.ok(calls.every(([u,i])=>u.startsWith('/api/yard/')&&i.credentials==='same-origin'&&i.headers.get('X-Yard-Request')==='1'));assert.ok(!calls.some(([u])=>u.includes('agent')||u.includes('plan')));}finally{globalThis.fetch=old;}
});
test('yard commands transmit the same version and idempotency key on an explicit retry',async()=>{
 const old=globalThis.fetch,calls=[];
 globalThis.fetch=async(url,init)=>{calls.push([url,init]);return response(url.endsWith('/session')?{workspaceId:'workspace-1'}:snap(2));};
 try{const{yardApi,yardETag}=await load();const event={type:'gate_out',containerId:'SIMU1',scenario:'routine',evidence:'SIM exit',clearanceConfirmed:true,exitConfirmed:true};for(let i=0;i<2;i++)await yardApi.command('la',event,yardETag(snap()),'stable-request-key');const writes=calls.filter(([u])=>u.endsWith('/commands'));assert.equal(writes.length,2);for(const[,init]of writes){assert.equal(init.headers.get('If-Match'),'"run-1:1"');assert.equal(init.headers.get('Idempotency-Key'),'stable-request-key');assert.deepEqual(JSON.parse(init.body),event);assert.equal(JSON.parse(init.body).at,undefined);}}finally{globalThis.fetch=old;}
});
test('unchanged yard reads use conditional ETags and preserve the acknowledged snapshot',async()=>{
 const old=globalThis.fetch;let conditional;
 globalThis.fetch=async(url,init)=>{if(url.endsWith('/session'))return response({workspaceId:'workspace-1'});conditional=init.headers.get('If-None-Match');return response(null,304);};
 try{const{yardApi}=await load();assert.equal(await yardApi.snapshot('la','"run-1:4"'),null);assert.equal(conditional,'"run-1:4"');}finally{globalThis.fetch=old;}
});
test('stale-version details survive transport and ambiguous saves do not silently retry',async()=>{
 const old=globalThis.fetch;let attempts=0;
 globalThis.fetch=async(url)=>{if(url.endsWith('/session'))return response({workspaceId:'workspace-1'});attempts++;return response({detail:'Current data changed; review again.'},412);};
 try{const{yardApi}=await load();await assert.rejects(yardApi.command('la',{type:'reset'},'"run-1:1"','request-id'),e=>e.status===412&&e.message==='Current data changed; review again.');assert.equal(attempts,1);globalThis.fetch=async()=>{attempts++;throw new TypeError('network down')};await assert.rejects(yardApi.command('la',{type:'reset'},'"run-1:1"','request-id'),e=>e.status===0&&e.message.includes('retry the same request'));assert.equal(attempts,2);}finally{globalThis.fetch=old;}
});
test('a cross-port or previous-workspace response cannot replace the current yard',async()=>{
 const old=globalThis.fetch;
 globalThis.fetch=async(url)=>response(url.endsWith('/session')?{workspaceId:'workspace-1'}:{...snap(),workspaceId:'old-workspace'});
 try{const{yardApi}=await load();await assert.rejects(yardApi.snapshot('la'),e=>e.status===-1);globalThis.fetch=async()=>response({...snap(),run:{port:'rotterdam'}});await assert.rejects(yardApi.snapshot('la'),e=>e.status===502);}finally{globalThis.fetch=old;}
});
