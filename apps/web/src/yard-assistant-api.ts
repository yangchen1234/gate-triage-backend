import { api, ApiError, consoleSessionHeaders, loadSession, newSession } from './api.ts';
import { ensureYardSession, YardApiError, yardRequest } from './yard-api.ts';
import type { DemoPort, Issue } from './yard-demo.ts';
export type AdvisoryRequest = { containerId:string; issue:Exclude<Issue,'clear'>; question:string };
export type YardAdvisory = {
 id:string; requestId:string; runId:string; inputRevision:number; port:DemoPort; containerId:string; issue:Issue;
 question:string; status:'running'|'succeeded'|'failed'; stale:boolean; createdAt:string; completedAt:string|null; error:string|null;
 context:{ recipientRole:string; escalation:'supervisor_now'|'responsible_team'; language:'en'|'nl'; facts:{id:string;label:string;value:unknown}[]; rules:string[] };
 result:null|{summary:string;recommendations:{action:string;rationale:string;evidenceIds:string[]}[];missingInformation:string[];subject:string;body:string;recipientRole:string;escalation:string;source:'claude';model:string;language:string;generatedAt:string;rules:string[];delivery:'draft_only'};
};
export async function assistantModel() {
 try { await loadSession(); return (await api.session()).model; }
 catch(error) { if(error instanceof ApiError && error.status===401) return (await newSession()).model; throw error; }
}
export function advisoryIsStale(job:YardAdvisory,runId:string,revision:number) {
 return job.stale||job.runId!==runId||job.inputRevision!==revision;
}
function check(job:YardAdvisory,port:DemoPort,containerId?:string,issue?:Issue) {
 if(!job||job.port!==port||(containerId&&job.containerId!==containerId)||(issue&&job.issue!==issue)||!['running','succeeded','failed'].includes(job.status)||typeof job.id!=='string'||typeof job.runId!=='string'||!Number.isSafeInteger(job.inputRevision))throw new YardApiError(502,'Invalid advisory response.');
 return job;
}
export const yardAssistantApi = {
 async generate(port:DemoPort,body:AdvisoryRequest,etag:string,key:string):Promise<YardAdvisory>{
  await ensureYardSession();
  return check((await yardRequest(`/ports/${port}/advisories`,{method:'POST',headers:{...consoleSessionHeaders(),'If-Match':etag,'Idempotency-Key':key},body:JSON.stringify(body)})).data,port,body.containerId,body.issue);
 },
 async job(port:DemoPort,id:string):Promise<YardAdvisory>{const job=check((await yardRequest(`/ports/${port}/advisories/${encodeURIComponent(id)}`)).data,port);if(job.id!==id)throw new YardApiError(502,'Invalid advisory response.');return job;},
 async latest(port:DemoPort,containerId:string,issue:Issue):Promise<YardAdvisory|null>{
  await ensureYardSession();
  const job=(await yardRequest(`/ports/${port}/advisories?${new URLSearchParams({container_id:containerId,issue})}`)).data.job;
  return job?check(job,port,containerId,issue):null;
 },
};
