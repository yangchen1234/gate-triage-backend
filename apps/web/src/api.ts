export type RecordValue = Record<string, any>;
export type Workspace = RecordValue & { id:string; revision:number; snapshot:RecordValue; token?:string };
const SESSION_KEY='gate-triage-session-v1';
const RECENT_KEY='gate-triage-recent-workspaces-v1';
export type RecentWorkspace={id:string;token:string;name:string;scenario_name:string;scenario_id:string;clock_min:number;last_used:string;unavailable?:boolean};
export function savedSession():{id:string;token:string}|null {try{const value=JSON.parse(localStorage.getItem(SESSION_KEY)||'null');return value&&typeof value.id==='string'&&typeof value.token==='string'?value:null}catch{return null}}
export function recentWorkspaces():RecentWorkspace[]{try{const value=JSON.parse(localStorage.getItem(RECENT_KEY)||'[]');return Array.isArray(value)?value.filter(item=>item&&typeof item.id==='string'&&typeof item.token==='string').sort((a,b)=>String(b.last_used||'').localeCompare(String(a.last_used||''))):[]}catch{return []}}
export function saveRecentWorkspace(id:string,token:string,metadata:Partial<Omit<RecentWorkspace,'id'|'token'>>={}){if(!id||!token)return;const items=recentWorkspaces(),previous=items.find(item=>item.id===id);const entry:RecentWorkspace={name:'Saved rehearsal',scenario_name:'Simulation rehearsal',scenario_id:'',clock_min:0,last_used:new Date().toISOString(),...previous,...metadata,id,token,unavailable:false};localStorage.setItem(RECENT_KEY,JSON.stringify([entry,...items.filter(item=>item.id!==id)]));}
export function saveSession(id:string,token:string,metadata:Partial<Omit<RecentWorkspace,'id'|'token'>>={}){const previous=savedSession();if(previous&&previous.id!==id&&!recentWorkspaces().some(item=>item.id===previous.id))saveRecentWorkspace(previous.id,previous.token);saveRecentWorkspace(id,token,{...metadata,last_used:new Date().toISOString()});localStorage.setItem(SESSION_KEY,JSON.stringify({id,token}));}
export function markWorkspaceUnavailable(id:string){const items=recentWorkspaces();localStorage.setItem(RECENT_KEY,JSON.stringify(items.map(item=>item.id===id?{...item,unavailable:true}:item)));}
export function clearSession(){localStorage.removeItem(SESSION_KEY)}
export function canApplySnapshot(current:{id:string;revision:number}|null,incoming:{id:string;revision:number}){return !current||current.id!==incoming.id||incoming.revision>=current.revision;}
export class ApiError extends Error { status:number; constructor(status:number,message:string){super(message);this.status=status} }
export class TransportError extends Error {
  outcomeUnknown=true;
  constructor(){super('Connection interrupted. The result is not confirmed. Reconnect, then retry the same action to recover its original receipt.');}
}
const pendingMemory=new Map<string,string>();
function intentRead(key:string){try{if(typeof sessionStorage!=='undefined')return sessionStorage.getItem(key)}catch{}return pendingMemory.get(key)||null;}
function intentWrite(key:string,value:string){pendingMemory.set(key,value);try{if(typeof sessionStorage!=='undefined')sessionStorage.setItem(key,value)}catch{ /* Memory still protects retries while this tab remains open. */ }}
function canonical(value:any):any{if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));return value;}
/** Pending logical submissions survive rerenders and reloads in this browser tab.
 * Only body fingerprints and random request keys are stored; no token or form text.
 */
export class LogicalSubmission {
  storageKey:string;
  constructor(namespace:string){this.storageKey=`gate-triage-pending:${namespace}`;}
  entries():Record<string,{key:string;created_at:string}>{try{return JSON.parse(intentRead(this.storageKey)||'{}')}catch{return {}}}
  async keyFor(body:unknown){
    const serialized=JSON.stringify(canonical(JSON.parse(JSON.stringify(body??null))));
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(serialized));
    const fingerprint=Array.from(new Uint8Array(digest)).map(byte=>byte.toString(16).padStart(2,'0')).join('');
    const entries=this.entries();if(entries[fingerprint]?.key)return entries[fingerprint].key;
    const key=crypto.randomUUID();entries[fingerprint]={key,created_at:new Date().toISOString()};intentWrite(this.storageKey,JSON.stringify(entries));return key;
  }
  finish(key:string){const entries=this.entries();for(const fingerprint of Object.keys(entries))if(entries[fingerprint].key===key)delete entries[fingerprint];intentWrite(this.storageKey,JSON.stringify(entries));}
}
export async function request(path:string,options:{method?:string;body?:unknown;token?:string;revision?:number;key?:string}={}) {
 const method=options.method||'GET',headers:Record<string,string>={'Accept':'application/json'};
 const intent=method!=='GET'&&!options.key?new LogicalSubmission(`${method}:${path}`):null;
 if(options.body!==undefined)headers['Content-Type']='application/json';
 if(options.token)headers['X-Workspace-Token']=options.token;
 if(options.revision!==undefined)headers['If-Match']=String(options.revision);
 if(method!=='GET')headers['Idempotency-Key']=options.key||await intent!.keyFor(options.body);
 const prepared={method,headers,body:options.body===undefined?undefined:JSON.stringify(options.body)};
 let res:Response|undefined;
 for(let attempt=0;attempt<2;attempt++){
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),15000);
  try{res=await fetch('/api/v1'+path,{...prepared,signal:controller.signal});break}
  catch{if(attempt===1)throw new TransportError();await new Promise(resolve=>setTimeout(resolve,300))}
  finally{clearTimeout(deadline)}
 }
 if(!res)throw new TransportError();
 let payload:RecordValue={},parseFailed=false;try{payload=await res.json()}catch{parseFailed=true}if(res.ok&&parseFailed)throw new TransportError();
 if(!res.ok){if(res.status<500&&intent)intent.finish(headers['Idempotency-Key']);const error=payload.error||payload.detail;throw new ApiError(res.status,typeof error==='string'?error:error?.message||payload.message||`Request failed (${res.status}). Please try again.`)}
 if(intent)intent.finish(headers['Idempotency-Key']);
 return payload;
}
export async function pollJob(workspaceId:string,token:string,jobId:string,onProgress:(job:RecordValue)=>void){
 for(let i=0;i<240;i++){
  const response=await request(`/workspaces/${workspaceId}/jobs/${jobId}`,{token});const job=response.data||response;onProgress(job);
  if(job.status==='succeeded')return job.result;
  if(['failed','cancelled','superseded'].includes(job.status))throw new Error(job.error?.message||job.error||`Job ${job.status}.`);
  await new Promise(resolve=>setTimeout(resolve,500));
 }
 throw new Error('This job is taking longer than expected. The server keeps its progress; refresh to reconnect.');
}
export const WORKSPACE_VIEWS=['operations','simulation','experiments','evidence','scale'] as const;
export type WorkspaceView=typeof WORKSPACE_VIEWS[number];
export function savedWorkspaceView(workspaceId:string):WorkspaceView|null{if(!workspaceId)return null;try{const value=localStorage.getItem(`gate-triage-view-${workspaceId}`);return WORKSPACE_VIEWS.includes(value as WorkspaceView)?value as WorkspaceView:null}catch{return null}}
export function saveWorkspaceView(workspaceId:string,view:WorkspaceView){if(!workspaceId||!WORKSPACE_VIEWS.includes(view))return;try{localStorage.setItem(`gate-triage-view-${workspaceId}`,view)}catch{ /* Navigation remains usable if local storage is unavailable. */ }}
