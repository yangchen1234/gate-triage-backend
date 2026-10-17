import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { LogicalSubmission, TransportError, request, canApplySnapshot } from '../src/api.ts';
beforeEach(()=>{const values=new Map();globalThis.sessionStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};});
test('a logical submission keeps its key across remounts and differently ordered object keys',async()=>{
 const one=new LogicalSubmission('form-stability');const key=await one.keyFor({title:'A',container_ids:['C1']});
 assert.equal(await new LogicalSubmission('form-stability').keyFor({container_ids:['C1'],title:'A'}),key);
 assert.notEqual(await one.keyFor({title:'Changed',container_ids:['C1']}),key);
 one.finish(key);assert.notEqual(await one.keyFor({title:'A',container_ids:['C1']}),key);
});
test('transport retries use the exact same key and request body',async()=>{
 const calls=[];globalThis.fetch=async(_url,options)=>{calls.push(options);if(calls.length===1)throw new Error('lost');return new Response(JSON.stringify({data:{id:'saved'}}),{status:200})};
 await request('/test-network-once',{method:'POST',body:{title:'One request'}});
 assert.equal(calls.length,2);assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);assert.equal(calls[0].body,calls[1].body);
});
test('a user retry after unknown commit recovers its original logical key',async()=>{
 const keys=[];globalThis.fetch=async(_url,options)=>{keys.push(options.headers['Idempotency-Key']);throw new Error('response lost')};
 await assert.rejects(request('/test-unknown',{method:'POST',body:{title:'Saved maybe'}}),TransportError);
 globalThis.fetch=async(_url,options)=>{keys.push(options.headers['Idempotency-Key']);return new Response(JSON.stringify({data:{id:'same-original'}}),{status:200})};
 await request('/test-unknown',{method:'POST',body:{title:'Saved maybe'}});
 assert.equal(new Set(keys).size,1);
});
test('completed intentional submissions receive new keys while separate pending bodies retain their own keys',async()=>{
 const intent=new LogicalSubmission('multi-pending'),first=await intent.keyFor({title:'First'}),second=await intent.keyFor({title:'Second'});
 assert.notEqual(first,second);assert.equal(await intent.keyFor({title:'First'}),first);
 intent.finish(first);assert.equal(await intent.keyFor({title:'Second'}),second);
});

test('same-workspace stale snapshots cannot rewind a newer revision',()=>{assert.equal(canApplySnapshot({id:'one',revision:12},{id:'one',revision:11}),false);assert.equal(canApplySnapshot({id:'one',revision:12},{id:'one',revision:12}),true);assert.equal(canApplySnapshot({id:'one',revision:12},{id:'one',revision:13}),true);assert.equal(canApplySnapshot({id:'one',revision:12},{id:'other',revision:1}),true);});
test('a truncated successful response retains the key for receipt recovery',async()=>{const keys=[];globalThis.fetch=async(_url,options)=>{keys.push(options.headers['Idempotency-Key']);return new Response('{broken',{status:200})};await assert.rejects(request('/test-partial-response',{method:'POST',body:{title:'Saved'}}),TransportError);globalThis.fetch=async(_url,options)=>{keys.push(options.headers['Idempotency-Key']);return new Response(JSON.stringify({data:{id:'original'}}),{status:200})};await request('/test-partial-response',{method:'POST',body:{title:'Saved'}});assert.equal(keys[0],keys[1]);});
