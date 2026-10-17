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
export class ApiError extends Error { status:number; constructor(status:number,message:string){super(message);this.status=status} }
export async function request(path:string,options:{method?:string;body?:unknown;token?:string;revision?:number;key?:string}={}) {
 const headers:Record<string,string>={'Accept':'application/json'};
 if(options.body!==undefined)headers['Content-Type']='application/json';
 if(options.token)headers['X-Workspace-Token']=options.token;
 if(options.revision!==undefined)headers['If-Match']=String(options.revision);
 if(options.method&&options.method!=='GET')headers['Idempotency-Key']=options.key||crypto.randomUUID();
 const res=await fetch('/api/v1'+path,{method:options.method||'GET',headers,body:options.body===undefined?undefined:JSON.stringify(options.body)});
 let payload:RecordValue={};try{payload=await res.json()}catch{ /* A gateway can return HTML. */ }
 if(!res.ok){const error=payload.error||payload.detail;throw new ApiError(res.status,typeof error==='string'?error:error?.message||payload.message||`Request failed (${res.status}). Please try again.`)}
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
